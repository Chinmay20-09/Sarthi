"""Small, deterministic personality services for Sarthi.

This package owns conversational mood interpretation and expression only. It
does not call providers, execute tools, or control Desktop behavior.
"""

from .moods import UserMood, detect_user_mood
from .pet_mapping import mood_to_pet_state
from .state import SarthiMoodEngine

__all__ = ["UserMood", "detect_user_mood", "mood_to_pet_state", "SarthiMoodEngine"]
