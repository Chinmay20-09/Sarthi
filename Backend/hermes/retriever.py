"""
Hybrid Retriever — RAG over Sarthi's existing stores, no vector database.

Architecture (deliberate):

    User query
       ↓
    Retriever.retrieve(query)
       ├── SQL retrieval          → knowledge_memory (/remember facts),
       │                            command_history, settings
       ├── Knowledge retrieval    → applications + websites (fuzzy, via
       │                            the EntityResolver's own store)
       ├── Sandbox retrieval      → similar past Hermes tasks (query index)
       └── Conversation retrieval → session history (recent turns)
       ↓
    ContextBuilder / Context  — bounded, source-tagged text blocks

The existing Sarthi .db and knowledge JSON files stay the single source of
truth — nothing is duplicated into a vector store. SQL is the primary
retrieval mechanism (keyword LIKE for memory/history, exact/fuzzy for
entities); no embeddings are introduced because every store here is small
enough that keyword/structured retrieval is exact and instant. If a future
corpus outgrows this, a semantic layer can be added behind the same
Retriever interface without touching callers.

Bounded by design: retrieve() never dumps a whole store into the prompt —
every section is capped (max chars per section and overall).
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Boundaries (kept generous enough to be useful, small enough for an 8B model)
# ---------------------------------------------------------------------------

MAX_TOTAL_CHARS = 6000
MAX_MEMORY_FACTS = 12
MAX_MEMORY_CHARS = 1200
MAX_HISTORY_ROWS = 8
MAX_HISTORY_CHARS = 1000
MAX_ENTITIES = 12
MAX_ENTITY_CHARS = 700
MAX_SETTINGS_ROWS = 8
MAX_SETTINGS_CHARS = 400
MAX_SANDBOX_MATCHES = 3
MAX_SANDBOX_CHARS = 1200
MAX_CONVERSATION_TURNS = 4
MAX_CONVERSATION_CHARS = 800
MAX_APPS_SCANNED = 2000  # safety cap for the fuzzy entity scan

_WORD_RE = re.compile(r"[a-z0-9]{2,}")

# Generic words that carry no retrieval signal (kept tiny on purpose — the
# query text itself is usually already keyword-shaped).
_STOPWORDS = frozenset(
    {
        "the",
        "a",
        "an",
        "and",
        "or",
        "to",
        "of",
        "for",
        "on",
        "in",
        "is",
        "are",
        "me",
        "my",
        "you",
        "it",
        "this",
        "that",
        "with",
        "how",
        "what",
        "when",
        "where",
        "why",
        "who",
        "please",
        "can",
        "could",
        "would",
        "should",
        "do",
        "does",
        "did",
        "get",
        "take",
        "give",
        "tell",
        "about",
        "from",
        "at",
        "by",
        "as",
    }
)


def _keywords(query: str, limit: int = 8) -> list[str]:
    """Content keywords of a query, longest first (longest = most specific)."""
    words = [w for w in _WORD_RE.findall((query or "").lower()) if w not in _STOPWORDS]
    words.sort(key=len, reverse=True)
    seen: list[str] = []
    for w in words:
        if w not in seen:
            seen.append(w)
        if len(seen) >= limit:
            break
    return seen


def _clip(text: str, limit: int) -> str:
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "\u2026"


# Substrings that mark a settings key as a secret. The settings table holds
# user preferences today, but nothing structurally prevents a secret from
# being stored there — and the retriever feeds settings into prompts, so the
# guard costs nothing and is future-proof (mirrors the personal_context
# skill's SECRET_FIELDS hard-block).
_SECRET_HINTS = (
    "password",
    "passwd",
    "secret",
    "token",
    "api_key",
    "apikey",
    "credential",
    "cvv",
    "credit_card",
    "card_number",
    "ssn",
    "aadhaar",
)

_SECRET_FIELDS_CACHE: frozenset[str] | None = None


def _secret_fields() -> frozenset[str]:
    """The personal_context skill's SECRET_FIELDS (empty when unavailable)."""
    global _SECRET_FIELDS_CACHE
    if _SECRET_FIELDS_CACHE is None:
        try:
            from skills.personal_context.fields import SECRET_FIELDS

            _SECRET_FIELDS_CACHE = SECRET_FIELDS
        except Exception:
            _SECRET_FIELDS_CACHE = frozenset()
    return _SECRET_FIELDS_CACHE


