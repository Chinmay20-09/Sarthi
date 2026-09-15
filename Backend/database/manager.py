"""
DatabaseManager — Centralized database access for Sarthi.

Every skill and package uses DatabaseManager instead of creating
its own connections. This ensures:
    - Single SQLite connection (no connection duplication)
    - Shared schema management via models.py
    - Consistent query API across all skills
    - Centralized caching

Usage:
    db = DatabaseManager()
    db.execute("INSERT INTO my_table ...", (value1, value2))
    rows = db.fetch_all("SELECT * FROM my_table")
    row = db.fetch_one("SELECT * FROM my_table WHERE id = ?", (id,))

    # Multi-statement atomic write (single commit, rolled back on error):
    with db.transaction() as tx:
        tx.execute("INSERT ...", (a,))
        tx.execute("UPDATE ...", (b,))
"""

import logging
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from config import PROJECT_ROOT

from database.models import ALL_INDEXES, ALL_TABLES

logger = logging.getLogger(__name__)

# Default database path (relative to project root)
DEFAULT_DB_PATH = PROJECT_ROOT / "database" / "sarthi.db"

# How long a write waits for a competing writer's lock before failing with
# "database is locked". FastAPI runs sync endpoints in a threadpool, so two
# requests can write concurrently; without this the loser fails instantly.
BUSY_TIMEOUT_MS = 5_000


