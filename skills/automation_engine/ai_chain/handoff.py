"""
ai_chain/handoff.py

Backend hand-off between chain steps (v1.5).

The clipboard is scratch space — it gets clobbered by every Select-All +
Copy verification and can be emptied by clipboard managers at any moment.
Treating it as the source of truth for the AI1 -> AI2 hand-off made step 2
fragile: when the paste into AI2's composer failed, there was no saved
copy of the prompt to fall back to.

This module is that saved copy — the "backend" the robot sends from:

    step 1: capture AI1's reply  -> handoff.save("step1_response", text)
    step 2: send AI2 the prompt  -> prompt = handoff.load("step1_response")

Every paste attempt re-copies FROM the store, so a clobbered clipboard
never poisons the hand-off, and each step's prompt/response survives in
memory for the whole run (the responses also land in the run folder as
`0N_stepN_<site>_response.txt` via chain.py, which is the durable copy).

Pure Python, no automation imports — safe to unit-test anywhere.
"""

from __future__ import annotations

from pathlib import Path

from utils.logger import get_logger

logger = get_logger(__name__)

_store: dict[str, str] = {}


def save(key: str, text: str) -> str:
    """Store ``text`` under ``key`` (overwrites). Returns the stored text."""
    cleaned = (text or "").strip()
    _store[key] = cleaned
    return cleaned


def load(key: str) -> str:
    """The stored text for ``key`` ("" when absent)."""
    return _store.get(key, "")


def has(key: str) -> bool:
    """True when ``key`` holds a non-empty value."""
    return bool(_store.get(key, "").strip())


def reset() -> None:
    """Drop the whole store (start of a run / tests)."""
    _store.clear()


def describe(run_dir: Path | None = None) -> str:
    """Human-readable pointer to the backend copies (for error messages)."""
    where = f"run folder {run_dir}" if run_dir is not None else "the chain backend"
    return f"{len(_store)} saved prompt(s)/response(s) in {where}"
