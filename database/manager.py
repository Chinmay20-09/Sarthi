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
"""

import logging
import sqlite3
from pathlib import Path
from typing import Any

from config import PROJECT_ROOT

logger = logging.getLogger(__name__)

# Default database path (relative to project root)
DEFAULT_DB_PATH = PROJECT_ROOT / "database" / "sarthi.db"


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
                     Defaults to PROJECT_ROOT / "data" / "sarthi.db"
        """
        self.db_path = db_path or DEFAULT_DB_PATH
        self._connection: sqlite3.Connection | None = None

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
        # threadpool, so the connection (created at startup) is used from
        # worker threads. SQLite serializes access at the module level and
        # the file locks handle concurrency.
        self._connection = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.execute("PRAGMA foreign_keys=ON")
        logger.info(f"Connected to database: {self.db_path}")

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
        cursor = self.connection.cursor()
        cursor.executemany(sql, params_list)
        self.connection.commit()

    def fetch_one(self, sql: str, params: tuple = ()) -> dict[str, Any] | None:
        """
        Fetch a single row as a dictionary.

        Args:
            sql: SQL query
            params: Query parameters

        Returns:
            Row as dict, or None if no results
        """
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
