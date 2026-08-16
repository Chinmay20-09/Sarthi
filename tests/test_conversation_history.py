"""Tests for Hermes conversation history (session memory).

Hermes remembers earlier turns in a session: the ConversationStore keeps
per-session turns, providers inject them between the system message and the
current prompt, and both hermes.service.chat and POST /hermes/chat record
each exchange.
"""

import json

import httpx
import pytest
from fastapi.testclient import TestClient

from database.manager import DatabaseManager
from hermes.config.settings import HermesConfig
from hermes.conversation import ConversationStore, DEFAULT_SESSION, get_conversation_store
from hermes.models import Task
from hermes.orchestrator import HermesOrchestrator
from hermes.providers.base import AIProvider, ProviderResponse
from hermes.providers.local_provider import LocalHermesProvider
from hermes.providers.manager import ProviderManager
from hermes.tool_registry import ToolRegistry


# ----------------------------------------------------------------------
# ConversationStore
# ----------------------------------------------------------------------


def test_store_returns_empty_history_for_new_session():
    store = ConversationStore()
    assert store.get_history("sess_x") == []


def test_store_appends_turns_in_order():
    store = ConversationStore()
    store.add_turn("sess_x", "user", "hi")
    store.add_turn("sess_x", "assistant", "hello!")

    history = store.get_history("sess_x")
    assert history == [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello!"},
    ]


def test_store_caps_history_per_session():
    store = ConversationStore(max_messages=4)
    for i in range(6):
        store.add_turn("sess_x", "user", f"msg {i}")

    history = store.get_history("sess_x")
    assert len(history) == 4
    # Oldest messages dropped, newest kept
    assert history[0]["content"] == "msg 2"
    assert history[-1]["content"] == "msg 5"


def test_store_sessions_are_independent():
    store = ConversationStore()
    store.add_turn("sess_a", "user", "a")
    store.add_turn("sess_b", "user", "b")

    assert store.get_history("sess_a") == [{"role": "user", "content": "a"}]
    assert store.get_history("sess_b") == [{"role": "user", "content": "b"}]


def test_store_clear_forgets_session():
    store = ConversationStore()
    store.add_turn("sess_x", "user", "hi")
    store.clear("sess_x")
    assert store.get_history("sess_x") == []


def test_store_get_returns_copy():
    """Callers get a copy; mutating it must not affect the store."""
    store = ConversationStore()
    store.add_turn("sess_x", "user", "hi")
    history = store.get_history("sess_x")
    history.append({"role": "assistant", "content": "injected"})
    assert store.get_history("sess_x") == [{"role": "user", "content": "hi"}]


# ----------------------------------------------------------------------
# Persistence: a db-backed store survives restarts (new instances)
# ----------------------------------------------------------------------


def test_store_persists_turns_across_instances(tmp_path):
    """Turns written by one store are visible to a fresh store on the same db."""
    db_path = tmp_path / "conversations.db"
    first = ConversationStore(db=DatabaseManager(db_path))
    first.add_turn("sess_p", "user", "hello")
    first.add_turn("sess_p", "assistant", "hi there")

    # A brand-new store over the same database = what a restart sees.
    second = ConversationStore(db=DatabaseManager(db_path))
    assert second.get_history("sess_p") == [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi there"},
    ]


def test_store_persistent_cap_trims_oldest(tmp_path):
    """The per-session cap applies to persisted turns too."""
    store = ConversationStore(
        db=DatabaseManager(tmp_path / "conversations.db"), max_messages=4
    )
    for i in range(6):
        store.add_turn("sess_c", "user", f"msg {i}")

    history = store.get_history("sess_c")
    assert len(history) == 4
    assert history[0]["content"] == "msg 2"
    assert history[-1]["content"] == "msg 5"


def test_store_persistent_clear_forgets_session(tmp_path):
    """clear() removes persisted turns, not just the in-memory view."""
    db_path = tmp_path / "conversations.db"
    store = ConversationStore(db=DatabaseManager(db_path))
    store.add_turn("sess_cl", "user", "hi")
    store.clear("sess_cl")

    assert store.get_history("sess_cl") == []
    # A fresh store must not see the cleared turns either.
    fresh = ConversationStore(db=DatabaseManager(db_path))
    assert fresh.get_history("sess_cl") == []


