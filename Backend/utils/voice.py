"""
utils/voice.py

Best-effort voice announcements for system-handled automation.

Per docs/ABSOLUTE.md, any automation that takes control of the laptop
must tell the user — out loud — when to step away and when it is safe
to use the machine again. This helper makes those announcements:

    from utils.voice import announce

    announce("Automation started. Please step away from the keyboard.")
    ...
    announce("Automation finished. You can use your computer now.")

It never raises and never blocks the automation if no voice is
available: it tries, in order,

    1. Windows SAPI (win32com "SAPI.SpVoice") — the classic Windows TTS
    2. PowerShell System.Speech (built into Windows, no install needed)
    3. falls back to a log line only

On non-Windows systems announce() degrades to a log line so automations
still run in dev/CI.
"""

from __future__ import annotations

import logging
import platform
import shutil
import subprocess

logger = logging.getLogger(__name__)


def announce(message: str) -> None:
    """
    Speak ``message`` aloud (blocking). Best effort — never raises.

    Args:
        message: The text to say. Keep it short and clear — it is
                 spoken, not read.
    """
    if not message or not message.strip():
        return
    text = message.strip()

    if platform.system() == "Windows":
        if _announce_sapi(text) or _announce_powershell(text):
            return
    logger.info(f"[voice unavailable] {text}")


# ----------------------------------------------------------------------
# Windows implementations
# ----------------------------------------------------------------------


def _announce_sapi(text: str) -> bool:
    """Windows SAPI5 via pywin32 (win32com). Returns True on success."""
    try:
        import win32com.client  # type: ignore[import-not-found]

        voice = win32com.client.Dispatch("SAPI.SpVoice")
        voice.Speak(text)  # synchronous — returns when finished speaking
        return True
    except Exception as exc:  # ImportError, COM errors, ...
        logger.debug(f"SAPI voice unavailable ({exc})")
        return False


def _announce_powershell(text: str) -> bool:
    """Windows System.Speech via PowerShell. Returns True on success."""
    if shutil.which("powershell") is None:
        return False
    script = (
        "Add-Type -AssemblyName System.Speech;"
        "$v = New-Object System.Speech.Synthesis.SpeechSynthesizer;"
        "$v.Speak($args[0])"
    )
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-STA", "-Command", script, text],
            capture_output=True,
            timeout=120,
            check=False,
        )
        return result.returncode == 0
    except Exception as exc:
        logger.debug(f"PowerShell voice unavailable ({exc})")
        return False
