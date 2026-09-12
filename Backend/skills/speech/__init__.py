"""
Speech recognition skill for Sarthi.

Provides push-to-talk microphone recording and Whisper-based
transcription as a proper BaseSkill (triggered via POST /listen —
there is no always-on wake word).

Usage:
    from skills.speech import SpeechSkill
    skill = SpeechSkill()
"""

from .main import SpeechSkill

__all__ = ["SpeechSkill"]
