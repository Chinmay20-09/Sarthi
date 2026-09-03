"""
ai_chain/parsing.py

Pure string helpers: parsing a spoken/written chain command and
extracting an AI reply from a copied page transcript.

No automation imports — fully unit-testable.
"""

from __future__ import annotations

import re

from .calibration import resolve_site
from .models import ChainRequest

# e.g. "chain <query> from chatgpt to gemini"
_FROM_TO_RE = re.compile(
    r"\bfrom\s+(?P<ai1>[\w .-]+?)\s+to\s+(?P<ai2>[\w .-]+?)(?:[.!?;,]|$)",
    re.IGNORECASE,
)

# "open <AI1> <query> ... to <AI2>" — e.g. "open chatgpt and get prompt
# for ... and send it to gemini" (used when no "from X to Y" is present).
_OPEN_CHAIN_RE = re.compile(
    r"^\s*open\s+(?P<ai1>[\w .-]+?)\s+(?P<body>.*?)\bto\s+(?P<ai2>[\w .-]+?)(?:[.!?;,]|$)",
    re.IGNORECASE | re.DOTALL,
)

# Trailing "and send it" / "sendit" / "and send" filler before "to <AI2>".
_SEND_IT_SUFFIX_RE = re.compile(r"\s+(?:and\s+)?send\s*(?:it)?\s*$", re.IGNORECASE)

_ACTION_PREFIX_RE = re.compile(
    r"^(please\s+)?(chain|automate|run)\s+", re.IGNORECASE
)


def parse_chain_command(raw_text: str, default_ai1: str = "chatgpt", default_ai2: str = "gemini") -> ChainRequest:
    """
    Parse a chain command into a ChainRequest.

    Understands:
        "chain make an image of the sarthi workflow from chatgpt to gemini"
        "/chain <query> from chatgpt to gemini"
        "automate <query> from gemini to chatgpt"

    When no "from X to Y" is present, defaults AI1/AI2 are used and the
    whole command body becomes the query.
    """
    text = (raw_text or "").strip()
    if text.startswith("/"):
        text = text.lstrip("/").strip()

    match = _FROM_TO_RE.search(text)
    ai1, ai2 = default_ai1, default_ai2
    query = text
    if match:
        try:
            ai1 = resolve_site(match.group("ai1")).key
            ai2 = resolve_site(match.group("ai2")).key
            query = (text[: match.start()] + " " + text[match.end() :]).strip()
        except ValueError:
            # Unknown name in the sentence — fall through with defaults and
            # keep the whole text as the query (validation happens on use).
            ai1, ai2 = default_ai1, default_ai2
            query = text
    else:
        # "open <AI1> ... to <AI2>" (no "from ... to").
        open_match = _OPEN_CHAIN_RE.match(text)
        if open_match is not None:
            try:
                ai1 = resolve_site(open_match.group("ai1")).key
                ai2 = resolve_site(open_match.group("ai2")).key
                query = _clean_open_chain_body(open_match.group("body"))
            except ValueError:
                ai1, ai2 = default_ai1, default_ai2
                query = text

    query = _ACTION_PREFIX_RE.sub("", query).strip(" ,.!?;:").strip()
    if not query:
        query = text.strip(" ,.!?;:").strip() or "please continue"

    return ChainRequest(query=query, ai1=ai1, ai2=ai2)


def extract_reply(transcript: str, prompt: str, footer_markers: tuple[str, ...] = ()) -> str:
    """
    Pull the assistant reply out of a copied page transcript.

    The transcript is everything Ctrl+A/Ctrl+C picked up from the page
    (conversation + page chrome). The assistant's reply is the text that
    comes *after* the last occurrence of the prompt we sent. When the
    prompt cannot be found, the whole transcript is returned (best
    effort — the caller can still store it for review).
    """
    if not transcript:
        return ""
    text = transcript.strip()

    # Trim known footer noise appended after the real reply.
    if footer_markers:
        first_marker = min(
            (text.find(marker) for marker in footer_markers if marker in text),
            default=-1,
        )
        if first_marker >= 0:
            text = text[:first_marker].rstrip()

    needle = prompt.strip()
    if needle:
        match = _last_fuzzy_match(text, needle)
        if match is not None:
            text = text[match.end():]

    # Collapse the runaway blank lines copy-paste produces.
    lines = [line.rstrip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line.strip()).strip()


def _clean_open_chain_body(body: str) -> str:
    """Clean the query between 'open <AI1>' and 'to <AI2>'.

    Removes the leading connector ("and get ..." -> "get ...") and the
    trailing "and send it" / "sendit" filler speech adds before the
    destination AI.
    """
    text = (body or "").strip()
    text = re.sub(r"^(?:and|then)\s+", "", text, flags=re.IGNORECASE)
    text = _SEND_IT_SUFFIX_RE.sub("", text)
    return text.strip(" ,.!?;:").strip()


def _last_fuzzy_match(text: str, needle: str):
    """Last occurrence of needle in text, tolerant of whitespace runs.

    The copied transcript may render the prompt with different newline/
    space runs than the exact string we sent, so each word of the prompt
    is matched with flexible whitespace between words.
    """
    words = [word for word in needle.split() if word]
    if not words:
        return None
    pattern = re.compile(r"\s+".join(re.escape(word) for word in words))
    matches = list(pattern.finditer(text))
    return matches[-1] if matches else None
