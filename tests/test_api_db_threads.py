"""Regression tests for SQLite usage through FastAPI's threadpool.

FastAPI/uvicorn runs sync endpoints in threadpool worker threads, while the
DatabaseManager connection is created once at import time (main thread).
Without ``check_same_thread=False`` in database/manager.py, every DB call from
an endpoint raised ``sqlite3.ProgrammingError`` — /settings returned 500 and
DB-touching skills silently degraded to ``no_handler``.

These tests hit the real endpoints via TestClient (which runs sync endpoints
in worker threads, reproducing the cross-thread scenario) and assert the
behavior that used to break.
"""

import uuid

from fastapi.testclient import TestClient

from api import app
from database.manager import get_database

client = TestClient(app)


class TestSettingsThroughThreadpool:
    """/settings must work when called from a threadpool worker."""

    def test_read_setting(self):
        """GET /settings/{key} must return 200 (used to be a 500)."""
        response = client.get("/settings/github_username")
        assert response.status_code == 200
        data = response.json()
        assert data["key"] == "github_username"
        assert "value" in data  # None is fine; a DB error is not

    def test_write_and_read_setting(self):
        """POST then GET /settings must persist (write path touches the DB)."""
        key = f"test_thread_{uuid.uuid4().hex[:8]}"
        value = "thread-safe"
        try:
            write = client.post(
                "/settings",
                json={"key": key, "value": value},
            )
            assert write.status_code == 200
            assert write.json()["success"] is True

            read = client.get(f"/settings/{key}")
            assert read.status_code == 200
            assert read.json()["value"] == value
        finally:
            # Never leave test rows in the real database
            get_database().execute("DELETE FROM settings WHERE key = ?", (key,))


class TestCommandThroughThreadpool:
    """A /command that a DB-touching skill owns must not silently fail."""

    def test_github_username_query_not_no_handler(self):
        """user_config reads the settings DB; a DB failure used to degrade
        this to no_handler instead of the skill's real answer."""
        response = client.post(
            "/command",
            json={"text": "what is my github username"},
        )
        assert response.status_code == 200
        data = response.json()

        # Regression: with a broken DB connection this came back as
        # no_handler. With the fix it is needs_input (prompt card) or
        # executed (username already saved) — never no_handler.
        assert data["status"] != "no_handler", data
        assert data["success"] or (data.get("result") or {}).get("visual"), data


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])
