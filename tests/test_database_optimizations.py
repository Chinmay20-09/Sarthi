"""Tests for the DatabaseManager optimizations.

Covers:
    - Canonical schema bootstrap: every table and index from models.py is
      created automatically at connect time (self-healing schema).
    - session_id indexes on conversation_messages / chat_messages are real
      and actually used by the query planner.
    - Connection pragmas: WAL journal, synchronous=NORMAL, busy_timeout.
    - transaction(): single atomic commit, rollback on error.
    - Thread-safe writes from FastAPI-style threadpool workers.

All tests use in-memory or tmp_path SQLite; the real sarthi.db is untouched.
"""

import sqlite3
import threading
from pathlib import Path

import pytest
from database.manager import DatabaseManager
from database.models import ALL_INDEXES, ALL_TABLES


@pytest.fixture
def db():
    """In-memory DatabaseManager with the canonical schema bootstrapped."""
    manager = DatabaseManager(db_path=Path(":memory:"))
    _ = manager.connection  # trigger lazy connect + bootstrap
    yield manager
    manager.close()


@pytest.fixture
def file_db(tmp_path: Path):
    """File-backed DatabaseManager (needed for WAL, which :memory: can't use)."""
    manager = DatabaseManager(db_path=tmp_path / "test.db")
    _ = manager.connection
    yield manager
    manager.close()


# ---------------------------------------------------------------------------
# Canonical schema bootstrap
# ---------------------------------------------------------------------------


class TestSchemaBootstrap:
    def test_all_canonical_tables_created_on_connect(self, db):
        """Connecting must create every table registered in ALL_TABLES."""
        for name in ALL_TABLES:
            assert db.table_exists(name), f"Table '{name}' was not bootstrapped"

    def test_all_canonical_indexes_created_on_connect(self, db):
        """Connecting must create every index registered in ALL_INDEXES."""
        rows = db.fetch_all("SELECT name FROM sqlite_master WHERE type='index'")
        names = {row["name"] for row in rows}
        for index_name in ALL_INDEXES:
            assert index_name in names, f"Index '{index_name}' was not bootstrapped"

    def test_bootstrap_is_idempotent(self, db):
        """Re-connecting (close + reuse) must not fail or duplicate schema."""
        db.close()
        _ = db.connection  # reconnect → bootstrap runs again
        rows = db.fetch_all(
            "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_%'"
        )
        assert len(rows) == len(ALL_INDEXES)


# ---------------------------------------------------------------------------
# session_id indexes (the actual optimization)
# ---------------------------------------------------------------------------


class TestSessionIndexes:
    def test_conversation_session_query_uses_index(self, db):
        """The per-session history read must be an index scan, not a table scan."""
        db.execute(
            "INSERT INTO conversation_messages (session_id, role, content) VALUES (?, ?, ?)",
            ("sess_a", "user", "hello"),
        )
        plan = db.fetch_all(
            "EXPLAIN QUERY PLAN SELECT role, content FROM conversation_messages "
            "WHERE session_id = ? ORDER BY id ASC",
            ("sess_a",),
        )
        detail = " ".join(row["detail"] for row in plan)
        assert "idx_conversation_messages_session" in detail, detail
        assert "SCAN conversation_messages" not in detail, detail  # no full scan

    def test_chat_session_delete_uses_index(self, db):
        """Reset-chat's per-session delete must use the chat_messages index."""
        plan = db.fetch_all(
            "EXPLAIN QUERY PLAN DELETE FROM chat_messages WHERE session_id = ?",
            ("sess_x",),
        )
        detail = " ".join(row["detail"] for row in plan)
        assert "idx_chat_messages_session" in detail, detail

    def test_session_trim_subquery_uses_index(self, db):
        """add_turn's trim (DELETE ... WHERE session_id = ? AND id NOT IN (...)) must index."""
        plan = db.fetch_all(
            "EXPLAIN QUERY PLAN DELETE FROM conversation_messages WHERE session_id = ? "
            "AND id NOT IN (SELECT id FROM conversation_messages WHERE session_id = ? "
            "ORDER BY id DESC LIMIT 20)",
            ("sess_a", "sess_a"),
        )
        detail = " ".join(row["detail"] for row in plan)
        assert "idx_conversation_messages_session" in detail, detail


# ---------------------------------------------------------------------------
# Connection pragmas
# ---------------------------------------------------------------------------


class TestPragmas:
    def test_wal_journal_mode(self, file_db):
        """WAL requires a file-backed DB; :memory: stays in 'memory' mode."""
        row = file_db.fetch_one("PRAGMA journal_mode")
        assert row["journal_mode"] == "wal"

    def test_synchronous_normal(self, file_db):
        """synchronous=NORMAL is the standard WAL pairing (no per-commit fsync)."""
        row = file_db.fetch_one("PRAGMA synchronous")
        assert row["synchronous"] == 1  # 0=off, 1=normal, 2=full

    def test_busy_timeout_set(self, db):
        # Column name for "PRAGMA busy_timeout" varies across sqlite versions;
        # there is exactly one value — read it positionally.
        row = db.fetch_one("PRAGMA busy_timeout")
        assert row is not None and list(row.values())[0] > 0

    def test_foreign_keys_on(self, db):
        row = db.fetch_one("PRAGMA foreign_keys")
        assert row["foreign_keys"] == 1


