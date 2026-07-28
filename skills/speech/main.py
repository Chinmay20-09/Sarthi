"""
Speech Skill for Sarthi.

Wraps wake-word detection and Whisper-based transcription as a
proper BaseSkill compatible with the Skill Registry.

Speech is no longer a separate module — it is simply another capability.

Uses injected dependencies via self.knowledge and self.events (DI pattern).
"""

import logging
from typing import Any

from brain.intent import Intent
from skills.base import BaseSkill

logger = logging.getLogger(__name__)


class SpeechSkill(BaseSkill):
    """
    Speech recognition skill.

    Provides voice input capabilities:
        - Record audio from microphone
        - Transcribe using Whisper
        - Detect wake word

    Usage:
        skill = SpeechSkill(knowledge_manager=manager, event_bus=bus)
        result = skill.execute(intent)
    """

    name = "speech"
    description = "Voice input via microphone and Whisper transcription"
    version = "1.0.0"

    # ------------------------------------------------------------------
    # BaseSkill interface
    # ------------------------------------------------------------------

    def execute(self, intent: Intent) -> dict[str, Any]:
        """
        Execute a speech command.

        Supported actions:
            - "listen" or "record": Record and transcribe audio

        Args:
            intent: Parsed Intent (action, target, confidence)

        Returns:
            Dict with execution results
        """
        action = intent.action.lower() if intent.action else ""

        if action in ("listen", "record"):
            return self._listen()

        if action == "wakeword":
            return self._check_wakeword()

        return {
            "success": False,
            "status": "unknown",
            "error": f"Unknown speech action: {action}",
        }

    # ------------------------------------------------------------------
    # Internal methods
    # ------------------------------------------------------------------

    def _listen(self) -> dict[str, Any]:
        """Record audio and transcribe."""
        try:
            from speech.recorder import record_audio
            from speech.speech_to_text import transcribe

            audio = record_audio()
            text = transcribe(audio)

            # Publish event via DI
            self.events.publish("speech_recognized", {"text": text}, source="speech_skill")

            return {
                "success": True,
                "status": "transcribed",
                "result": {"text": text},
            }
        except Exception as e:
            logger.error(f"Speech recognition failed: {e}")
            return {
                "success": False,
                "status": "error",
                "error": str(e),
            }

    def _check_wakeword(self) -> dict[str, Any]:
        """Check for wake word detection."""
        try:
            from speech.wake_word import detect_wake_word

            detected = detect_wake_word()
            return {
                "success": True,
                "status": "wakeword_checked",
                "result": {"detected": detected},
            }
        except Exception as e:
            logger.error(f"Wake word detection failed: {e}")
            return {
                "success": False,
                "status": "error",
                "error": str(e),
            }