class DatabaseManager:
    """
    Manages the SQLite database connection and provides
    a consistent query API for all skills.

    All database access goes through this class.
    Skills should never create their own connections.
    """

    def __init__(self, db_path: Path | None = None):
        """
        Initialize database connection.

        Args:
            db_path: Path to SQLite database file.
                     Defaults to PROJECT_ROOT / "database" / "sarthi.db"
        """
        self.db_path = db_path or DEFAULT_DB_PATH
        self._connection: sqlite3.Connection | None = None
        # Serializes access to the shared connection. check_same_thread=False
        # lets the connection be *used* from any thread (FastAPI threadpool);
        # this lock makes concurrent use safe rather than merely permitted.
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    @property
    def connection(self) -> sqlite3.Connection:
        """Lazily initialize and return the database connection."""
        if self._connection is None:
            self._connect()
        return self._connection

    def _connect(self) -> None:
        """Create the database connection and ensure directory exists."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        # check_same_thread=False: FastAPI/uvicorn runs sync endpoints in a
        # threadpool, so the connection (created lazily on first use) is used
        # from worker threads. Access is serialized by self._lock.
        self._connection = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        # WAL: readers don't block the writer and vice versa; commits don't
        # force a full checkpoint. synchronous=NORMAL is the standard WAL
        # pairing — durable across app crashes without per-commit fsyncs
        # (only a power loss may roll back the last transactions).
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.execute("PRAGMA synchronous=NORMAL")
        self._connection.execute("PRAGMA foreign_keys=ON")
        self._connection.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS}")
        self._ensure_canonical_schema()
        logger.info(f"Connected to database: {self.db_path}")

    def _ensure_canonical_schema(self) -> None:
        """Create every canonical table and index from models.py.

        Idempotent (all statements are IF NOT EXISTS), so this runs on every
        connect and the schema is self-healing: callers no longer need to
        scatter CREATE TABLE statements through endpoints and skills.
        """
        try:
            cursor = self._connection.cursor()
            for sql in ALL_TABLES.values():
                cursor.execute(sql)
            for sql in ALL_INDEXES.values():
                cursor.execute(sql)
            self._connection.commit()
        except sqlite3.Error as e:
            # Never block startup over schema bootstrap; individual callers
            # create their own tables when needed and will surface real errors.
            logger.warning(f"Canonical schema bootstrap failed: {e}")

    def close(self) -> None:
        """Close the database connection."""
        if self._connection is not None:
            self._connection.close()
            self._connection = None
            logger.debug("Database connection closed")

    def __del__(self):
        """Ensure connection is closed on garbage collection."""
        self.close()

    # ------------------------------------------------------------------
    # Query API
    # ------------------------------------------------------------------

    def execute(self, sql: str, params: tuple = ()) -> None:
        """
        Execute a write query (INSERT, UPDATE, DELETE, CREATE).

        Args:
            sql: SQL statement
            params: Query parameters
        """
        with self._lock:
            cursor = self.connection.cursor()
            cursor.execute(sql, params)
            self.connection.commit()

    def execute_many(self, sql: str, params_list: list[tuple]) -> None:
        """
        Execute a write query for multiple parameter sets.

        Args:
            sql: SQL statement
            params_list: List of parameter tuples
        """
        with self._lock:
            cursor = self.connection.cursor()
            cursor.executemany(sql, params_list)
            self.connection.commit()

    @contextmanager
    def transaction(self):
        """Group several writes into one atomic commit.

        Yields a cursor-like executor; on success everything is committed in
        a single transaction (one fsync instead of one per statement), and on
        exception everything is rolled back. Reads inside see the writes made
        earlier in the same transaction.
        """
        with self._lock:
            conn = self.connection
            try:
                yield _Transaction(conn)
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    def fetch_one(self, sql: str, params: tuple = ()) -> dict[str, Any] | None:
        """
        Fetch a single row as a dictionary.

        Args:
            sql: SQL query
            params: Query parameters

        Returns:
            Row as dict, or None if no results
        """
        with self._lock:
            cursor = self.connection.cursor()
            cursor.execute(sql, params)
            row = cursor.fetchone()
            return dict(row) if row else None

    def fetch_all(self, sql: str, params: tuple = ()) -> list[dict[str, Any]]:
        """
        Fetch all rows as a list of dictionaries.

        Args:
            sql: SQL query
            params: Query parameters

        Returns:
            List of row dicts
        """
        with self._lock:
            cursor = self.connection.cursor()
            cursor.execute(sql, params)
            rows = cursor.fetchall()
            return [dict(row) for row in rows]

    def table_exists(self, table_name: str) -> bool:
        """Check if a table exists in the database."""
        result = self.fetch_one(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (table_name,),
        )
        return result is not None

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def create_table(self, sql: str) -> None:
        """
        Create a table if it doesn't exist.

        Args:
            sql: CREATE TABLE IF NOT EXISTS statement
        """
        self.execute(sql)
        logger.debug(f"Executed schema: {sql[:60]}...")

    @property
    def is_connected(self) -> bool:
        """Check if the database connection is active."""
        return self._connection is not None


class _Transaction:
    """Executor handed out by DatabaseManager.transaction().

    Writes queue on the open transaction; reads (fetch_one/fetch_all) see
    this transaction's own uncommitted writes. Must NOT be used after the
    ``with`` block exits.
    """

    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def execute(self, sql: str, params: tuple = ()) -> None:
        self._conn.execute(sql, params)

    def executemany(self, sql: str, params_list: list[tuple]) -> None:
        self._conn.executemany(sql, params_list)

    def fetch_one(self, sql: str, params: tuple = ()) -> dict[str, Any] | None:
        """Read one row within this transaction (sees own uncommitted writes)."""
        cursor = self._conn.execute(sql, params)
        row = cursor.fetchone()
        return dict(row) if row else None

    def fetch_all(self, sql: str, params: tuple = ()) -> list[dict[str, Any]]:
        """Read all rows within this transaction (sees own uncommitted writes)."""
        cursor = self._conn.execute(sql, params)
        return [dict(row) for row in cursor.fetchall()]


# Global singleton instance (optional — can also create fresh instances)
_instance: DatabaseManager | None = None


def get_database() -> DatabaseManager:
    """
    Get or create the global DatabaseManager instance.

    Skills can request their own instance via constructor,
    but for simple use cases this singleton is sufficient.

    Returns:
        DatabaseManager instance
    """
    global _instance
    if _instance is None:
        _instance = DatabaseManager()
    return _instance
