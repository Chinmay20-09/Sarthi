"""Tests for chat transcript persistence (\"memory of one chat\").

The chat window keeps one persistent conversation per session (survives
reloads and restarts); \"reset chat\" wipes the transcript AND the Hermes
session context, while /remember facts (knowledge_memory) survive the
reset untouched in the database.
"""

import pytest
from fastapi.testclient import TestClient

from api import app
from database.manager import DatabaseManager
from database.models import CREATE_CONVERSATION_MESSAGES
from knowledge.memory import KnowledgeMemory


@pytest.fixture
def chat_env(monkeypatch, tmp_path):
    """Isolate the API's database + memory behind a temp SQLite file."""
    db = DatabaseManager(tmp_path / "chat.db")
    monkeypatch.setattr("database.manager.get_database", lambda: db)
    memory = KnowledgeMemory()
    monkeypatch.setattr("knowledge.memory.get_memory", lambda: memory)
    return TestClient(app), db, memory


def test_chat_round_trip_persists_messages_in_order(chat_env):
    client, _, _ = chat_env
    client.post(
        "/chat",
        json={"session_id": "sess_a", "role": "user", "content": {"text": "hello"}},
    )
    client.post(
        "/chat",
        json={
            "session_id": "sess_a",
            "role": "assistant",
            "content": {"text": "hi there", "success": True},
        },
    )

    resp = client.get("/chat", params={"session_id": "sess_a"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["count"] == 2
    assert data["messages"][0] == {"id": 1, "role": "user", "content": {"text": "hello"}}
    assert data["messages"][1]["role"] == "assistant"
    assert data["messages"][1]["content"]["text"] == "hi there"


def test_chat_empty_for_new_session(chat_env):
    client, _, _ = chat_env
    data = client.get("/chat", params={"session_id": "sess_new"}).json()
    assert data["success"] is True
    assert data["count"] == 0
    assert data["messages"] == []


def test_chat_sessions_are_independent(chat_env):
    client, _, _ = chat_env
    client.post("/chat", json={"session_id": "sess_a", "role": "user", "content": {"text": "a"}})
    client.post("/chat", json={"session_id": "sess_b", "role": "user", "content": {"text": "b"}})

    data_a = client.get("/chat", params={"session_id": "sess_a"}).json()
    data_b = client.get("/chat", params={"session_id": "sess_b"}).json()
    assert data_a["count"] == 1
    assert data_b["count"] == 1
    assert data_a["messages"][0]["content"]["text"] == "a"
    assert data_b["messages"][0]["content"]["text"] == "b"


def test_reset_clears_chat_and_hermes_context_but_keeps_facts(chat_env):
    client, db, memory = chat_env
    # Chat transcript rows (what the UI renders)
    client.post("/chat", json={"session_id": "sess_r", "role": "user", "content": {"text": "hi"}})
    client.post(
        "/chat", json={"session_id": "sess_r", "role": "assistant", "content": {"text": "yo"}}
    )
    # Hermes session context — the AI's own conversation turns
    db.create_table(CREATE_CONVERSATION_MESSAGES)
    db.execute(
        "INSERT INTO conversation_messages (session_id, role, content, created_at) "
        "VALUES ('sess_r', 'user', 'hi', datetime('now'))"
    )
    # A /remember fact — must survive the reset
    assert memory.remember_long("user_name", "Alice") is True

    resp = client.delete("/chat", params={"session_id": "sess_r"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["remembered_facts"] == 1

    # Transcript gone, Hermes context gone…
    assert client.get("/chat", params={"session_id": "sess_r"}).json()["count"] == 0
    assert db.fetch_all("SELECT * FROM conversation_messages WHERE session_id = 'sess_r'") == []
    # …but the /remember fact is still in the database.
    assert memory.recall_long("user_name") == "Alice"


def test_reset_only_touches_requested_session(chat_env):
    client, _, _ = chat_env
    client.post(
        "/chat", json={"session_id": "sess_keep", "role": "user", "content": {"text": "keep me"}}
    )
    client.post(
        "/chat", json={"session_id": "sess_drop", "role": "user", "content": {"text": "drop me"}}
    )

    client.delete("/chat", params={"session_id": "sess_drop"})

    keep = client.get("/chat", params={"session_id": "sess_keep"}).json()
    drop = client.get("/chat", params={"session_id": "sess_drop"}).json()
    assert keep["count"] == 1
    assert drop["count"] == 0
