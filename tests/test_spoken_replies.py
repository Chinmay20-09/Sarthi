"""Tests for the spoken-replies voice responder (utils/spoken_replies.py).

Locks the behaviour that EVERY command response is spoken aloud, not just
the ai_chain hands-off warnings, while things that must never be spoken
are skipped:

    - empty replies, test mode, visual cards, interactive statuses
    - the toggle (persisted setting) gates all speaking
    - markdown artifacts are cleaned before speaking
    - long replies are truncated to one utterance
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from utils import spoken_replies
from utils.spoken_replies import (
    VOICE_REPLIES_KEY,
    get_enabled,
    set_enabled,
    speak_result,
)


@pytest.fixture(autouse=True)
def _force_enabled(monkeypatch):
    """Default every test to the toggle-on state; individual tests override."""
    monkeypatch.setattr(spoken_replies, "get_enabled", lambda: True)


@pytest.fixture(autouse=True)
def _no_test_mode(monkeypatch):
    from brain import modes

    monkeypatch.setattr(modes, "_test_mode", False)


@pytest.fixture
def announce_spy():
    with patch.object(spoken_replies, "announce") as spy:
        yield spy


# ----------------------------------------------------------------------
# What gets spoken
# ----------------------------------------------------------------------


class TestSpeaksReplies:
    def test_speaks_simple_success(self, announce_spy):
        assert speak_result({"text": "Chrome opened", "success": True}) is True
        announce_spy.assert_called_once_with("Chrome opened")

    def test_speaks_result_message_when_text_missing(self, announce_spy):
        result = {"success": True, "result": {"message": "Got it — I'll remember: Alice"}}
        assert speak_result(result) is True
        announce_spy.assert_called_once_with("Got it — I'll remember: Alice")

    def test_speaks_error_when_no_text(self, announce_spy):
        assert speak_result({"success": False, "error": "Chrome is not running"}) is True
        announce_spy.assert_called_once_with("Chrome is not running")

    def test_prefers_text_over_error(self, announce_spy):
        result = {"success": False, "text": "Done, with warnings", "error": "ignored"}
        assert speak_result(result) is True
        announce_spy.assert_called_once_with("Done, with warnings")


# ----------------------------------------------------------------------
# What is never spoken
# ----------------------------------------------------------------------


class TestSkips:
    def test_silent_when_toggle_off(self, announce_spy, monkeypatch):
        monkeypatch.setattr(spoken_replies, "get_enabled", lambda: False)
        assert speak_result({"text": "Chrome opened"}) is False
        announce_spy.assert_not_called()

    def test_silent_in_test_mode(self, announce_spy, monkeypatch):
        from brain import modes

        monkeypatch.setattr(modes, "_test_mode", True)
        assert speak_result({"text": "Chrome opened"}) is False
        announce_spy.assert_not_called()

    def test_silent_for_empty_result(self, announce_spy):
        assert speak_result({}) is False
        assert speak_result(None) is False
        announce_spy.assert_not_called()

    def test_silent_for_blank_text(self, announce_spy):
        assert speak_result({"text": "   "}) is False
        announce_spy.assert_not_called()

    def test_silent_for_visual_card(self, announce_spy):
        result = {
            "success": False,
            "status": "needs_decision",
            "result": {"visual": {"type": "open_choice", "data": {"name": "vscode"}}},
        }
        assert speak_result(result) is False
        announce_spy.assert_not_called()

    def test_silent_for_interactive_status(self, announce_spy):
        assert speak_result({"text": "Pick one", "status": "needs_decision"}) is False
        announce_spy.assert_not_called()

    def test_silent_for_speech_routed_replies(self, announce_spy):
        """The voice pipeline's own transcript must not be re-spoken."""
        result = {"text": "you said open chrome", "routing": "speech"}
        assert speak_result(result) is False
        announce_spy.assert_not_called()


# ----------------------------------------------------------------------
# Speech shaping
# ----------------------------------------------------------------------


class TestSpeechShaping:
    def test_markdown_cleaned(self):
        assert (
            spoken_replies._clean_for_speech("## Header\n- item one\n**bold** move")
            == "Header item one bold move"
        )

    def test_long_reply_truncated_on_word_boundary(self, announce_spy):
        text = "word " * 120  # 600 chars
        assert speak_result({"text": text}) is True
        spoken = announce_spy.call_args[0][0]
        assert len(spoken) <= spoken_replies.MAX_SPOKEN_CHARS + 1  # + ellipsis
        assert spoken.endswith("…")

    def test_empty_after_cleaning_not_spoken(self, announce_spy):
        assert speak_result({"text": "```python\n```"}) is False
        announce_spy.assert_not_called()


# ----------------------------------------------------------------------
# Toggle persistence
# ----------------------------------------------------------------------


class TestToggle:
    def test_roundtrip_via_settings_table(self):
        original = get_enabled()
        try:
            assert set_enabled(False) is False
            assert get_enabled() is False
            assert set_enabled(True) is True
            assert get_enabled() is True
        finally:
            set_enabled(original)

    def test_settings_key_stable(self):
        assert VOICE_REPLIES_KEY == "voice_replies"


# ----------------------------------------------------------------------
# Event-bus wiring
# ----------------------------------------------------------------------


class TestBusWiring:
    def test_registered_handler_speaks_completed_commands(self, announce_spy):
        from events.bus import EventBus

        bus = EventBus()
        spoken_replies.register_voice_replies(bus)
        bus.publish("command_completed", {"text": "Weather is sunny"})
        announce_spy.assert_called_once_with("Weather is sunny")

    def test_other_events_ignored(self, announce_spy):
        from events.bus import EventBus

        bus = EventBus()
        spoken_replies.register_voice_replies(bus)
        bus.publish("intent_parsed", {"text": "open chrome"})
        announce_spy.assert_not_called()

    def test_handler_failure_never_breaks_the_bus(self):
        from events.bus import EventBus

        bus = EventBus()
        spoken_replies.register_voice_replies(bus)
        with patch.object(spoken_replies, "get_enabled", side_effect=RuntimeError("boom")):
            event = bus.publish("command_completed", {"text": "hi"})
        assert event is not None  # bus survived
