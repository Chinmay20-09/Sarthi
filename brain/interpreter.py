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

    Args:
        text: Raw natural language input (e.g., "open Chrome")

    Returns:
        Intent with action, target, and confidence.
    """
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
    )
