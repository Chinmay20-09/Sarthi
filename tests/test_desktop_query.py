"""Focused tests for the Phase One desktop query path."""

from unittest.mock import MagicMock, patch

import pytest
from api import DesktopQueryRequest, desktop_query
from hermes.desktop_query import run_desktop_query
from hermes.providers.base import ProviderResponse
from pydantic import ValidationError


class FakeStore:
    def __init__(self):
        self.turns = []

    def get_history(self, _session_id):
        return []

    def add_turn(self, session_id, role, content):
        self.turns.append((session_id, role, content))


def response(text, success=True, error=None):
    return ProviderResponse(
        success=success, provider="Test", model="test-model", text=text, error=error
    )


def test_desktop_query_plain_answer_uses_configured_provider_and_session():
    store = FakeStore()
    with (
        patch("hermes.desktop_query.get_conversation_store", return_value=store),
        patch("hermes.desktop_query.get_orchestrator") as get_orchestrator,
    ):
        orchestrator = MagicMock()
        orchestrator.generate.return_value = response(
            "The sky looks blue because of Rayleigh scattering."
        )
        get_orchestrator.return_value = orchestrator

        result = run_desktop_query("Why is the sky blue?", "desktop-test")

    assert result["success"] is True
    assert result["response"].startswith("The sky")
    assert result["action"] is None
    assert result["session_id"] == "desktop-test"
    assert [turn[1] for turn in store.turns] == ["user", "assistant"]


def test_open_url_is_returned_for_desktop_client_to_execute():
    store = FakeStore()
    hand = MagicMock()
    hand.execute.return_value = {
        "success": True,
        "action": "open_url",
        "message": "URL opened",
        "data": {},
    }
    with (
        patch("hermes.desktop_query.get_conversation_store", return_value=store),
        patch("hermes.desktop_query.get_orchestrator") as get_orchestrator,
        patch("hermes.desktop_query.get_desktop_hand", return_value=hand),
    ):
        orchestrator = MagicMock()
        orchestrator.generate.side_effect = [
            response(
                '{"tool_call":{"tool":"desktop_open_url","arguments":{"url":"https://example.com"}}}'
            ),
            response("I opened the example site."),
        ]
        get_orchestrator.return_value = orchestrator

        result = run_desktop_query("Open https://example.com", "desktop-test")

    hand.execute.assert_not_called()
    assert result["success"] is True
    assert result["action"]["name"] == "open_url"
    assert result["client_action"] == {
        "type": "open_url",
        "url": "https://example.com",
    }
    assert result["response"] == "I opened the example site."


def test_file_url_is_rejected_before_it_reaches_the_desktop_client():
    hand = MagicMock()
    with (
        patch("hermes.desktop_query.get_conversation_store", return_value=FakeStore()),
        patch("hermes.desktop_query.get_orchestrator") as get_orchestrator,
        patch("hermes.desktop_query.get_desktop_hand", return_value=hand),
    ):
        orchestrator = MagicMock()
        orchestrator.generate.return_value = response(
            '{"tool_call":{"tool":"desktop_open_url","arguments":{"url":"file:///C:/secret"}}}'
        )
        get_orchestrator.return_value = orchestrator

        result = run_desktop_query("Open this file URL")

    assert result["success"] is False
    assert result["action"]["success"] is False
    assert "HTTP or HTTPS" in result["response"]
    assert hand.execute.call_count == 0
    assert orchestrator.generate.call_count == 1


def test_pet_state_request_is_returned_to_desktop_client():
    with (
        patch("hermes.desktop_query.get_conversation_store", return_value=FakeStore()),
        patch("hermes.desktop_query.get_orchestrator") as get_orchestrator,
        patch("hermes.desktop_query.get_desktop_hand") as get_hand,
    ):
        orchestrator = MagicMock()
        get_orchestrator.return_value = orchestrator

        result = run_desktop_query("turn sad")

    get_hand.assert_not_called()
    orchestrator.generate.assert_not_called()
    assert result["success"] is True
    assert result["client_action"] == {"type": "set_pet_state", "state": "sad"}
    assert result["action"]["pending"] is True
    assert "sad" in result["response"]


