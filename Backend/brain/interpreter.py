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
- Recognize AI-chain commands ("run/chain/automate <query> from <AI> to <AI>")
  so "run ... from chatgpt to gemini" is not mistaken for an app open
- Return a normalized Intent for downstream processing
"""

import re

from brain.intent import Intent
from brain.wordfinder import find_target_keyword

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
    # AI chain actions (automation engine laptop automation)
    "chain": "chain",
    "automate": "chain",
    # Browser awareness actions (inspect arbitrary websites)
    "browse": "browse",
    "visit": "browse",
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

# Domains the deterministic skills already know how to operate quickly
# ("open youtube.com and play song" stays on the fast, known path — it is
# never routed to browser awareness).
_DETERMINISTIC_DOMAINS = frozenset(
    {
        "youtube.com",
        "www.youtube.com",
        "github.com",
        "www.github.com",
        "google.com",
        "www.google.com",
        "stackoverflow.com",
        "www.stackoverflow.com",
    }
)

# Dot-RUNS ("..", "../..") must never split a sentence: they are filesystem
# traversal segments inside terminal command paths ("cd ../..", "echo x to
# ../../f.txt"). Splitting on them previously turned "cd ../.." into the
# fragments "cd /" + "/" and derailed the command to the complexity router.
# The protection is gated on a terminal-command prefix so ordinary text with
# ellipses ("...") keeps its legacy sentence-splitting behaviour.
_DOT_RUN_RE = re.compile(r"\.{2,}")
_DOT_RUN_SENTINEL_RE = re.compile(r"\x01D(\d+)\x01")
_TERMINAL_PREFIX_RE = re.compile(
    r"^\s*(?:cd\b|echo\b|create\s+(?:file|directory|dir)\b|write\b)",
    re.IGNORECASE,
)

# A bare domain like "example.com" or "www.example.com/path" (no scheme
# required) — the signal that the user wants browser awareness for a site
# the deterministic knowledge base does not cover.
_DOMAIN_RE = re.compile(
    r"(?:https?://)?(?:www\.)?[a-z0-9-]+(?:\.[a-z0-9-]+){1,}(?:[/:][^\s]*)?",
    re.IGNORECASE,
)

# AI-chain commands: a trigger word plus a "from <AI> to <AI>" clause.
# "run" is also an app-open word, so the from-to clause is what
# disambiguates the sentence into a chain instead of an app launch.
_CHAIN_TRIGGER_WORDS = {"chain", "automate", "run"}
_CHAIN_FROM_TO_RE = re.compile(
    r"\bfrom\s+(?P<ai1>[\w .-]+?)\s+to\s+(?P<ai2>[\w .-]+?)(?:[.!?;,]|$)",
    re.IGNORECASE,
)
# Names the ai_chain module recognises (kept in sync with
# ai_chain/calibration.py SITE_ALIASES so the interpreter needs no
# automation imports).
_CHAIN_AI_NAMES = frozenset(
    {
        "chatgpt",
        "chat gpt",
        "gpt",
        "openai",
        "open ai chat",
        "gemini",
        "google gemini",
    }
)

# "open <AI1> <query> ... to <AI2>" — e.g. "open chatgpt and get prompt
# for ... and send it to gemini". Recognised as an AI chain so the whole
# sentence is not swallowed as the target of "open".
_OPEN_CHAIN_RE = re.compile(
    r"^\s*open\s+(?P<ai1>[\w .-]+?)\s+(?P<body>.*?)\bto\s+(?P<ai2>[\w .-]+?)(?:[.!?;,]|$)",
    re.IGNORECASE | re.DOTALL,
)

# Terminal actions (TERMINAL capability): cd / echo / create / write.
# Exported so downstream stages (entity resolution in brain/engine.py)
# can recognise terminal intents and leave their targets untouched.
TERMINAL_ACTIONS = frozenset({"cd", "echo", "create", "write"})

# "create file <path>" / "create directory <path>" / "create dir <path>"
# (optionally "... with content <text>"). Explicit shapes only — a plain
# "create a poem" is conversational, not a filesystem command.
_CREATE_RE = re.compile(
    r"^create\s+(?P<kind>file|directory|dir)\s+(?P<rest>.+)$",
    re.IGNORECASE | re.DOTALL,
)

# "write <content> to <path>" needs the "to <path>" clause; a bare
# "write a poem" stays conversational (NLP fallback) instead of failing
# at the terminal skill with a usage error.
_WRITE_TO_CLAUSE_RE = re.compile(r"^\s*.+?\s+to\s+\S", re.IGNORECASE | re.DOTALL)


def _token_key(token: str) -> str:
    """Lowercased token without trailing punctuation (for keyword checks)."""
    return token.lower().rstrip(_TRAILING_PUNCTUATION)


# Full sentences AND domain/URL tokens may both contain '.' — the dots
# inside "example.com" or "https://x.io/pricing" must not end a sentence.
_DOMAIN_TOKEN_RE = re.compile(
    r"(?i)(?:https?://)?(?:www\.)?[a-z0-9-]+(?:\.[a-z0-9-]+){1,}(?:[/:][^\s.!?;,]*)?"
)
_SENTINEL_CHAR = "\u0001"


def split_queries(text: str) -> list[str]:
    """Split text into separate queries at full stops ('.').

    "open youtube and search AI. also tell me about weather" becomes
    ["open youtube and search AI", "also tell me about weather"]. Empty
    fragments are dropped. Dots that belong to a domain or URL
    ("example.com", "https://x.io/pricing") are preserved — they never
    split the sentence.
    """
    raw = text or ""
    protected, holder = _protect_domain_tokens(raw)
    # Protect dot-runs ("..") BEFORE splitting — but only for terminal
    # commands, where they are traversal segments of a path, never
    # sentence-ending punctuation ("...").
    dot_runs: list[str] = []
    if _TERMINAL_PREFIX_RE.match(raw):

        def _hold_dot_run(match: re.Match) -> str:
            dot_runs.append(match.group(0))
            return f"{_SENTINEL_CHAR}D{len(dot_runs) - 1}{_SENTINEL_CHAR}"

        protected = _DOT_RUN_RE.sub(_hold_dot_run, protected)
    parts = [part for part in protected.split(".") if part.strip()]
    restored = [_restore_domain_tokens(part, holder).strip() for part in parts]
    # Re-expand the dot-run sentinels back into real '..' segments.
    return [
        _DOT_RUN_SENTINEL_RE.sub(lambda m: dot_runs[int(m.group(1))], part) for part in restored
    ]


def _protect_domain_tokens(text: str) -> tuple[str, dict[str, str]]:
    """Swap domain/URL dots for sentinels so they survive sentence-splitting.

    Returns (protected_text, {sentinel: original_token}).
    """
    holder: dict[str, str] = {}
    result = text
    for index, match in enumerate(_DOMAIN_TOKEN_RE.finditer(text)):
        token = match.group(0)
        sentinel = f"{_SENTINEL_CHAR}{index}{_SENTINEL_CHAR}"
        holder[sentinel] = token
        result = result.replace(token, sentinel, 1)
    return result, holder


def _restore_domain_tokens(part: str, holder: dict[str, str]) -> str:
    for sentinel, token in holder.items():
        part = part.replace(sentinel, token)
    return part


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

    # Terminal file commands (cd / echo / create / write): explicit command
    # shapes only, checked before the generic scan so ACTION_WORDS and the
    # filler-word filter ("to", "the", ...) never mangle paths or literal
    # text ("echo hello to notes.txt" must keep its "to" clause).
    terminal = _parse_terminal_intent(stripped)
    if terminal is not None:
        return [terminal]

    # AI chain: "run/chain/automate <query> from <AI> to <AI>" is a
    # chain command. Without this, "run <query> from chatgpt to gemini"
    # is read as an app-open (run -> open) and fails trying to launch an
    # application named after the query.
    chain_intent = _parse_chain_intent(stripped)
    if chain_intent is not None:
        return [chain_intent]

    # AI chain, "open" flavour: "open chatgpt and <query> ... to gemini".
    open_chain = _parse_open_chain(stripped)
    if open_chain is not None:
        return [open_chain]

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

    # Open-family actions: stop the target at the first known keyword
    # (wordfinder keyword DB) instead of taking the whole sentence, so
    # "open chatgpt and get prompt ..." targets "chatgpt". Sentences
    # without a known keyword keep the legacy whole-target behaviour
    # (e.g. "open visual studio code").
    if action in _OPEN_ACTION_WORDS and target_words:
        keyword = find_target_keyword(target_words)
        if keyword is not None:
            target = keyword[0]

    return [
        Intent(
            action=action,
            target=target,
            confidence=1.0 if action != "unknown" else 0.0,
            raw_text=stripped,
        )
    ]


def _parse_terminal_intent(text: str) -> Intent | None:
    """Parse terminal-style file commands (cd / echo / create / write).

    Returns None for anything that is not an explicit command shape so
    those sentences keep flowing through the generic scan (and, when
    nothing matches there, the conversational fallback):

        cd documents                        -> cd / "documents"
        echo hello                          -> echo / "hello"
        echo hello to notes.txt             -> echo / "hello to notes.txt"
            (the terminal skill splits the "to <file>" clause)
        create file notes.txt               -> create / "file notes.txt"
        create dir projects                 -> create / "dir projects"
        create file notes.txt with content hi -> create (skill creates + writes)
        write hello world to notes.txt      -> write / "hello world to notes.txt"

    "write a poem" (no "to <file>") and "create a website" (no
    file/directory kind) are NOT terminal commands — they return None.
    "cd" / "echo" alone are terminal intents with an empty target so the
    skill can answer with its structured usage hint.
    """
    lowered = text.lower()

    # Trailing punctuation is NOT stripped from terminal targets: sentence
    # dots are already consumed by split_queries, and any remaining dots are
    # part of the path/text ("cd .." must stay "..", not become ".").

    # cd <path> — also "cd" alone (target "" -> the skill's usage hint).
    if lowered == "cd" or lowered.startswith("cd "):
        return Intent(
            action="cd",
            target=text[2:].strip(),
            confidence=1.0,
            raw_text=text,
        )

    # echo <text> [to <file>]
    if lowered == "echo" or lowered.startswith("echo "):
        return Intent(
            action="echo",
            target=text[4:].strip(),
            confidence=1.0,
            raw_text=text,
        )

    # create file|directory|dir <path> [with content <text>]
    create_match = _CREATE_RE.match(text)
    if create_match is not None:
        kind = create_match.group("kind").lower()
        rest = create_match.group("rest").strip()
        return Intent(
            action="create",
            target=f"{kind} {rest}".strip(),
            confidence=1.0,
            raw_text=text,
        )

    # write <content> to <file> — requires the "to <file>" clause.
    if lowered.startswith("write ") and _WRITE_TO_CLAUSE_RE.match(text):
        return Intent(
            action="write",
            target=text[5:].strip(),
            confidence=1.0,
            raw_text=text,
        )

    return None


def _parse_chain_intent(text: str) -> Intent | None:
    """Build a chain intent from a "<trigger> <query> from <AI> to <AI>" sentence.

    Only fires when the sentence starts with a chain trigger word AND the
    from-to clause names known AIs, so plain "run chrome" (no from-to) or
    "run from home to office" (unknown names) keep their normal meaning.
    The full sentence is kept as the target/raw_text: the automation skill
    re-parses it with parse_chain_command to split query vs. AIs.
    """
    match = _CHAIN_FROM_TO_RE.search(text)
    if match is None:
        return None
    first = text.split(maxsplit=1)[0].lower().rstrip(_TRAILING_PUNCTUATION)
    if first not in _CHAIN_TRIGGER_WORDS:
        return None
    ai1 = " ".join(match.group("ai1").strip().lower().split())
    ai2 = " ".join(match.group("ai2").strip().lower().split())
    if ai1 not in _CHAIN_AI_NAMES or ai2 not in _CHAIN_AI_NAMES:
        return None
    return Intent(action="chain", target=text, confidence=1.0, raw_text=text)


def _parse_open_chain(text: str) -> Intent | None:
    """Build a chain intent from an "open <AI1> <query> ... to <AI2>" sentence.

    Example: "open chatgpt and get prompt for making birthday invitation
    image prompt and sendit to gemini" -> chain chatgpt -> gemini, with
    the query extracted by parse_chain_command. Fires only when both AI
    names are known, so "open chrome and go to settings" keeps its
    normal open meaning.
    """
    match = _OPEN_CHAIN_RE.match(text)
    if match is None:
        return None
    ai1 = " ".join(match.group("ai1").strip().lower().split())
    ai2 = " ".join(match.group("ai2").strip().lower().split())
    if ai1 not in _CHAIN_AI_NAMES or ai2 not in _CHAIN_AI_NAMES:
        return None
    return Intent(action="chain", target=text, confidence=1.0, raw_text=text)


def _parse_compound(tokens: list[str], keys: list[str], raw_text: str) -> list[Intent] | None:
    """Decompose "open X and search Q" / "open X and play Y".

    "open youtube and search AI" -> [open youtube, search AI with site=youtube]
    "open youtube and play lofi" -> [open youtube, play lofi with site=youtube]

    Returns None when the sentence is not of that shape.
    """
    open_index = _first_action_index(keys, _OPEN_ACTION_WORDS)
    if open_index is None:
        return None

    # "open <bare-domain> and <task>" — e.g. "open example.com and find the
    # pricing page". The deterministic open/search path cannot drive an
    # arbitrary website, so the whole sentence becomes ONE browse intent
    # (url + objective re-parsed by the Browser Awareness skill). Known
    # deterministic domains (youtube.com, github.com, ...) keep the fast
    # existing path.
    bare_domain = _extract_bare_domain(tokens)
    if bare_domain is not None and bare_domain not in _DETERMINISTIC_DOMAINS:
        return [Intent(action="browse", target=bare_domain, confidence=1.0, raw_text=raw_text)]

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


def _extract_bare_domain(tokens: list[str]) -> str | None:
    """First bare-domain/URL token in the sentence, or None.

    "example.com", "www.example.com/pricing" and "https://x.io" all
    count; plain words ("youtube", "chrome") do not.
    """
    for token in tokens:
        match = _DOMAIN_RE.fullmatch(token.rstrip(_TRAILING_PUNCTUATION))
        if match is not None:
            return match.group(0)
    return None


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
