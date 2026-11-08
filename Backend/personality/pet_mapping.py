"""Maps Sarthi's simulated mood to existing Desktop Pet images."""

MOOD_TO_PET_STATE = {
    "happy": "happy",
    "curious": "thinking",
    "calm": "sleeping",
    "focused": "working",
    "sleepy": "sleeping",
    "concerned": "confused",
    "playful": "happy",
    "neutral": "sleeping",
}


def mood_to_pet_state(mood: str | None) -> str:
    """Return a supported pet state; unknown moods fall back to sleeping."""
    return MOOD_TO_PET_STATE.get((mood or "neutral").strip().lower(), "sleeping")
