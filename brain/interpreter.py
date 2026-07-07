from models.intent import Intent


def interpret(text: str) -> Intent:

    text = text.lower()

    words = text.split()

    if not words:
        return Intent(
            action="unknown",
            confidence=0.0
        )

    action = words[0]

    target = ""

    if len(words) > 1:
        target = " ".join(words[1:])

    return Intent(
        action=action,
        target=target,
        confidence=1.0
    )