def _is_secret_key(key: str) -> bool:
    """True when a settings key looks like a secret and must never reach a prompt."""
    lowered = (key or "").lower()
    if any(hint in lowered for hint in _SECRET_HINTS):
        return True
    return lowered in _secret_fields()


@dataclass
class Source:
    """One retrieved source, tagged for logging and prompt attribution."""

    name: str  # "memory" | "command_history" | "settings" | "knowledge" |
    #           "sandbox" | "conversation"
    kind: str  # "sql" | "keyword" | "fuzzy" | "index"
    duration_ms: float = 0.0
    count: int = 0
    detail: dict = field(default_factory=dict)


@dataclass
class Context:
    """Bounded retrieval result handed to the model (never a raw DB dump)."""

    text: str = ""
    sources: list[Source] = field(default_factory=list)
    total_chars: int = 0
    duration_ms: float = 0.0

    def as_dict(self) -> dict:
        """Compact log/diagnostic form (no retrieved content, just metadata)."""
        return {
            "duration_ms": round(self.duration_ms, 2),
            "total_chars": self.total_chars,
            "sources": [
                {
                    "name": s.name,
                    "kind": s.kind,
                    "count": s.count,
                    "duration_ms": round(s.duration_ms, 2),
                }
                for s in self.sources
            ],
        }


def _sql_available() -> bool:
    """True when the SQLite layer can be used (best-effort, cached per call)."""
    try:
        import database.manager  # noqa: F401

        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Per-store retrieval
# ---------------------------------------------------------------------------


def _retrieve_memory(db, keywords: list[str]) -> tuple[list[str], list[Source]]:
    """/remember facts (knowledge_memory), keyword-matched first."""
    started = time.perf_counter()
    facts: list[dict] = []
    try:
        rows = db.fetch_all(
            "SELECT key, value FROM knowledge_memory ORDER BY updated_at DESC LIMIT ?",
            (MAX_APPS_SCANNED,),
        ) or []
    except Exception as e:
        logger.debug("retriever: memory query failed: %s", e)
        return [], [Source(name="memory", kind="sql", duration_ms=_ms(started), count=0)]

    lowered = [(str(r.get("key", "")), str(r.get("value", ""))) for r in rows]
    matched = [
        (k, v)
        for k, v in lowered
        if any(kw in k.lower() or kw in v.lower() for kw in keywords)
    ]
    chosen = matched[:MAX_MEMORY_FACTS] or lowered[:MAX_MEMORY_FACTS]
    facts = [f"{k}: {v}" for k, v in chosen]
    return facts, [
        Source(
            name="memory",
            kind="sql",
            duration_ms=_ms(started),
            count=len(facts),
            detail={"matched": len(matched), "total": len(lowered)},
        )
    ]


def _retrieve_history(db, keywords: list[str]) -> tuple[list[str], list[Source]]:
    """Recent command_history rows, keyword-matched first, newest first."""
    started = time.perf_counter()
    try:
        rows = db.fetch_all(
            "SELECT command, action, target, success, timestamp FROM command_history "
            "ORDER BY id DESC LIMIT ?",
            (MAX_APPS_SCANNED,),
        ) or []
    except Exception as e:
        logger.debug("retriever: history query failed: %s", e)
        return [], [
            Source(name="command_history", kind="sql", duration_ms=_ms(started), count=0)
        ]

    lines_all = [
        f"{str(r.get('command', ''))[:120]} -> {r.get('action', '')} "
        f"{r.get('target', '')} ({'ok' if r.get('success') else 'failed'})"
        for r in rows
    ]
    matched = [
        line
        for line in lines_all
        if any(kw in line.lower() for kw in keywords)
    ]
    chosen = matched[:MAX_HISTORY_ROWS] or lines_all[:MAX_HISTORY_ROWS]
    text = "\n".join(f"- {line}" for line in chosen)
    return [_clip(text, MAX_HISTORY_CHARS)], [
        Source(
            name="command_history",
            kind="sql",
            duration_ms=_ms(started),
            count=len(chosen),
            detail={"matched": len(matched)},
        )
    ]


