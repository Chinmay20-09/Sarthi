"""
ai_chain/screen.py

Screen-state classification for browser awareness.

The robot reads an AI page by clicking into the conversation area and
doing Ctrl+A / Ctrl+C. Whether that copy is usable depends entirely on
*what the browser screen is showing*: a logged-out login wall, a fresh
"new chat" landing, a page that is still generating, the real
conversation, or — when the click landed inside a message element — only
a fragment of it.

This module names that state from the copied text alone (no OCR, no
automation imports), so the driver can react cheaply and deterministically:

    LOGIN_WALL / LANDING_PAGE  -> fail fast with a precise message; the
                                  page is not the conversation at all.
    LOADING                    -> keep waiting (or fail fast once the
                                  budget ran out).
    CONVERSATION               -> the sent prompt is on the page; the
                                  copy-paste heuristic may be trusted.
    FRAGMENT / EMPTY / UNKNOWN -> the copy grabbed the wrong thing; the
                                  driver re-reads and only then considers
                                  the local awareness model.

Only the last bucket may reach the local Hermes model — page chrome is
never sent to it.
"""

from __future__ import annotations

import re
from enum import Enum

from .models import SiteSpec
from .parsing import prompt_present

# Transcripts shorter than this (and without the prompt) cannot be a real
# conversation page — menus, sidebars and chrome alone push copies well
# past it. Such copies are usually a message element captured whole.
FRAGMENT_MAX_CHARS = 80


class ScreenState(str, Enum):
    """What the browser screen is showing, inferred from the copy."""

    CONVERSATION = "conversation"  # the sent prompt is visible -> real chat
    LOGIN_WALL = "login_wall"  # logged out / account wall in the way
    LANDING_PAGE = "landing_page"  # fresh new-chat landing, prompt never sent
    LOADING = "loading"  # page busy generating, but no conversation text yet
    FRAGMENT = "fragment"  # copy is too small to be the page (an element)
    EMPTY = "empty"  # clipboard came back empty
    UNKNOWN = "unknown"  # text, but no way to tell what the page is


def classify(transcript: str, prompt: str, spec: SiteSpec) -> ScreenState:
    """
    Name the screen state behind a copied transcript.

    The sent prompt is the strongest signal: if it is on the page the
    copy came from the real conversation (even when it also carries
    chrome). Everything else is classified with the site's markers.
    """
    text = (transcript or "").strip()
    if not text:
        return ScreenState.EMPTY

    # The sent prompt on the page beats every marker — a real chat can
    # legitimately contain words like "Sign up" or "New chat" in chrome.
    if prompt_present(text, prompt):
        return ScreenState.CONVERSATION

    if _any_marker(text, spec.login_markers):
        return ScreenState.LOGIN_WALL
    if _any_marker(text, spec.landing_markers):
        return ScreenState.LANDING_PAGE
    if _any_marker(text, spec.loading_markers):
        return ScreenState.LOADING

    # No prompt, no markers, and too little text to be a full page.
    if len(text) < FRAGMENT_MAX_CHARS:
        return ScreenState.FRAGMENT
    return ScreenState.UNKNOWN


def state_message(state: ScreenState, spec: SiteSpec) -> str:
    """Human-readable failure text for the deterministic screen states."""
    if state is ScreenState.LOGIN_WALL:
        return (
            f"[{spec.label}] the browser is showing a login screen — the "
            "conversation is not reachable. Log in to the site in your "
            "browser, then run the chain again."
        )
    if state is ScreenState.LANDING_PAGE:
        return (
            f"[{spec.label}] the page is still on its 'new chat' landing — the "
            "prompt never reached the site. The message box was probably not "
            "found; recalibrate the composer point and rerun: "
            f"python -m skills.automation_engine.ai_chain.calibrate "
            f"--site {spec.key} --point composer --record"
        )
    if state is ScreenState.LOADING:
        return (
            f"[{spec.label}] the page is still generating and no reply appeared "
            f"within its {spec.max_wait:.0f}s budget."
        )
    if state is ScreenState.EMPTY:
        return (
            f"[{spec.label}] the copy came back empty — the clipboard or the "
            "Select-All hotkey did not capture the page."
        )
    # FRAGMENT / UNKNOWN / CONVERSATION are not terminal states.
    return f"[{spec.label}] the page could not be read ({state.value})."


# ----------------------------------------------------------------------
# Marker matching
# ----------------------------------------------------------------------


def _any_marker(text: str, markers: tuple[str, ...]) -> bool:
    return any(_marker_present(text, marker) for marker in markers)


def _marker_present(text: str, marker: str) -> bool:
    """Case-insensitive marker match.

    Multi-word markers match as substrings ("Log in" inside a sentence);
    single-word markers match on word boundaries so "Stop" never fires on
    "Full stop" or "Desktop".
    """
    needle = (marker or "").strip()
    if not needle:
        return False
    if " " in needle:
        return needle.lower() in text.lower()
    return re.search(rf"\b{re.escape(needle)}\b", text, re.IGNORECASE) is not None
