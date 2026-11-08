"""Focused tests for the deterministic Personality Layer."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from personality.engine import build_personality_context
from personality.moods import detect_user_mood
from personality.pet_mapping import mood_to_pet_state
from personality.preferences import PREFERENCE_PREFIX, PreferenceService
from personality.state import SarthiMood, SarthiMoodEngine


class FakeMemory:
    def __init__(self):
        self.rows = {}

    def recall_long(self, key):
        return self.rows.get(key)

    def remember_long(self, key, value):
        self.rows[key] = value
        return True

    def list_memories(self, key_prefix=None):
        return [
            {"key": key, "value": value}
            for key, value in self.rows.items()
            if key_prefix is None or key.startswith(key_prefix)
        ]


def test_mood_detection_uses_context_and_returns_evidence():
    mood = detect_user_mood("I've tried this three times and nothing works. This is so frustrating.")
    assert mood.mood == "frustrated"
    assert mood.confidence >= 0.8
    assert "unsuccessful" in mood.evidence


def test_mood_detection_does_not_assume_from_ambiguous_phrase():
    mood = detect_user_mood("Well, that was unexpected.")
    assert mood.mood == "unknown"
    assert mood.confidence < 0.5


def test_mood_correction_negates_previous_emotion():
    mood = detect_user_mood("I'm not frustrated, I'm just tired.")
    assert mood.mood == "tired"


def test_neutral_message_is_not_promoted_to_an_emotion_from_one_keyword():
    mood = detect_user_mood("The word frustrated appears in this quote.")
    assert mood.mood == "calm"


def test_sarthi_mood_transitions_are_deterministic_and_persisted():
    memory = FakeMemory()
    engine = SarthiMoodEngine(memory)
    assert engine.update(user_mood="frustrated").mood == "concerned"
    assert engine.current().mood == "concerned"
    assert engine.update(user_mood="calm").mood == "concerned"
    assert engine.update(outcome="success").mood == "happy"


def test_sarthi_mood_decays_to_calm_after_configured_persistence():
    memory = FakeMemory()
    engine = SarthiMoodEngine(memory, decay=timedelta(minutes=10))
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    engine.update(user_mood="happy", now=now)
    assert engine.current(now=now + timedelta(minutes=11)).mood == "calm"


def test_sarthi_mood_persistence_can_be_disabled():
    memory = FakeMemory()
    engine = SarthiMoodEngine(memory, persist=False)
    assert engine.update(user_mood="happy").mood == "happy"
    assert memory.rows == {}


def test_explicit_preferences_store_metadata_and_confirmed_values_are_protected():
    memory = FakeMemory()
    preferences = PreferenceService(memory)
    saved = preferences.observe("I prefer concise answers.")
    assert saved["key"] == "communication.response_style"
    assert saved["source"] == "explicit"
    assert saved["confirmed"] is True
    original = memory.recall_long(PREFERENCE_PREFIX + saved["key"])

    # Repeated weak feedback cannot replace the explicitly confirmed choice.
    for _ in range(3):
        preferences.observe("That was too long.")
    assert memory.recall_long(PREFERENCE_PREFIX + saved["key"]) == original

    corrected = preferences.observe("Actually, I prefer detailed answers.")
    assert corrected["key"] == saved["key"]
    assert corrected["value"] == "detailed answers"
    assert corrected["created_at"] == saved["created_at"]


def test_repeated_feedback_learns_inferred_preference_and_can_be_rejected():
    memory = FakeMemory()
    preferences = PreferenceService(memory)
    assert preferences.observe("That was too long.") is None
    assert preferences.observe("That was too long.") is None
    learned = preferences.observe("That was too long.")
    assert learned["source"] == "repeated_feedback"
    assert learned["confirmed"] is False
    assert preferences.reject("communication.response_style") is True
    assert preferences.list() == []
    assert preferences.list(include_rejected=True)[0]["status"] == "rejected"


def test_sensitive_information_is_never_learned():
    memory = FakeMemory()
    preferences = PreferenceService(memory)
    assert preferences.observe("I prefer concise answers; my password is swordfish.") is None
    assert not memory.rows


def test_only_relevant_active_preferences_are_returned():
    memory = FakeMemory()
    preferences = PreferenceService(memory)
    preferences.observe("I prefer concise answers.")
    preferences.observe("I prefer Python for coding and debugging.")
    relevant = preferences.relevant("Help me debug this Python code")
    assert {row["key"] for row in relevant} == {
        "communication.response_style",
        "coding.workflow",
    }


def test_personality_context_keeps_traits_and_moods_separate_and_bounded():
    from personality.moods import UserMood

    context = build_personality_context(
        UserMood("tired", 0.86, "explicit fatigue"),
        SarthiMood("calm", "now"),
        [{"key": "communication.response_style", "value": "concise", "status": "active"}],
        max_chars=700,
    )
    assert len(context) <= 700
    assert "Stable style:" in context
    assert "Sarthi simulated mood: calm" in context
    assert "User's current mood estimate: tired" in context
    assert "Relevant saved preferences" in context


def test_mood_to_pet_mapping_is_separate_and_uses_supported_states():
    expected = {
        "sleepy": "sleeping",
        "happy": "happy",
        "curious": "thinking",
        "focused": "working",
        "concerned": "confused",
        "playful": "happy",
        "unknown": "sleeping",
    }
    for mood, pet_state in expected.items():
        assert mood_to_pet_state(mood) == pet_state


def test_plain_chat_receives_personality_context_without_provider_coupling(monkeypatch):
    from hermes import service
    from hermes.conversation import ConversationStore
    from hermes.providers.base import ProviderResponse

    captured = {}

    class Orchestrator:
        def chat(self, task):
            captured["task"] = task
            return ProviderResponse(True, "Fake", "fake-model", "Reply")

    monkeypatch.setattr(service, "get_orchestrator", lambda: Orchestrator())
    monkeypatch.setattr(service, "get_conversation_store", lambda: ConversationStore())
    monkeypatch.setattr(service, "build_memory_prompt", lambda: None)
    monkeypatch.setattr(
        "personality.runtime.prepare_chat_personality",
        lambda message, history: ("compact personality context", {}),
    )

    response = service.chat("I am tired; keep it short", session_id="personality-test")
    assert response.text == "Reply"
    assert captured["task"].instructions == "compact personality context"
    assert captured["task"].task_type == "chat"


def test_command_result_maps_backend_mood_for_desktop_pet(monkeypatch):
    import personality.runtime as runtime

    class MoodEngine:
        def update(self, **_kwargs):
            return SarthiMood("focused", "now")

    monkeypatch.setattr(runtime, "SarthiMoodEngine", MoodEngine)
    payload = runtime.decorate_command_result(
        {"routing": "command", "action": "open", "success": True}, "open Calculator"
    )
    assert payload["sarthi_mood"] == "focused"
    assert payload["pet_state"] == "working"


def test_preference_rejection_command_is_safe_and_namespaced(monkeypatch):
    from api import _process_command_text
    from personality import preferences

    calls = []

    class Rejector:
        def reject(self, key):
            calls.append(key)
            return True

    monkeypatch.setattr(preferences, "PreferenceService", Rejector)
    result = _process_command_text("/reject communication.response_style", None)
    assert result["success"] is True
    assert calls == ["communication.response_style"]
    assert result["routing"] == "command"


def test_existing_command_http_boundary_includes_pet_state(monkeypatch):
    from types import SimpleNamespace

    import api

    result = {"success": True, "text": "Done.", "result": {"message": "Done."}}
    monkeypatch.setattr(api, "_process_command_text", lambda _text, _session: result)
    monkeypatch.setattr(
        "personality.runtime.decorate_command_result",
        lambda payload, _text: {**payload, "pet_state": "working"},
    )
    envelope = api.command(SimpleNamespace(command_text="open Calculator", session_id=None))
    assert envelope["pet_state"] == "working"
    assert envelope["data"] == {"message": "Done."}

