"""Tests for the Projects feature (Knowledge tab).

Covers the /projects CRUD API (create, list, get, update, delete),
validation (required name, URL shape, duplicates, whitespace trimming),
persistence across fresh DatabaseManager instances, and the Hermes
retriever's projects source.

Database access is isolated behind a tmp SQLite file by monkeypatching
``database.manager.get_database`` — the endpoints import it lazily inside
each request, so the patch is picked up per-request.
"""

import pytest
from api import app
from database.manager import DatabaseManager
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """TestClient against an isolated projects database."""
    db = DatabaseManager(tmp_path / "projects_test.db")
    monkeypatch.setattr("database.manager.get_database", lambda: db)
    return TestClient(app), db


UNIQUE = {"n": 0}


def _unique_name(base: str = "Project") -> str:
    UNIQUE["n"] += 1
    return f"{base} {UNIQUE['n']}"


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


class TestProjectsCRUD:
    def test_create_project(self, client):
        c, db = client
        res = c.post(
            "/projects",
            json={
                "name": "Sarthi",
                "github_url": "https://github.com/Chinmay20-09/Sarthi",
                "terminal_path": "C:/Sarthi",
            },
        )
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True
        assert data["project"]["name"] == "Sarthi"
        assert data["project"]["github_url"] == "https://github.com/Chinmay20-09/Sarthi"
        assert data["project"]["terminal_path"] == "C:/Sarthi"

    def test_get_projects_returns_stored_projects(self, client):
        c, _ = client
        c.post("/projects", json={"name": _unique_name("Alpha")})
        c.post("/projects", json={"name": _unique_name("Beta")})
        res = c.get("/projects")
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True
        names = [p["name"] for p in data["projects"]]
        assert any(n.startswith("Alpha") for n in names)
        assert any(n.startswith("Beta") for n in names)
        assert data["count"] == len(data["projects"])

    def test_get_individual_project(self, client):
        c, _ = client
        created = c.post("/projects", json={"name": _unique_name("Solo")}).json()
        pid = created["project"]["id"]
        res = c.get(f"/projects/{pid}")
        assert res.status_code == 200
        assert res.json()["project"]["id"] == pid

    def test_get_missing_project(self, client):
        c, _ = client
        res = c.get("/projects/999999")
        assert res.status_code == 200
        assert res.json()["success"] is False
        assert "not found" in res.json()["error"].lower()

    def test_update_project(self, client):
        c, _ = client
        created = c.post(
            "/projects",
            json={"name": _unique_name("EditMe"), "terminal_path": "C:/old"},
        ).json()
        pid = created["project"]["id"]
        res = c.put(
            f"/projects/{pid}",
            json={"terminal_path": "C:/new/path"},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True
        assert data["project"]["terminal_path"] == "C:/new/path"
        # Untouched field survives a partial update.
        assert data["project"]["name"] == created["project"]["name"]

    def test_update_missing_project(self, client):
        c, _ = client
        res = c.put("/projects/999999", json={"name": "Ghost"})
        assert res.status_code == 200
        assert res.json()["success"] is False

    def test_delete_project(self, client):
        c, db = client
        created = c.post("/projects", json={"name": _unique_name("Del")}).json()
        pid = created["project"]["id"]
        res = c.delete(f"/projects/{pid}")
        assert res.status_code == 200
        assert res.json()["success"] is True
        # Gone from the API...
        assert c.get(f"/projects/{pid}").json()["success"] is False
        # ...and from the database.
        assert (
            db.fetch_one("SELECT * FROM projects WHERE id = ?", (pid,)) is None
        )


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


class TestProjectsValidation:
    def test_name_required(self, client):
        c, _ = client
        res = c.post("/projects", json={"name": "   "})
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is False
        assert "name is required" in data["error"].lower()

    def test_fields_are_trimmed(self, client):
        c, _ = client
        res = c.post(
            "/projects",
            json={
                "name": "  Trimmed  ",
                "github_url": "  https://github.com/u/r  ",
                "terminal_path": "  C:/path  ",
            },
        )
        data = res.json()
        assert data["success"] is True
        assert data["project"]["name"] == "Trimmed"
        assert data["project"]["github_url"] == "https://github.com/u/r"
        assert data["project"]["terminal_path"] == "C:/path"

    def test_github_url_optional(self, client):
        c, _ = client
        res = c.post("/projects", json={"name": _unique_name("NoUrl")})
        assert res.json()["success"] is True

    def test_malformed_url_rejected(self, client):
        c, _ = client
        for bad in ("github.com/u/r", "ftp://x", "//nope"):
            res = c.post("/projects", json={"name": _unique_name("Bad"), "github_url": bad})
            data = res.json()
            assert data["success"] is False, bad
            assert "must start with" in data["error"].lower()

    def test_valid_schemes_accepted(self, client):
        c, _ = client
        for url in (
            "https://github.com/u/r",
            "http://github.com/u/r",
            "git@github.com:u/r.git",
            "ssh://git@github.com/u/r.git",
        ):
            res = c.post("/projects", json={"name": _unique_name("Ok"), "github_url": url})
            assert res.json()["success"] is True, url

    def test_duplicate_name_rejected(self, client):
        c, _ = client
        name = _unique_name("Dup")
        assert c.post("/projects", json={"name": name}).json()["success"] is True
        res = c.post("/projects", json={"name": name})
        data = res.json()
        assert data["success"] is False
        assert "already exists" in data["error"].lower()

    def test_duplicate_name_case_insensitive(self, client):
        c, _ = client
        name = _unique_name("Case")
        assert c.post("/projects", json={"name": name}).json()["success"] is True
        res = c.post("/projects", json={"name": name.lower()})
        assert res.json()["success"] is False

    def test_update_can_keep_own_name(self, client):
        c, _ = client
        created = c.post("/projects", json={"name": _unique_name("Keep")}).json()
        pid = created["project"]["id"]
        res = c.put(f"/projects/{pid}", json={"name": created["project"]["name"]})
        assert res.json()["success"] is True

    def test_update_to_other_project_name_rejected(self, client):
        c, _ = client
        first = c.post("/projects", json={"name": _unique_name("One")}).json()
        second = c.post("/projects", json={"name": _unique_name("Two")}).json()
        res = c.put(
            f"/projects/{second['project']['id']}",
            json={"name": first["project"]["name"]},
        )
        assert res.json()["success"] is False
        assert "already exists" in res.json()["error"].lower()


# ---------------------------------------------------------------------------
# Persistence + Hermes compatibility
# ---------------------------------------------------------------------------


class TestProjectsPersistenceAndRetrieval:
    def test_projects_persist_across_database_instances(self, client, tmp_path, monkeypatch):
        c, _ = client
        c.post(
            "/projects",
            json={"name": "PersistPy", "github_url": "https://github.com/u/p", "terminal_path": "C:/p"},
        )
        # A fresh DatabaseManager over the same file = what a restart sees.
        monkeypatch.setattr(
            "database.manager.get_database",
            lambda: DatabaseManager(tmp_path / "projects_test.db"),
        )
        rows = DatabaseManager(tmp_path / "projects_test.db").fetch_all(
            "SELECT name, github_url, terminal_path FROM projects WHERE name = 'PersistPy'"
        )
        assert rows == [
            {
                "name": "PersistPy",
                "github_url": "https://github.com/u/p",
                "terminal_path": "C:/p",
            }
        ]

    def test_retriever_surfaces_matching_project(self, client, tmp_path):
        c, db = client
        db.execute(
            "INSERT INTO projects (name, github_url, terminal_path, created_at, updated_at) "
            "VALUES ('Sarthi', 'https://github.com/Chinmay20-09/Sarthi', 'C:/Sarthi', "
            "datetime('now'), datetime('now'))"
        )
        from hermes.retriever import Retriever

        context = Retriever(db=db).retrieve("solve Sarthi backend latency")
        assert "Project: Sarthi" in context.text
        assert "https://github.com/Chinmay20-09/Sarthi" in context.text
        assert "Terminal: C:/Sarthi" in context.text
        assert any(s.name == "projects" for s in context.sources)

    def test_retriever_works_without_projects_table(self, tmp_path):
        """Pre-migration DB (no projects table) must degrade silently."""
        import sqlite3

        conn = sqlite3.connect(tmp_path / "legacy.db")
        conn.execute("CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT)")
        conn.commit()
        conn.close()

        from database.manager import DatabaseManager
        from hermes.retriever import Retriever

        legacy_db = DatabaseManager(tmp_path / "legacy.db")
        # The canonical bootstrap creates the table; drop it to simulate a
        # legacy database, then verify retrieval still works.
        legacy_db.execute("DROP TABLE projects")
        context = Retriever(db=legacy_db).retrieve("work on Sarthi")
        assert "Project: Sarthi" not in context.text
        assert any(s.name == "projects" and s.count == 0 for s in context.sources)

    def test_retriever_lists_project_without_keyword_match(self, client):
        """Projects are few — unmatched ones still appear (up to the cap)."""
        c, db = client
        db.execute(
            "INSERT INTO projects (name, github_url, terminal_path, created_at, updated_at) "
            "VALUES ('TotallyUnrelated', '', '', datetime('now'), datetime('now'))"
        )
        from hermes.retriever import Retriever

        context = Retriever(db=db).retrieve("hello there")
        assert "TotallyUnrelated" in context.text