# ---------------------------------------------------------------------------
# transaction()
# ---------------------------------------------------------------------------


class TestTransaction:
    def test_commit_persists_all_statements(self, db):
        with db.transaction() as tx:
            tx.execute("INSERT INTO settings (key, value) VALUES (?, ?)", ("tx_k1", "v1"))
            tx.execute("INSERT INTO settings (key, value) VALUES (?, ?)", ("tx_k2", "v2"))
        assert db.fetch_one("SELECT value FROM settings WHERE key = 'tx_k1'")["value"] == "v1"
        assert db.fetch_one("SELECT value FROM settings WHERE key = 'tx_k2'")["value"] == "v2"

    def test_rollback_on_exception_persists_nothing(self, db):
        with pytest.raises(RuntimeError, match="boom"):
            with db.transaction() as tx:
                tx.execute("INSERT INTO settings (key, value) VALUES ('tx_r', 'v')")
                raise RuntimeError("boom")
        assert db.fetch_one("SELECT value FROM settings WHERE key = 'tx_r'") is None

    def test_reads_see_uncommitted_writes_within_transaction(self, db):
        """Reads through the transaction executor see its own uncommitted writes;
        db.fetch_one() inside a transaction would deadlock on the non-reentrant
        connection lock — that is exactly what tx.fetch_one exists for."""
        with db.transaction() as tx:
            tx.execute("INSERT INTO settings (key, value) VALUES ('tx_v', 'v')")
            row = tx.fetch_one("SELECT value FROM settings WHERE key = 'tx_v'")
            assert row["value"] == "v"
        # After commit, the normal read path sees it too.
        assert db.fetch_one("SELECT value FROM settings WHERE key = 'tx_v'")["value"] == "v"

    def test_transaction_isolated_from_outside_reads(self, file_db, tmp_path: Path):
        """An uncommitted transaction's writes are invisible to a second
        connection (WAL snapshot isolation for readers).

        NOTE: never call db.fetch_one() inside an open db.transaction() —
        the non-reentrant connection lock makes that a deadlock. Use a second
        DatabaseManager (as here) or the transaction's own tx.fetch_one().
        """
        file_db.execute("INSERT INTO settings (key, value) VALUES ('tx_out', 'before')")
        # Second connection simulates another reader (e.g. another threadpool request)
        reader = DatabaseManager(db_path=tmp_path / "test.db")
        try:
            _ = reader.connection
            with file_db.transaction() as tx:
                tx.execute("UPDATE settings SET value = 'during' WHERE key = 'tx_out'")
                assert (
                    reader.fetch_one("SELECT value FROM settings WHERE key = 'tx_out'")["value"]
                    == "before"
                )
            assert (
                reader.fetch_one("SELECT value FROM settings WHERE key = 'tx_out'")["value"]
                == "during"
            )
        finally:
            reader.close()

    def test_single_commit_for_batch_inserts(self, db):
        """execute_many-equivalent via transaction commits once."""
        with db.transaction() as tx:
            tx.executemany(
                "INSERT INTO command_history (command, action, success) VALUES (?, ?, ?)",
                [("cmd_i", "open", 1) for i in range(50)],
            )
        assert db.fetch_one("SELECT COUNT(*) AS n FROM command_history")["n"] == 50


# ---------------------------------------------------------------------------
# Thread safety
# ---------------------------------------------------------------------------


class TestThreadSafety:
    def test_concurrent_writes_from_threadpool_workers(self, db):
        """FastAPI runs sync endpoints in worker threads; writes must serialize."""
        threads = 8
        writes_per_thread = 25
        errors: list[Exception] = []

        def worker(tid: int):
            try:
                for i in range(writes_per_thread):
                    db.execute(
                        "INSERT INTO settings (key, value) VALUES (?, ?)",
                        (f"thr_{tid}_{i}", "x"),
                    )
            except Exception as e:  # pragma: no cover — surfaces real races
                errors.append(e)

        workers = [threading.Thread(target=worker, args=(t,)) for t in range(threads)]
        for w in workers:
            w.start()
        for w in workers:
            w.join()

        assert errors == []
        row = db.fetch_one("SELECT COUNT(*) AS n FROM settings WHERE key LIKE 'thr_%'")
        assert row["n"] == threads * writes_per_thread

    def test_cross_thread_connection_allowed(self, db):
        """check_same_thread=False: a worker thread may use the main connection."""
        caught: list[Exception] = []

        def worker():
            try:
                db.fetch_one("SELECT 1 AS one")
            except sqlite3.Error as e:  # pragma: no cover
                caught.append(e)

        t = threading.Thread(target=worker)
        t.start()
        t.join()
        assert caught == []


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])
