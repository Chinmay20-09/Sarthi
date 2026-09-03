"""
brain/wordfinder.py

Keyword-based target detection for the interpreter.

When a command like "open chatgpt and get prompt for making a logo" is
parsed, the interpreter used to treat EVERYTHING after "open" as the
target. The wordfinder fixes that: it knows the target keywords and
stops the target at the first known keyword, so the sentence above
targets "chatgpt".

Keywords come from three layers:
    1. built-in defaults (AI names)  — always active
    2. brain/keywords.json           — the file YOU edit (gitignored)
    3. scanned applications          — learned automatically from the
       Knowledge layer (every app's name and aliases become keywords, so
       a fresh "scan my system" teaches the wordfinder immediately)

Edit brain/keywords.json directly, or add keywords from the command line:

    python -m brain.wordfinder add telegram whatsapp
    python -m brain.wordfinder            # list the active keywords

Matching rules:
    - keywords are matched as a *prefix* of the target words
    - the longest matching keyword wins ("chat gpt" beats "gpt")
    - multi-word keywords are supported
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
KEYWORDS_FILE = PACKAGE_DIR / "keywords.json"
KEYWORDS_EXAMPLE = PACKAGE_DIR / "keywords.example.json"

# Built-in keywords — always active, so the interpreter works before the
# user edits keywords.json.
DEFAULT_KEYWORDS = frozenset(
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

_keywords_cache: frozenset[str] | None = None


def get_keywords(manager=None) -> frozenset[str]:
    """All active keywords: defaults + user keywords.json + scanned apps.

    The knowledge layer is consulted lazily (its application list is
    cached by KnowledgeManager), so every scanned application's name and
    aliases automatically become target keywords — a fresh scan teaches
    the wordfinder without any file editing.

    Args:
        manager: Optional KnowledgeManager (tests inject a fake). Defaults
                 to the global knowledge manager.
    """
    return _static_keywords() | _knowledge_keywords(manager)


def _static_keywords() -> frozenset[str]:
    """Built-in defaults + the user's keywords.json (cached)."""
    global _keywords_cache
    if _keywords_cache is None:
        words = set(DEFAULT_KEYWORDS)
        if KEYWORDS_FILE.exists():
            try:
                data = json.loads(KEYWORDS_FILE.read_text(encoding="utf-8"))
                for item in data.get("keywords", []):
                    clean = _normalize(item)
                    if clean:
                        words.add(clean)
            except (json.JSONDecodeError, OSError):
                pass
        _keywords_cache = frozenset(words)
    return _keywords_cache


def _knowledge_keywords(manager=None) -> frozenset[str]:
    """Names + aliases of every scanned application, normalized.

    Never raises: a missing/broken knowledge layer simply contributes no
    keywords (the static set still works).
    """
    try:
        if manager is None:
            from knowledge.manager import get_manager

            manager = get_manager()
        applications = manager.load_applications()
    except Exception:
        return frozenset()

    words = set()
    for app in applications:
        name = _normalize(app.get("name", ""))
        if name:
            words.add(name)
        for alias in app.get("aliases", []) or []:
            clean = _normalize(alias)
            if clean:
                words.add(clean)
    return frozenset(words)


def find_target_keyword(words: list[str], keywords: frozenset[str] | None = None):
    """Longest known keyword that prefixes ``words``.

    Args:
        words: Target words collected by the interpreter (e.g. ["chatgpt",
               "and", "get", "prompt"]).
        keywords: Optional keyword set (tests inject this); defaults to
                  the loaded keyword DB.

    Returns:
        (keyword, word_count) when a keyword matches the start of the
        target words, else None. Only *prefix* matches count, so
        "open visual studio code" is untouched unless that whole phrase
        is itself a keyword.
    """
    keywords = keywords if keywords is not None else get_keywords()
    best = None
    for keyword in keywords:
        count = len(keyword.split())
        if count > len(words):
            continue
        prefix = " ".join(_normalize(word) for word in words[:count])
        if prefix == keyword and (best is None or count > best[1]):
            best = (keyword, count)
    return best


def add_keyword(name: str) -> bool:
    """Append a keyword to the user's keywords.json (creating it if needed).

    The new keyword becomes active immediately (cache is reset).
    """
    clean = _normalize(name)
    if not clean:
        return False

    data = {}
    if KEYWORDS_FILE.exists():
        try:
            data = json.loads(KEYWORDS_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            data = {}

    if not data:
        data["_comment"] = (
            "Sarthi wordfinder keywords. Each entry ends an 'open ...' target: "
            "the interpreter stops the target at the first known keyword instead "
            "of swallowing the whole sentence. Edit this file directly or run "
            "'python -m brain.wordfinder add <keyword>'."
        )

    existing = {str(word).strip().lower() for word in data.get("keywords", [])}
    if clean not in existing:
        data.setdefault("keywords", []).append(clean)
        KEYWORDS_FILE.write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        global _keywords_cache
        _keywords_cache = None
    return True


def _normalize(value) -> str:
    """Lowercase, trim, collapse whitespace, and drop edge punctuation."""
    return " ".join(str(value).strip().lower().strip(".,!?;:").split())


if __name__ == "__main__":
    args = sys.argv[1:]
    if args and args[0] == "add":
        added = [arg for arg in args[1:] if add_keyword(arg)]
        print(f"Added {len(added)} keyword(s) to {KEYWORDS_FILE}")
    else:
        static = sorted(_static_keywords())
        learned = _knowledge_keywords()
        print("Static keywords (defaults + brain/keywords.json):")
        print("  " + ", ".join(static))
        print(f"\nLearned from scanned applications: {len(learned)} keyword(s)")
        print(f"Total active keywords: {len(get_keywords())}")
        print(f"\nUser file: {KEYWORDS_FILE}")
        if not KEYWORDS_FILE.exists():
            print("(none yet — run: python -m brain.wordfinder add <keyword>)")
