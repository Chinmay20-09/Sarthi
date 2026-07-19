"""Tests for database/manager.py.

Tests DatabaseManager CRUD operations, connection management,
table creation, and the singleton get_database() factory.
All tests use in-memory SQLite to avoid touching disk.
"""

from pathlib import Path

import pytest

from database.manager import DatabaseManager, get_database
from database.models import ALL_TABLES


@pytest.fixture
def db():
    """Create an in-memory DatabaseManager for testing."""
    manager = DatabaseManager(db_path=Path(":memory:"))
    _ = manager.connection  # trigger lazy connection
    yield manager
    manager.close()


# ---------------------------------------------------------------------------
# Connection Management
# ---------------------------------------------------------------------------


class TestConnection:
    def test_connection_is_lazy(self):
        """Connection should not be established until first use."""
        manager = DatabaseManager(db_path=Path(":memory:"))
        assert manager.is_connected is False
        manager.close()

    def test_connection_established_on_use(self, db):
        """Connection should be established on first query."""
        assert db.is_connected is True

    def test_close_then_reconnect(self, db):
        """Closing and reusing should reconnect."""
        db.close()
        assert db.is_connected is False
        # Using connection property should reconnect
        conn = db.connection
        assert conn is not None

    def test_close_releases_connection(self, db):
        """Close should set connection to None."""
        db.close()
        assert db._connection is None


# ---------------------------------------------------------------------------
# Table Creation
# ---------------------------------------------------------------------------


class TestTableCreation:
    def test_create_table(self, db):
        """create_table should create a table."""
        db.create_table("CREATE TABLE IF NOT EXISTS test_table (id INTEGER PRIMARY KEY, name TEXT)")
        assert db.table_exists("test_table") is True

    def test_create_table_idempotent(self, db):
        """Creating the same table twice should not fail."""
        sql = "CREATE TABLE IF NOT EXISTS test_table (id INTEGER PRIMARY KEY)"
        db.create_table(sql)
        db.create_table(sql)  # Second time — should be fine

    def test_table_not_exists(self, db):
        """table_exists should return False for non-existent tables."""
        assert db.table_exists("non_existent_table") is False

    def test_create_table_with_models(self, db):
        """All known table schemas should be creatable."""
        for name, sql in ALL_TABLES.items():
            db.create_table(sql)
            assert db.table_exists(name), f"Table '{name}' was not created"


# ---------------------------------------------------------------------------
# CRUD Operations
# ---------------------------------------------------------------------------


class TestInsertAndFetch:
    def test_insert_and_fetch_one(self, db):
        """Insert a row and fetch it back."""
        db.create_table(
            "CREATE TABLE IF NOT EXISTS test_items (id INTEGER PRIMARY KEY, name TEXT, value INTEGER)"
        )
        db.execute(
            "INSERT INTO test_items (name, value) VALUES (?, ?)",
            ("item1", 42),
        )
        row = db.fetch_one("SELECT * FROM test_items WHERE name = ?", ("item1",))
        assert row is not None
        assert row["name"] == "item1"
        assert row["value"] == 42

    def test_fetch_one_no_results(self, db):
        """fetch_one with no match should return None."""
        db.create_table("CREATE TABLE IF NOT EXISTS test_empty (id INTEGER PRIMARY KEY, name TEXT)")
        row = db.fetch_one("SELECT * FROM test_empty WHERE name = ?", ("nothing",))
        assert row is None

    def test_fetch_all(self, db):
        """Insert multiple rows and fetch them all."""
        db.create_table(
            "CREATE TABLE IF NOT EXISTS test_multi (id INTEGER PRIMARY KEY, label TEXT)"
        )
        db.execute("INSERT INTO test_multi (label) VALUES ('a')")
        db.execute("INSERT INTO test_multi (label) VALUES ('b')")
        db.execute("INSERT INTO test_multi (label) VALUES ('c')")
        rows = db.fetch_all("SELECT * FROM test_multi ORDER BY id")
        assert len(rows) == 3
        assert rows[0]["label"] == "a"
        assert rows[2]["label"] == "c"

    def test_fetch_all_empty(self, db):
        """fetch_all on an empty table should return empty list."""
        db.create_table("CREATE TABLE IF NOT EXISTS test_empty2 (id INTEGER PRIMARY KEY)")
        rows = db.fetch_all("SELECT * FROM test_empty2")
        assert rows == []


class TestUpdateAndDelete:
    def test_update(self, db):
        """Update a row and verify the change."""
        db.create_table(
            "CREATE TABLE IF NOT EXISTS test_updates (id INTEGER PRIMARY KEY, name TEXT, value INTEGER)"
        )
        db.execute("INSERT INTO test_updates (name, value) VALUES ('old', 0)")
        db.execute("UPDATE test_updates SET value = 99 WHERE name = 'old'")
        row = db.fetch_one("SELECT * FROM test_updates WHERE name = 'old'")
        assert row["value"] == 99

    def test_delete(self, db):
        """Delete a row and verify it's gone."""
        db.create_table(
            "CREATE TABLE IF NOT EXISTS test_deletes (id INTEGER PRIMARY KEY, name TEXT)"
        )
        db.execute("INSERT INTO test_deletes (name) VALUES ('temp')")
        db.execute("DELETE FROM test_deletes WHERE name = 'temp'")
        row = db.fetch_one("SELECT * FROM test_deletes WHERE name = 'temp'")
        assert row is None


class TestExecuteMany:
    def test_execute_many(self, db):
        """Insert multiple rows with executemany."""
        db.create_table("CREATE TABLE IF NOT EXISTS test_many (id INTEGER PRIMARY KEY, val TEXT)")
        params = [("a",), ("b",), ("c",)]
        db.execute_many("INSERT INTO test_many (val) VALUES (?)", params)
        rows = db.fetch_all("SELECT * FROM test_many ORDER BY id")
        assert len(rows) == 3


# ---------------------------------------------------------------------------
# Row Factory
# ---------------------------------------------------------------------------


class TestRowFactory:
    def test_rows_returned_as_dicts(self, db):
        """Rows should be dictionaries, not tuples."""
        db.create_table("CREATE TABLE IF NOT EXISTS test_dicts (id INTEGER PRIMARY KEY, name TEXT)")
        db.execute("INSERT INTO test_dicts (name) VALUES ('test')")
        row = db.fetch_one("SELECT * FROM test_dicts")
        assert isinstance(row, dict)
        assert "id" in row
        assert "name" in row


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------


class TestGetDatabase:
    def test_get_database_returns_instance(self):
        """get_database() should return a DatabaseManager."""
        db = get_database()
        assert isinstance(db, DatabaseManager)
        db.close()

    def test_get_database_is_singleton(self):
        """get_database() should return the same instance on repeat calls."""
        db1 = get_database()
        db2 = get_database()
        assert db1 is db2
        db1.close()