def test_persistent_store_sessions_are_independent(tmp_path):
    """Sessions do not leak into each other on disk."""
    db_path = tmp_path / "conversations.db"
    store = ConversationStore(db=DatabaseManager(db_path))
    store.add_turn("sess_a", "user", "a")
    store.add_turn("sess_b", "user", "b")

    fresh = ConversationStore(db=DatabaseManager(db_path))
    assert fresh.get_history("sess_a") == [{"role": "user", "content": "a"}]
    assert fresh.get_history("sess_b") == [{"role": "user", "content": "b"}]


def test_get_conversation_store_singleton_is_persistent(monkeypatch, tmp_path):
    """The app's singleton store is wired to the database, not memory."""
    import hermes.conversation as conv

    db = DatabaseManager(tmp_path / "conversations.db")
    monkeypatch.setattr(conv, "get_database", lambda: db)
    monkeypatch.setattr(conv, "_store", None)

    store = get_conversation_store()

    assert store._db is db
    # And it actually writes through to the db.
    store.add_turn("sess_s", "user", "persisted?")
    assert DatabaseManager(tmp_path / "conversations.db").fetch_one(
        "SELECT content FROM conversation_messages WHERE session_id = ?", ("sess_s",)
    )["content"] == "persisted?"


# ----------------------------------------------------------------------
# Provider: history injected between system and current prompt
# ----------------------------------------------------------------------


def test_local_provider_injects_history_between_system_and_prompt(monkeypatch):
    config = HermesConfig(model="m", local_model="hermes3:8b")
    provider = LocalHermesProvider(config)

    captured = {}

    def fake_post(url, **kwargs):
        captured["json"] = kwargs["json"]
        return type("R", (), {"raise_for_status": lambda self: None, "json": lambda self: {"message": {"content": "ok"}}})()

    monkeypatch.setattr("hermes.providers.local_provider.httpx.post", fake_post)

    task = Task(
        prompt="Who won?",
        instructions="Be helpful.",
        history=[
            {"role": "user", "content": "Who are you?"},
            {"role": "assistant", "content": "I am Hermes."},
        ],
    )
    response = provider.generate(task)

    assert response.success is True
    messages = captured["json"]["messages"]
    assert messages == [
        {"role": "system", "content": "Be helpful."},
        {"role": "user", "content": "Who are you?"},
        {"role": "assistant", "content": "I am Hermes."},
        {"role": "user", "content": "Who won?"},
    ]


def test_local_provider_skips_malformed_history_turns(monkeypatch):
    config = HermesConfig(model="m", local_model="hermes3:8b")
    provider = LocalHermesProvider(config)

    captured = {}

    def fake_post(url, **kwargs):
        captured["json"] = kwargs["json"]
        return type("R", (), {"raise_for_status": lambda self: None, "json": lambda self: {"message": {"content": "ok"}}})()

    monkeypatch.setattr("hermes.providers.local_provider.httpx.post", fake_post)

    provider.generate(
        Task(
            prompt="hi",
            history=[
                {"role": "system", "content": "skip me"},
                {"role": "user", "content": ""},  # empty content skipped
                "not-a-dict",  # ignored
                {"role": "user", "content": "hello"},
            ],
        )
    )

    messages = captured["json"]["messages"]
    assert messages == [
        # only the valid history turn is injected
        {"role": "user", "content": "hello"},
        {"role": "user", "content": "hi"},
    ]


# ----------------------------------------------------------------------
# service.chat: session memory round-trip
# ----------------------------------------------------------------------


class FakeChatProvider(AIProvider):
    """Deterministic provider that reports what it saw."""

    name = "Fake"

    def generate(self, task: Task) -> ProviderResponse:
        history_note = ", ".join(f"{t['role']}:{t['content']}" for t in (task.history or []))
        return ProviderResponse(
            success=True,
            provider=self.name,
            model="m",
            text=f"reply[{history_note}]",
        )