@pytest.mark.parametrize(
    ("query", "state"),
    [
        ("turn sleeping", "sleeping"),
        ("make Hitori happy", "happy"),
        ("please set pet to thinking", "thinking"),
        ("change Hitori to working", "working"),
        ("turn confused", "confused"),
        ("make the pet sad", "sad"),
        ("turn Hitori asleep", "sleeping"),
        ("switch the pet to cheerful", "happy"),
    ],
)
def test_pet_emotion_commands_are_deterministic_and_skip_model(query, state):
    with (
        patch("hermes.desktop_query.get_conversation_store", return_value=FakeStore()),
        patch("hermes.desktop_query.get_orchestrator") as get_orchestrator,
        patch("hermes.desktop_query.get_desktop_hand") as get_hand,
    ):
        result = run_desktop_query(query)

    get_orchestrator.assert_not_called()
    get_hand.assert_not_called()
    assert result["success"] is True
    assert result["client_action"] == {"type": "set_pet_state", "state": state}
    assert result["action"]["pending"] is True


def test_play_youtube_shortcut_uses_desktop_client_browser():
    with (
        patch("hermes.desktop_query.get_conversation_store", return_value=FakeStore()),
        patch("hermes.desktop_query.get_orchestrator") as get_orchestrator,
        patch("hermes.desktop_query.get_desktop_hand") as get_hand,
    ):
        orchestrator = MagicMock()
        get_orchestrator.return_value = orchestrator

        result = run_desktop_query("play youtube")

    get_hand.assert_not_called()
    orchestrator.generate.assert_not_called()
    assert result["client_action"] == {
        "type": "open_url",
        "url": "https://www.youtube.com/",
    }
    assert "youtube.com" in result["response"]


def test_play_youtube_song_opens_first_video_without_model():
    with (
        patch("hermes.desktop_query.get_conversation_store", return_value=FakeStore()),
        patch("hermes.desktop_query.get_orchestrator") as get_orchestrator,
        patch(
            "hermes.desktop_query.get_first_youtube_video_url",
            return_value="https://www.youtube.com/watch?v=abcdefghijk",
        ),
    ):
        result = run_desktop_query("Play lost in love on YouTube")

    get_orchestrator.assert_not_called()
    assert result["client_action"] == {
        "type": "open_url",
        "url": "https://www.youtube.com/watch?v=abcdefghijk",
    }


def test_play_song_without_youtube_uses_video_resolver():
    with (
        patch("hermes.desktop_query.get_conversation_store", return_value=FakeStore()),
        patch("hermes.desktop_query.get_orchestrator") as get_orchestrator,
        patch(
            "hermes.desktop_query.get_first_youtube_video_url",
            return_value="https://www.youtube.com/watch?v=abcdefghijk",
        ) as resolve_video,
    ):
        result = run_desktop_query("Play lost in love")

    get_orchestrator.assert_not_called()
    resolve_video.assert_called_once_with("lost in love")
    assert result["client_action"]["url"] == "https://www.youtube.com/watch?v=abcdefghijk"


def test_compound_request_uses_model_only_to_split_then_queues_ordered_actions():
    with (
        patch("hermes.desktop_query.get_conversation_store", return_value=FakeStore()),
        patch("hermes.desktop_query.get_orchestrator") as get_orchestrator,
        patch("hermes.desktop_query.get_desktop_hand") as get_hand,
        patch(
            "hermes.desktop_query.get_first_youtube_video_url",
            return_value="https://www.youtube.com/watch?v=abcdefghijk",
        ),
    ):
        orchestrator = MagicMock()
        orchestrator.generate.return_value = response(
            '{"tasks":["turn sad","play lost in love on youtube"]}'
        )
        get_orchestrator.return_value = orchestrator

        result = run_desktop_query("Turn sad and play lost in love on YouTube")

    assert orchestrator.generate.call_count == 1
    assert orchestrator.generate.call_args.args[0].task_type == "desktop_decomposition"
    get_hand.assert_not_called()
    assert result["success"] is True
    assert result["client_actions"] == [
        {"type": "set_pet_state", "state": "sad"},
        {
            "type": "open_url",
            "url": "https://www.youtube.com/watch?v=abcdefghijk",
        },
    ]


