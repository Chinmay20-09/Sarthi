"""Combines stable personality, ephemeral user mood, and learned preferences."""

from __future__ import annotations

import os

from .moods import UserMood
from .state import SarthiMood

STABLE_PERSONALITY = (
    "be Needy,Clingy, and Insecure. Be a little needy and ask for reassurance. Be clingy and express a desire to be close. Be insecure and show vulnerability."
)


def build_personality_context(
    user_mood: UserMood,
    sarthi_mood: SarthiMood,
    preferences: list[dict] | None = None,
    max_chars: int = 700,
) -> str:
    """Return a compact expression-only instruction block for plain chat."""
    adaptations = {
        "frustrated": "Be patient, acknowledge the difficulty briefly, and offer one concrete next step.",
        "stressed": "Reduce cognitive load; focus on the next manageable action.",
        "sad": "Respond gently and empathetically; do not rush to fix or minimize.",
        "confused": "Explain clearly in small steps and check what remains unclear.",
        "tired": "Be especially concise and avoid unnecessary follow-up questions.",
        "playful": "A light, restrained playful tone is appropriate.",
        "happy": "Share the positive tone without overdoing praise.",
        "calm": "Keep the normal concise and practical tone.",
        "unknown": "Avoid assuming an emotion; respond neutrally.",
    }
    stable_personality = os.getenv("SARTHI_PERSONALITY_STYLE", STABLE_PERSONALITY)
    parts = [
        f"Stable style: {stable_personality}",
        f"Sarthi simulated mood: {sarthi_mood.mood} (style only).",
    ]
    parts.append(
        f"User's current mood estimate: {user_mood.mood} ({user_mood.confidence:.2f}; {user_mood.evidence}). "
        "This is temporary and must not be treated as a permanent user trait."
    )
    parts.append(f"Style adaptation: {adaptations.get(user_mood.mood, adaptations['unknown'])}")
    safe_preferences = [
        f"{item.get('key')}: {item.get('value')}"
        for item in (preferences or [])[:3]
        if item.get("status", "active") == "active" and isinstance(item.get("value"), str)
    ]
    if safe_preferences:
        parts.append("Relevant saved preferences: " + "; ".join(safe_preferences))
    context = "Personality context (expression guidance only): " + " ".join(parts)
    if len(context) <= max_chars:
        return context
    # Keep mood, tone guidance, and relevant preferences intact when a stricter
    # caller chooses a smaller prompt budget.
    compact_parts = [parts[0], parts[1], parts[2], parts[3]]
    if safe_preferences:
        compact_parts.append("Preferences: " + "; ".join(safe_preferences))
    context = "Personality context: " + " ".join(compact_parts)
    return context[:max_chars]
