"""
utils/spoken_replies.py

Speaks Sarthi's command results out loud.

docs/ABSOLUTE.md already requires voice announcements for system-handled
automation (ai_chain hands-off warnings). This module extends the same
idea to EVERY response: after a command completes, its assistant reply is
spoken through the same best-effort `utils.voice.announce` channel, so
voice-first users hear the answer instead of reading the dashboard.

Design rules:

- Event-driven: the API layer publishes `command_completed`; this module
  subscribes once and speaks the reply. Skills and the brain never call
  the responder directly, so no execution path is coupled to TTS.
- Never raises, never blocks longer than one utterance: announce() is
  best-effort and degrades to a log line when no voice is available.
- Skips what must not be spoken:
    * empty replies (nothing to say),
    * test mode (no side effects),
    * visual-card payloads (the UI drives those interactions),
    * needs_decision / other interactive statuses (waiting for a click),
    * voice pipeline output itself (would double-speak the transcript).

A user toggle is persisted through the existing settings table so the
preference survives restarts (POST /settings/voice-replies).
"""

from __future__ import annotations

import re

from utils.logger import get_logger
from utils.voice import announce

logger = get_logger(__name__)

# Settings-table key for the user toggle (see api.py /settings/voice-replies).
VOICE_REPLIES_KEY = "voice_replies"

# Statuses that expect a UI click / further input — speaking them would
# announce a question the user is already looking at.
_INTERACTIVE_STATUSES = frozenset({"needs_decision", "needs_input", "awaiting_choice"})

# Markdown noise that reads badly aloud: markdown headers, bullet
# markers, blockquotes, and code-fence lines (```python / ```) which are
# dropped whole — a bare fence line carries no speakable content.
_MD_PREFIX_RE = re.compile(r"^\s*(?:#{1,6}\s+|[-*+]\s+|>\s*)")
_MD_INNER_RE = re.compile(r"[*_`#]+")
_MD_FENCE_RE = re.compile(r"^\s*```")


def _clean_for_speech(text: str) -> str:
    """Flatten markdown artifacts that sound wrong when spoken."""
    spoken_lines: list[str] = []
    for line in (text or "").splitlines():
        if _MD_FENCE_RE.match(line):
            continue  # code fence markers — never speakable
        line = _MD_PREFIX_RE.sub("", line)
        line = _MD_INNER_RE.sub("", line)
        if line.strip():
            spoken_lines.append(line.strip())
    return " ".join(spoken_lines).strip()


def _extract_text(result: dict) -> str:
    """Best-effort assistant reply from a command_completed payload."""
    text = result.get("text")
    if isinstance(text, str) and text.strip():
        return text.strip()
    # Some paths only fill result.message (e.g. memory handlers).
    inner = result.get("result")
    if isinstance(inner, dict):
        message = inner.get("message")
        if isinstance(message, str) and message.strip():
            return message.strip()
    return ""


def _extract_error(result: dict) -> str:
    error = result.get("error")
    return error.strip() if isinstance(error, str) else ""


def _looks_visual(result: dict) -> bool:
    """True when the payload is a visual card the UI must render first."""
    inner = result.get("result")
    if isinstance(inner, dict):
        visual = inner.get("visual")
        if isinstance(visual, dict) and visual.get("type"):
            return True
    return False


def _is_from_speech(result: dict) -> bool:
    """True when the reply came from the voice pipeline (would double-speak)."""
    return result.get("routing") == "speech"


def speak_result(result: dict) -> bool:
    """Speak one command result. Returns True when something was spoken.

    This is the single decision point used by both the event subscription
    and tests: it decides WHAT to say (reply, or error) and whether to say
    anything at all (see the module docstring for the skip rules).
    """
    if not isinstance(result, dict):
        return False
    if not get_enabled():
        return False

    from brain.modes import get_test_mode

    if get_test_mode():
        return False

    status = str(result.get("status") or "").lower()
    if status in _INTERACTIVE_STATUSES:
        return False

    if _looks_visual(result) or _is_from_speech(result):
        return False

    text = _extract_text(result) or _extract_error(result)
    if not text:
        return False

    spoken = _clean_for_speech(text)
    if not spoken:
        return False

    # Truncate very long replies: TTS should not read an essay aloud.
    if len(spoken) > MAX_SPOKEN_CHARS:
        cut = spoken[:MAX_SPOKEN_CHARS]
        break_at = cut.rfind(" ")
        spoken = cut[:break_at if break_at > 0 else MAX_SPOKEN_CHARS].rstrip() + "…"

    try:
        announce(spoken)
        return True
    except Exception as exc:  # announce is best-effort, but never let it escape
        logger.debug(f"Voice reply failed: {exc}")
        return False


# Cap so a long Hermes essay is summarized to its opening, not read in full.
MAX_SPOKEN_CHARS = 300


def _on_command_completed(event) -> None:
    """Event-bus hook: speak every completed command's reply."""
    try:
        speak_result(event.data)
    except Exception as exc:  # the bus already catches, but be explicit
        logger.debug(f"Voice reply handler failed: {exc}")


def register_voice_replies(bus) -> None:
    """Subscribe the voice responder to `command_completed` on this bus."""
    bus.on("command_completed", _on_command_completed)


# ----------------------------------------------------------------------
# Toggle (persisted via the settings table through api.py)
# ----------------------------------------------------------------------


def get_enabled() -> bool:
    """Whether spoken replies are on. Defaults to True."""
    try:
        from database.manager import get_database

        row = get_database().fetch_one(
            "SELECT value FROM settings WHERE key = ?", (VOICE_REPLIES_KEY,)
        )
        if row is not None and row["value"] is not None:
            return str(row["value"]).strip().lower() in {"1", "true", "yes", "on"}
    except Exception:
        pass
    return True


def set_enabled(enabled: bool) -> bool:
    """Persist the toggle and return the new state."""
    from database.manager import get_database

    get_database().execute(
        "INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES (?, ?, datetime('now'))",
        (VOICE_REPLIES_KEY, "true" if enabled else "false"),
    )
    return bool(enabled)
