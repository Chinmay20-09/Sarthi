"""Chat mode state — conversation mode vs default execution mode.

Conversation mode ("talk mode") makes Sarthi purely conversational: the brain
pipeline is skipped entirely and every input goes to Hermes' plain chat path
(no tool planning, no task execution). Typing "/exit" returns to default mode
where commands execute normally.

State is process-local (in-memory); a server restart resets to default mode.

Usage:
    from brain.modes import get_mode, set_mode, detect_mode_command

    detect_mode_command("conversation mode")  # -> "conversation"
    detect_mode_command("/exit")              # -> "default"
    detect_mode_command("open chrome")        # -> None
"""

DEFAULT_MODE = "default"
CONVERSATION_MODE = "conversation"

# Phrases that switch into conversation mode (matched case-insensitively on
# the trimmed input, substring match — "switch to talk mode" also works).
CONVERSATION_TRIGGERS = (
    "conversation mode",
    "conversational mode",
    "talk mode",
    "chat mode",
)

# Phrases that switch back to default mode. "/exit" is the primary one and is
# matched by prefix so "/exit mode" and "/exit please" also work.
EXIT_PREFIXES = ("/exit",)
EXIT_PHRASES = (
    "exit mode",
    "exit chat mode",
    "exit talk mode",
    "exit conversation mode",
    "back to default mode",
)

_mode = DEFAULT_MODE


def get_mode() -> str:
    """Current chat mode: DEFAULT_MODE or CONVERSATION_MODE."""
    return _mode


def set_mode(mode: str) -> str:
    """Set the chat mode; unknown values fall back to default mode."""
    global _mode
    _mode = mode if mode == CONVERSATION_MODE else DEFAULT_MODE
    return _mode


def detect_mode_command(text: str) -> str | None:
    """Return the mode the input asks to switch to, or None if it isn't one.

    Examples:
        "conversation mode" / "talk mode" / "chat mode"  -> "conversation"
        "/exit" / "exit mode"                            -> "default"
        "open chrome"                                    -> None
    """
    if not text:
        return None
    normalized = " ".join(text.strip().lower().split())
    if not normalized:
        return None

    if any(trigger in normalized for trigger in CONVERSATION_TRIGGERS):
        return CONVERSATION_MODE
    if normalized.startswith(EXIT_PREFIXES) or normalized in EXIT_PHRASES:
        return DEFAULT_MODE
    return None
