"""Small runtime facade used only by conversational/chat and /command paths."""

from __future__ import annotations

from .engine import build_personality_context
from .moods import detect_user_mood
from .preferences import PreferenceService
from .state import SarthiMoodEngine

_preferences: PreferenceService | None = None


def get_preference_service() -> PreferenceService:
    global _preferences
    if _preferences is None:
        _preferences = PreferenceService()
    return _preferences


def prepare_chat_personality(message: str, history: list[dict] | None = None) -> tuple[str, dict]:
    """Learn explicit safe preference, update simulated mood, and build context."""
    mood = detect_user_mood(message, history)
    preferences = get_preference_service()
    preferences.observe(message)
    state = SarthiMoodEngine().update(user_mood=mood.mood, message=message)
    context = build_personality_context(
        mood, state, preferences.relevant(message),
    )
    return context, {"user_mood": mood, "sarthi_mood": state}


def decorate_command_result(result: dict, message: str) -> dict:
    """Add the current pet state to the existing /command envelope fields."""
    try:
        mood = detect_user_mood(message)
        route = result.get("routing")
        action = result.get("action")
        if route == "command" and action not in (None, "conversation", "reject_preference"):
            outcome = "success" if result.get("success") else "failure"
            state = SarthiMoodEngine().update(
                user_mood=mood.mood, message=message, outcome=outcome
            )
        else:
            # Conversation mode already updated state before prompt construction.
            state = SarthiMoodEngine().current()
        from .pet_mapping import mood_to_pet_state

        result["pet_state"] = mood_to_pet_state(state.mood)
        result["sarthi_mood"] = state.mood
    except Exception:
        # The personality layer is optional and must not break commands/chat.
        result.setdefault("pet_state", "sleeping")
    return result