def _retrieve_settings(db) -> tuple[list[str], list[Source]]:
    """Non-secret settings keys (names + short values; keys are user prefs).

    Secret-looking keys (password/token/api_key/...) are withheld entirely
    and only reported by count — their values never reach a prompt.
    """
    started = time.perf_counter()
    try:
        rows = db.fetch_all(
            "SELECT key, value FROM settings ORDER BY key LIMIT ?", (MAX_SETTINGS_ROWS,)
        ) or []
    except Exception as e:
        logger.debug("retriever: settings query failed: %s", e)
        return [], [Source(name="settings", kind="sql", duration_ms=_ms(started), count=0)]

    lines: list[str] = []
    withheld = 0
    for r in rows:
        key = str(r.get("key", ""))
        if _is_secret_key(key):
            withheld += 1
            continue
        lines.append(f"{key}: {_clip(str(r.get('value', '')), 60)}")
    if withheld:
        lines.append(f"({withheld} secret-looking setting(s) withheld)")
    return lines, [
        Source(
            name="settings",
            kind="sql",
            duration_ms=_ms(started),
            count=len(lines),
            detail={"withheld": withheld},
        )
    ]


def _retrieve_knowledge(query: str) -> tuple[list[str], list[Source]]:
    """Applications + websites via the EntityResolver's own store (fuzzy)."""
    started = time.perf_counter()
    try:
        from knowledge.manager import get_manager

        manager = get_manager()
    except Exception as e:
        logger.debug("retriever: knowledge manager unavailable: %s", e)
        return [], [Source(name="knowledge", kind="fuzzy", duration_ms=_ms(started), count=0)]

    lowered = (query or "").lower()
    lines: list[str] = []

    # Websites: names/aliases/URLs are tiny — match by substring.
    try:
        for site in manager.load_websites():
            name = str(site.get("name", ""))
            aliases = " ".join(str(a) for a in site.get("aliases", []) or [])
            url = str(site.get("url", ""))
            hay = f"{name} {aliases} {url}".lower()
            if name.lower() in lowered or any(kw in hay for kw in _keywords(query, 12)):
                lines.append(f"website {name}: {url}")
            if len(lines) >= MAX_ENTITIES:
                break
    except Exception as e:
        logger.debug("retriever: websites unavailable: %s", e)

    # Applications: use the resolver's token-overlap scoring over the flat
    # app list (mirrors EntityResolver's RapidFuzz use, but cheap and inline
    # so retrieval never depends on resolver state).
    try:
        apps = manager.load_applications()
        query_words = set(_keywords(query, 12))
        scored: list[tuple[float, str]] = []
        for app in apps[:MAX_APPS_SCANNED]:
            name = str(app.get("name", ""))
            aliases = [str(a) for a in app.get("aliases", []) or []]
            words = {w.lower() for w in _WORD_RE.findall(f"{name} {' '.join(aliases)}")}
            overlap = len(words & query_words)
            if overlap:
                status = app.get("app_status", "")
                scored.append((overlap, f"app {name} ({status})"))
        scored.sort(key=lambda pair: -pair[0])
        lines.extend(line for _, line in scored[: max(0, MAX_ENTITIES - len(lines))])
    except Exception as e:
        logger.debug("retriever: applications unavailable: %s", e)

    count = len(lines)
    return lines, [
        Source(name="knowledge", kind="fuzzy", duration_ms=_ms(started), count=count)
    ]


def _retrieve_sandbox(query: str, sandbox) -> tuple[list[str], list[Source]]:
    """Past Hermes tasks whose normalized query shares keywords with this one."""
    started = time.perf_counter()
    if sandbox is None:
        return [], [Source(name="sandbox", kind="index", duration_ms=_ms(started), count=0)]
    try:
        index = json.loads(sandbox.index_path.read_text(encoding="utf-8"))
    except Exception:
        return [], [Source(name="sandbox", kind="index", duration_ms=_ms(started), count=0)]

    query_words = set(_keywords(query, 10))
    matches: list[tuple[int, str, str]] = []
    for past_query, records in index.items():
        past_words = set(_keywords(past_query, 10))
        overlap = len(query_words & past_words)
        if not overlap or not records:
            continue
        rec = records[-1]  # newest record for that query
        status = rec.get("status", "?")
        matches.append(
            (
                overlap,
                str(past_query)[:100],
                f'"{str(rec.get("prompt", past_query))[:90]}" -> {status} '
                f'({"last 60 chars: " + _clip(str(rec.get("tool_used", "")), 40) or "no tool"})',
            )
        )
    matches.sort(key=lambda m: -m[0])
    lines = [f"past task {q}: {d}" for _, q, d in matches[:MAX_SANDBOX_MATCHES]]
    text = _clip("\n".join(lines), MAX_SANDBOX_CHARS) if lines else ""
    return ([text] if text else []), [
        Source(name="sandbox", kind="index", duration_ms=_ms(started), count=len(lines))
    ]


