"""
Speech recognition skill for Sarthi.

Provides wake-word detection and Whisper-based transcription
as a proper BaseSkill.

Usage:
    from skills.speech import SpeechSkill
    skill = SpeechSkill()
"""

from .main import SpeechSkill

__all__ = ["SpeechSkill"]
