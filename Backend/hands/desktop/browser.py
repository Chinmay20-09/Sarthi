"""Browser URL opening for the Desktop hand.

The Desktop hand is deliberately thin here: it only opens http/https URLs
in the default browser. Element discovery, DOM inspection, and semantic
automation belong to Browser Awareness (``skills/browser_awareness/``) and
the ai_chain DOM layer — the priority order is:

    DOM / browser automation → accessibility / semantic UI → visual/UI
    automation → coordinate fallback (calibrated, never random)

This module is the physical "open this URL" primitive at the end of that
chain, not a browser controller.
"""

from __future__ import annotations

import logging
import webbrowser
from urllib.parse import urlsplit

logger = logging.getLogger(__name__)

__all__ = ["open_url", "validate_url"]


def validate_url(url: str) -> str:
    """Return a normalized http/https URL, or raise ValueError.

    Everything except ``http``/``https`` schemes is refused — most
    importantly ``file:``, ``javascript:``, and other schemes with
    non-browser side effects.
    """
    cleaned = (url or "").strip()
    if not cleaned:
        raise ValueError("No URL provided")
    parts = urlsplit(cleaned)
    if parts.scheme not in ("http", "https"):
        raise ValueError(f"Only http/https URLs are allowed, got scheme: {parts.scheme!r}")
    if not parts.netloc:
        raise ValueError(f"URL has no host: {cleaned!r}")
    return cleaned


def open_url(url: str) -> str:
    """Open an http/https URL in the default browser. Returns the URL."""
    normalized = validate_url(url)
    webbrowser.open(normalized)
    logger.debug(f"[Desktop] open_url {normalized}")
    return normalized
