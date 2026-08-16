"""
Interpreter for Sarthi.

Parses natural language commands into structured Intent objects.

Responsibilities:
- Detect action keywords (open, search, play, close, check, status, sync, etc.)
- Extract target entities by filtering filler words
- Return a normalized Intent for downstream processing
"""

from brain.intent import Intent

ACTION_WORDS = {
    # App / web actions
    "open": "open",
    "launch": "open",
    "start": "open",
    "run": "open",
    "search": "search",
    "find": "search",
    "play": "play",
    "close": "close",
    # Project tracker actions
    "check": "check",
    "status": "status",
    "sync": "sync",
    "show": "show",
    "list": "show",
    "track": "track",
    "how": "how",
    "what": "what",
    "pending": "pending",
    "update": "sync",
    # Scanner actions
    "scan": "scan",
    "refresh": "scan",
    "discover": "scan",
    # User config actions (set/configure github username)
    "set": "set",
    "configure": "set",
}

FILLER_WORDS = {
    "please",
    "could",
    "would",
    "can",
    "you",
    "me",
    "the",
    "a",
    "an",
    "my",
    "for",
    "to",
    "on",
    "of",
    "is",
    "are",
    "do",
    "does",
    "tell",
    "me",
    "about",
}


def interpret(text: str) -> Intent:
    """
    Parse natural language text into a structured Intent.

    Slash commands are handled first: "/remember <stuff>" becomes an
    Intent with action="remember" and target="<stuff>", so any command
    prefixed with "/" maps straight to an action name.

    Args:
        text: Raw natural language input (e.g., "open Chrome", "/remember my name is Alice")

    Returns:
        Intent with action, target, and confidence.
    """
    stripped = text.strip()
    if stripped.startswith("/"):
        parts = stripped.split(maxsplit=1)
        name = parts[0][1:].lower().strip()
        rest = parts[1].strip() if len(parts) > 1 else ""
        if name:
            return Intent(
                action=name,
                target=rest,
                confidence=1.0,
                raw_text=text,
            )

    action = "unknown"
    target_words = []

    words = text.lower().split()

    for word in words:
        # Detect action
        if word in ACTION_WORDS:
            action = ACTION_WORDS[word]
            continue

        # Ignore filler words
        if word in FILLER_WORDS:
            continue

        # Everything else belongs to the target
        target_words.append(word)

    target = " ".join(target_words)

    return Intent(
        action=action,
        target=target,
        confidence=1.0 if action != "unknown" else 0.0,
        # Keep the original message so conversational skills can reply to it
        raw_text=text,
    )