def _retrieve_conversation(
    session_id: str | None, store=None
) -> tuple[list[str], list[Source]]:
    """The last few turns of this session (already persisted by Hermes)."""
    started = time.perf_counter()
    if not session_id:
        return [], [Source(name="conversation", kind="sql", duration_ms=_ms(started), count=0)]
    try:
        if store is None:
            from hermes.conversation import get_conversation_store

            store = get_conversation_store()

        history = store.get_history(session_id)
    except Exception as e:
        logger.debug("retriever: conversation unavailable: %s", e)
        return [], [Source(name="conversation", kind="sql", duration_ms=_ms(started), count=0)]

    turns = history[-MAX_CONVERSATION_TURNS:]
    lines = [f"{t.get('role', '?')}: {_clip(str(t.get('content', '')), 120)}" for t in turns]
    text = _clip("\n".join(lines), MAX_CONVERSATION_CHARS) if lines else ""
    return ([text] if text else []), [
        Source(name="conversation", kind="sql", duration_ms=_ms(started), count=len(turns))
    ]


def _ms(started: float) -> float:
    return (time.perf_counter() - started) * 1000


# ---------------------------------------------------------------------------
# Public retriever
# ---------------------------------------------------------------------------


class Retriever:
    """Hybrid retriever over Sarthi's existing stores.

    Args:
        sandbox: TaskSandbox for past-task lookup (None disables that source).
        db: DatabaseManager override (None uses the project-wide singleton).
            Used by tests and callers with an isolated database.
        conversation_store: ConversationStore override (None uses the global
            singleton). Used by tests and callers with an isolated store.
    """

    def __init__(self, sandbox=None, db=None, conversation_store=None):
        self._sandbox = sandbox
        self._db = db
        self._conversation_store = conversation_store

    def retrieve(self, query: str, session_id: str | None = None) -> Context:
        """Retrieve bounded context for ``query`` from every available store.

        Never raises: every store is individually guarded, so a broken store
        degrades to fewer sources instead of failing the task.
        """
        started = time.perf_counter()
        context = Context()

        keywords = _keywords(query)
        sections: list[str] = []

        # SQL stores (one shared connection when available)
        if _sql_available():
            if self._db is not None:
                db = self._db
            else:
                try:
                    from database.manager import get_database

                    db = get_database()
                except Exception as e:
                    logger.debug("retriever: database unavailable: %s", e)
                    db = None
            if db is not None:
                facts, src = _retrieve_memory(db, keywords)
                context.sources.extend(src)
                if facts:
                    sections.append(
                        "Remembered facts (/remember):\n" + "\n".join(f"- {f}" for f in facts)
                    )

                hist, src = _retrieve_history(db, keywords)
                context.sources.extend(src)
                if hist and hist[0]:
                    sections.append("Recent related commands:\n" + hist[0])

                settings, src = _retrieve_settings(db)
                context.sources.extend(src)
                if settings:
                    sections.append("Saved settings:\n" + "\n".join(f"- {s}" for s in settings))

        # Knowledge entities (apps + websites)
        k_lines, src = _retrieve_knowledge(query)
        context.sources.extend(src)
        if k_lines:
            sections.append("Known entities:\n" + "\n".join(f"- {line}" for line in k_lines))

        # Past Hermes tasks
        sb_lines, src = _retrieve_sandbox(query, self._sandbox)
        context.sources.extend(src)
        if sb_lines and sb_lines[0]:
            sections.append("Similar past Hermes tasks:\n" + sb_lines[0])

        # Session conversation
        conv, src = _retrieve_conversation(session_id, self._conversation_store)
        context.sources.extend(src)
        if conv and conv[0]:
            sections.append("Recent conversation:\n" + conv[0])

        # Enforce the total budget — drop the largest sections last.
        context.text = _assemble(sections, MAX_TOTAL_CHARS)
        context.total_chars = len(context.text)
        context.duration_ms = _ms(started)
        return context


def _assemble(sections: list[str], budget: int) -> str:
    """Join sections, dropping later ones when the budget is exceeded."""
    kept: list[str] = []
    used = 0
    for section in sections:
        if used + len(section) <= budget:
            kept.append(section)
            used += len(section) + 2
        else:
            remaining = budget - used
            if remaining > 200:
                kept.append(_clip(section, remaining))
            break
    return "\n\n".join(kept)
