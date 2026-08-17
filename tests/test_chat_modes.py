"""Tests for chat modes (conversation / default).

Conversation mode ("talk mode") makes Sarthi purely conversational: the brain
pipeline is never invoked, so no task or tool can execute, and typed "/exit"
returns to default mode where commands run normally.
"""

import pytest
from fastapi.testclient import TestClient

from api import app
from brain.modes import CONVERSATION_MODE, DEFAULT_MODE, detect_mode_command, get_mode, set_mode
from hermes.providers.base import ProviderResponse


@pytest.fixture(autouse=True)
def reset_mode():
    """Every test starts (and ends) in default mode."""
    set_mode(DEFAULT_MODE)
    yield
    set_mode(DEFAULT_MODE)


@pytest.fixture
def client():
    return TestClient(app)


def _brain_never_runs(text):
    raise AssertionError("brain pipeline must not run in conversation mode")


# ----------------------------------------------------------------------
# Phrase detection
# ----------------------------------------------------------------------


def test_detect_mode_command_phrases():
    assert detect_mode_command("conversation mode") == CONVERSATION_MODE
    assert detect_mode_command("talk mode") == CONVERSATION_MODE
    assert detect_mode_command("Chat Mode") == CONVERSATION_MODE
    assert detect_mode_command("switch to conversation mode") == CONVERSATION_MODE
    assert detect_mode_command("/exit") == DEFAULT_MODE
    assert detect_mode_command("/exit please") == DEFAULT_MODE
    assert detect_mode_command("exit mode") == DEFAULT_MODE
    assert detect_mode_command("open chrome") is None
    assert detect_mode_command("") is None
    assert detect_mode_command(None) is None


# ----------------------------------------------------------------------
# API: mode endpoints
# ----------------------------------------------------------------------


def test_mode_endpoints_round_trip(client):
    assert client.get("/mode").json()["mode"] == DEFAULT_MODE

    resp = client.post("/mode", json={"mode": "conversation"})
    assert resp.status_code == 200
    assert resp.json()["mode"] == CONVERSATION_MODE
    assert client.get("/mode").json()["mode"] == CONVERSATION_MODE

    # Unknown mode falls back to default
    resp = client.post("/mode", json={"mode": "garbage"})
    assert resp.json()["mode"] == DEFAULT_MODE


# ----------------------------------------------------------------------
# Switching modes through /command
# ----------------------------------------------------------------------


def test_command_conversation_mode_switches(client, monkeypatch):
    monkeypatch.setattr("api.engine.process", _brain_never_runs)
    resp = client.post("/command", json={"text": "conversation mode"})

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["mode"] == CONVERSATION_MODE
    assert data["action"] == "mode"
    assert get_mode() == CONVERSATION_MODE


def test_conversation_mode_does_not_execute_tasks(client, monkeypatch):
    """Even imperative commands ('open chrome') are answered conversationally."""
    monkeypatch.setattr("api.engine.process", _brain_never_runs)

    captured = {}

    def fake_chat(message, session_id=None):
        captured["message"] = message
        captured["session_id"] = session_id
        return ProviderResponse(
            success=True, provider="Fake", model="m", text="Sure, let's just chat!"
        )

    monkeypatch.setattr("hermes.service.chat", fake_chat)

    client.post("/command", json={"text": "talk mode", "session_id": "sess_mode"})

    resp = client.post("/command", json={"text": "open chrome", "session_id": "sess_mode"})
    data = resp.json()
    assert data["success"] is True
    assert data["action"] == "conversation"
    assert data["text"] == "Sure, let's just chat!"
    assert data["source"] == "nlp"
    assert data["mode"] == CONVERSATION_MODE
    # The conversation session flows through so Hermes remembers earlier turns
    assert captured["message"] == "open chrome"
    assert captured["session_id"] == "sess_mode"
    assert get_mode() == CONVERSATION_MODE


def test_exit_returns_to_default(client, monkeypatch):
    monkeypatch.setattr("api.engine.process", _brain_never_runs)
    client.post("/command", json={"text": "conversation mode"})

    resp = client.post("/command", json={"text": "/exit"})
    data = resp.json()
    assert data["success"] is True
    assert data["mode"] == DEFAULT_MODE
    assert get_mode() == DEFAULT_MODE


def test_default_mode_still_executes(client, monkeypatch):
    """Outside conversation mode, commands run through the brain as before."""
    from brain.intent import Intent
    from brain.response import BrainResponse

    captured = {}

    def fake_process(text):
        captured["text"] = text
        return BrainResponse(
            intent=Intent(action="open", target="chrome"),
            success=True,
            status="executed",
            action_result={"message": "Opening Chrome"},
        )

    monkeypatch.setattr("api.engine.process", fake_process)

    resp = client.post("/command", json={"text": "open chrome"})
    data = resp.json()
    assert captured["text"] == "open chrome"
    assert data["success"] is True
    assert data["text"] == "Opening Chrome"
    assert data["mode"] == DEFAULT_MODE


def test_conversation_reply_when_hermes_unavailable(client, monkeypatch):
    """A failing language model yields a graceful handled error, still no brain run."""
    monkeypatch.setattr("api.engine.process", _brain_never_runs)
    monkeypatch.setattr(
        "hermes.service.chat",
        lambda message, session_id=None: ProviderResponse(
            success=False, provider="Hermes", model="", text="", error="Connection timeout"
        ),
    )

    client.post("/command", json={"text": "conversation mode"})
    data = client.post("/command", json={"text": "hello"}).json()

    assert data["success"] is False
    assert data["action"] == "conversation"
    assert "Connection timeout" in data["text"]
    assert get_mode() == CONVERSATION_MODE  # still in conversation mode
