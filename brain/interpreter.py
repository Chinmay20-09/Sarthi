"""
Interpreter for Sarthi.

Parses natural language commands into structured Intent objects.

Responsibilities:
- Detect action keywords (open, search, play, close, check, status, sync, etc.)
- Extract target entities by filtering filler words
- Split a multi-query command on full stops ("open youtube and search AI.
  also tell me about weather" -> two separate queries)
- For "open X and search Q" / "open X and play Y", use everything after the
  keyword (stopping at the full stop) as the query and produce an open
  intent plus a site-aware search/play intent
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
    # Cleanup actions (clean task history)
    "clean": "clean",
    "cleanup": "clean",
    "clear": "clean",
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

# Keywords that open/launch something (target before "and search ...").
_OPEN_ACTION_WORDS = {"open", "launch", "start", "run"}
# Keywords that start a search query.
_SEARCH_ACTION_WORDS = {"search", "find"}
# Keywords that start a play request.
_PLAY_ACTION_WORDS = {"play"}
# Follow-on keywords that decompose "open X and <action> Y".
_COMPOUND_ACTION_WORDS = _SEARCH_ACTION_WORDS | _PLAY_ACTION_WORDS
# Words joining two clauses inside one sentence ("open X and search Y").
_CONNECTOR_WORDS = {"and", "then", "&"}
# Small words that can sit between the search keyword and the real query
# ("search for python" -> "python").
_QUERY_PREFIX_WORDS = {"for", "about", "on", "the", "a", "an", "to"}
# Punctuation that may trail the query / target and should be dropped.
_TRAILING_PUNCTUATION = ".,!?;:"


def _token_key(token: str) -> str:
    """Lowercased token without trailing punctuation (for keyword checks)."""
    return token.lower().rstrip(_TRAILING_PUNCTUATION)


def split_queries(text: str) -> list[str]:
    """Split text into separate queries at full stops ('.').

    "open youtube and search AI. also tell me about weather" becomes
    ["open youtube and search AI", "also tell me about weather"]. Empty
    fragments are dropped.
    """
    return [part.strip() for part in (text or "").split(".") if part.strip()]


def interpret_many(text: str) -> list[Intent]:
    """Parse every '.'-separated query in ``text`` into one or more Intents.

    Each sentence is parsed independently, and "open X and search Q"
    sentences expand into an open intent plus a search intent so both
    actions can be executed in sequence.
    """
    intents: list[Intent] = []
    for query in split_queries(text):
        intents.extend(_interpret_query(query))
    return intents


def interpret(text: str) -> Intent:
    """Parse natural language text into a structured Intent.

    Slash commands are handled first: "/remember <stuff>" becomes an
    Intent with action="remember" and target="<stuff>", so any command
    prefixed with "/" maps straight to an action name.

    When the text contains multiple '.'-separated queries, this returns
    the FIRST one (see interpret_many() for the full list).

    Args:
        text: Raw natural language input (e.g., "open Chrome", "/remember my name is Alice")

    Returns:
        Intent with action, target, and confidence.
    """
    intents = interpret_many(text)
    if intents:
        return intents[0]
    return Intent(
        action="unknown",
        target="",
        confidence=0.0,
        raw_text=text or "",
    )


# ----------------------------------------------------------------------
# Per-query parsing
# ----------------------------------------------------------------------


def _interpret_query(text: str) -> list[Intent]:
    """Parse one '.'-separated query into one or more Intents."""
    stripped = text.strip()
    if not stripped:
        return []

    if stripped.startswith("/"):
        parts = stripped.split(maxsplit=1)
        name = parts[0][1:].lower().strip()
        rest = parts[1].strip() if len(parts) > 1 else ""
        if name:
            return [
                Intent(
                    action=name,
                    target=rest,
                    confidence=1.0,
                    raw_text=stripped,
                )
            ]

    tokens = stripped.split()
    keys = [_token_key(tok) for tok in tokens]

    # "open X and search Q" -> [open X, search Q on X]
    compound = _parse_compound(tokens, keys, stripped)
    if compound is not None:
        return compound

    # A plain search command: everything after the keyword is the query.
    first_action = _first_action_index(keys)
    if first_action is not None and ACTION_WORDS[keys[first_action]] == "search":
        return [_build_search_intent(tokens, first_action, site="", raw_text=stripped)]

    # Generic single intent (legacy scanning behaviour).
    action = "unknown"
    target_words: list[str] = []
    for index, token in enumerate(tokens):
        key = keys[index]
        if key in ACTION_WORDS:
            action = ACTION_WORDS[key]
            continue
        # Ignore filler words and clause connectors
        if key in FILLER_WORDS or key in _CONNECTOR_WORDS:
            continue
        # Everything else belongs to the target
        target_words.append(token)

    target = " ".join(target_words).strip().rstrip(_TRAILING_PUNCTUATION)

    return [
        Intent(
            action=action,
            target=target,
            confidence=1.0 if action != "unknown" else 0.0,
            raw_text=stripped,
        )
    ]


def _parse_compound(tokens: list[str], keys: list[str], raw_text: str) -> list[Intent] | None:
    """Decompose "open X and search Q" / "open X and play Y".

    "open youtube and search AI" -> [open youtube, search AI with site=youtube]
    "open youtube and play lofi" -> [open youtube, play lofi with site=youtube]

    Returns None when the sentence is not of that shape.
    """
    open_index = _first_action_index(keys, _OPEN_ACTION_WORDS)
    if open_index is None:
        return None

    # The first search/play keyword after "open" drives the second intent.
    action_index = next(
        (i for i in range(open_index + 1, len(keys)) if keys[i] in _COMPOUND_ACTION_WORDS),
        None,
    )
    if action_index is None:
        return None
    action = ACTION_WORDS[keys[action_index]]  # "search" or "play"

    # Target = the words between "open" and the follow-on keyword
    target_words = [
        tokens[i]
        for i in range(open_index + 1, action_index)
        if keys[i]
        and keys[i] not in _CONNECTOR_WORDS
        and keys[i] not in FILLER_WORDS
        and keys[i] not in ACTION_WORDS
    ]
    target = " ".join(target_words).strip().rstrip(_TRAILING_PUNCTUATION)
    if not target:
        return None

    query = _extract_query(tokens, action_index)
    if query is None:
        # "open chrome and search" with nothing after the keyword — just open it.
        return [
            Intent(action="open", target=target, confidence=1.0, raw_text=raw_text),
        ]

    return [
        Intent(action="open", target=target, confidence=1.0, raw_text=raw_text),
        Intent(
            action=action,
            target=query,
            # Search/play runs on the opened site when it is a website (e.g.
            # youtube.com/results / watch), and falls back for apps.
            site=target,
            confidence=1.0,
            raw_text=raw_text,
        ),
    ]


def _build_search_intent(tokens: list[str], keyword_index: int, site: str, raw_text: str) -> Intent:
    """Build a search intent whose target is everything after the keyword."""
    return Intent(
        action="search",
        target=_extract_query(tokens, keyword_index) or "",
        site=site,
        confidence=1.0,
        raw_text=raw_text,
    )


def _extract_query(tokens: list[str], keyword_index: int) -> str | None:
    """Everything after a search keyword, minus leading prefix words.

    The query stops at the end of the sentence (the full stop is already
    handled by the sentence split). Returns None when nothing remains.
    """
    query_words = tokens[keyword_index + 1 :]
    while query_words and _token_key(query_words[0]) in _QUERY_PREFIX_WORDS:
        query_words.pop(0)

    query = " ".join(query_words).strip().rstrip(_TRAILING_PUNCTUATION)
    return query or None


def _first_action_index(keys: list[str], action_keys=None) -> int | None:
    """Index of the first word matching an action keyword, or None."""
    if action_keys is None:
        action_keys = ACTION_WORDS
    return next((i for i, key in enumerate(keys) if key in action_keys), None)