def _fake_orchestrator():
    manager = ProviderManager()
    manager.initialize(FakeChatProvider())
    return HermesOrchestrator(manager, tool_registry=ToolRegistry(), sandbox=None)


def test_service_chat_remembers_session(monkeypatch):
    """chat() attaches prior turns and records the new exchange."""
    from hermes import service

    orchestrator = _fake_orchestrator()
    monkeypatch.setattr(service, "get_orchestrator", lambda: orchestrator)
    store = ConversationStore()
    monkeypatch.setattr("hermes.service.get_conversation_store", lambda: store)

    first = service.chat("Who are you?", session_id="sess_mem")
    assert first.text == "reply[]"

    second = service.chat("What did I ask?", session_id="sess_mem")

    # Second call saw the first exchange as history
    assert "user:Who are you?" in second.text
    assert "assistant:reply[]" in second.text

    history = store.get_history("sess_mem")
    assert [t["role"] for t in history] == ["user", "assistant", "user", "assistant"]


def test_service_chat_default_session(monkeypatch):
    """Without a session_id, a shared default session still remembers."""
    from hermes import service

    orchestrator = _fake_orchestrator()
    monkeypatch.setattr(service, "get_orchestrator", lambda: orchestrator)
    store = ConversationStore()
    monkeypatch.setattr("hermes.service.get_conversation_store", lambda: store)

    service.chat("hello", session_id=None)
    service.chat("hello again", session_id=None)

    assert len(store.get_history(DEFAULT_SESSION)) == 4


# ----------------------------------------------------------------------
# API: POST /hermes/chat session flow
# ----------------------------------------------------------------------


def test_hermes_chat_echoes_and_uses_session_id():
    """POST /hermes/chat pins a session and records turns in it."""
    from unittest.mock import MagicMock, patch

    from api import app
    from hermes.providers.base import ProviderResponse as PR

    client = TestClient(app)
    store = ConversationStore()
    mock_response = PR(success=True, provider="Fake", model="m", text="Hello!")

    with patch("hermes.routes._orchestrator", None), \
         patch("hermes.routes._get_orchestrator") as mock_get, \
         patch("hermes.routes.get_conversation_store", return_value=store):
        mock_orch = MagicMock()
        mock_orch.process.return_value = mock_response
        mock_get.return_value = mock_orch

        resp = client.post("/hermes/chat", json={"message": "Hi", "session_id": "sess_api"})

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["session_id"] == "sess_api"

    history = store.get_history("sess_api")
    assert history == [
        {"role": "user", "content": "Hi"},
        {"role": "assistant", "content": "Hello!"},
    ]


def test_hermes_chat_default_session_when_omitted():
    """Omitting session_id falls back to the shared default session."""
    from unittest.mock import MagicMock, patch

    from api import app
    from hermes.providers.base import ProviderResponse as PR

    client = TestClient(app)
    store = ConversationStore()
    mock_response = PR(success=True, provider="Fake", model="m", text="Hello!")

    with patch("hermes.routes._orchestrator", None), \
         patch("hermes.routes._get_orchestrator") as mock_get, \
         patch("hermes.routes.get_conversation_store", return_value=store):
        mock_orch = MagicMock()
        mock_orch.process.return_value = mock_response
        mock_get.return_value = mock_orch

        resp = client.post("/hermes/chat", json={"message": "Hi"})

    assert resp.status_code == 200
    assert resp.json()["session_id"] == DEFAULT_SESSION
    assert len(store.get_history(DEFAULT_SESSION)) == 2


# ----------------------------------------------------------------------
# ToolPlanner preserves history through decision/follow-up tasks
# ----------------------------------------------------------------------


def test_tool_planner_preserves_history_in_decision_task():
    from hermes.tool_planner import ToolPlanner

    captured = {}

    def fake_generate(task):
        captured["history"] = task.history
        return ProviderResponse(
            success=True, provider="Fake", model="m",
            text='{"tool_call": {"tool": "x", "arguments": {}}}',
        )

    registry = ToolRegistry()
    planner = ToolPlanner(registry, fake_generate)
    planner.run(Task(prompt="do it", history=[{"role": "user", "content": "earlier"}]))

    assert captured["history"] == [{"role": "user", "content": "earlier"}]