def test_compound_request_rejects_model_subtasks_outside_deterministic_allowlist():
    with (
        patch("hermes.desktop_query.get_conversation_store", return_value=FakeStore()),
        patch("hermes.desktop_query.get_orchestrator") as get_orchestrator,
        patch("hermes.desktop_query.get_desktop_hand") as get_hand,
    ):
        orchestrator = MagicMock()
        orchestrator.generate.return_value = response(
            '{"tasks":["turn sad and delete files","play lost in love on youtube"]}'
        )
        get_orchestrator.return_value = orchestrator

        result = run_desktop_query("Turn sad and play lost in love on YouTube")

    get_hand.assert_not_called()
    assert result["success"] is False
    assert result["error"] == "unsupported_subtask"


def test_unsupported_model_action_is_rejected_without_touching_hand():
    hand = MagicMock()
    with (
        patch("hermes.desktop_query.get_conversation_store", return_value=FakeStore()),
        patch("hermes.desktop_query.get_orchestrator") as get_orchestrator,
        patch("hermes.desktop_query.get_desktop_hand", return_value=hand),
    ):
        orchestrator = MagicMock()
        orchestrator.generate.return_value = response(
            '{"tool_call":{"tool":"run_shell","arguments":{"command":"whoami"}}}'
        )
        get_orchestrator.return_value = orchestrator

        result = run_desktop_query("Run a shell command")

    assert result["success"] is False
    assert result["error"] == "invalid_action"
    hand.execute.assert_not_called()


def test_malformed_model_action_arguments_are_rejected_before_hand():
    hand = MagicMock()
    with (
        patch("hermes.desktop_query.get_conversation_store", return_value=FakeStore()),
        patch("hermes.desktop_query.get_orchestrator") as get_orchestrator,
        patch("hermes.desktop_query.get_desktop_hand", return_value=hand),
    ):
        orchestrator = MagicMock()
        orchestrator.generate.return_value = response(
            '{"tool_call":{"tool":"desktop_open_url","arguments":{"url":42}}}'
        )
        get_orchestrator.return_value = orchestrator

        result = run_desktop_query("Open a URL")

    assert result["success"] is False
    assert result["error"] == "invalid_action"
    hand.execute.assert_not_called()


def test_provider_timeout_is_returned_as_a_client_safe_failure():
    with (
        patch("hermes.desktop_query.get_conversation_store", return_value=FakeStore()),
        patch("hermes.desktop_query.get_orchestrator") as get_orchestrator,
    ):
        orchestrator = MagicMock()
        orchestrator.generate.return_value = response(
            "", success=False, error="The model request timed out."
        )
        get_orchestrator.return_value = orchestrator

        result = run_desktop_query("Explain something")

    assert result["success"] is False
    assert result["error"] == "model_unavailable"
    assert result["response"] == "The model request timed out."


def test_desktop_query_endpoint_has_stable_response_envelope():
    with patch(
        "hermes.desktop_query.run_desktop_query",
        return_value={"success": True, "response": "Hello.", "error": None, "action": None},
    ):
        result = desktop_query(DesktopQueryRequest(query="Hello", session_id="ui-1"))

    assert result == {
        "success": True,
        "response": "Hello.",
        "error": None,
        "action": None,
        "session_id": "ui-1",
    }


def test_desktop_query_endpoint_rejects_empty_or_extra_fields():
    for payload in ({"query": "   "}, {"query": "hi", "extra": "no"}):
        try:
            DesktopQueryRequest.model_validate(payload)
        except ValidationError:
            continue
        raise AssertionError(f"request unexpectedly accepted: {payload}")
