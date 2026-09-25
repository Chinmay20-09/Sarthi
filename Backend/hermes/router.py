"""
Complexity Router — the fast/complex gate in front of Sarthi's two paths.

Design rules (locked by tests/test_hermes_router.py):

- The router NEVER loads a model, never does network I/O, never touches the
  database. It is pure text heuristics so the fast path stays fast: routing
  a simple command adds microseconds, not milliseconds.
- Fast-path indicators are the interpreter's own action words plus a small
  high-confidence pattern set. Anything else routes to Hermes, which is the
  safe default: the deterministic pipeline is always tried first inside the
  agent loop, so a wrong "complex" verdict costs a retrieval, not a disaster.
- The router must evolve without hardcoding an enormous list: the keyword
  tables are module constants, designed to be extended, and the agent loop
  still tries the deterministic pipeline first regardless of the verdict.

Public API:
    Route (dataclass)                        — {route, reason, score, signals}
    route_command(text) -> Route             — classify one command
    is_compound(text) -> bool                — "then/after that/and then" detection
    looks_like_url(text) -> bool
    looks_like_task_instruction(text) -> bool — multi-step task, not a command
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Fast-path signals
# ---------------------------------------------------------------------------

# Single-action commands the deterministic pipeline owns. The FIRST word of
# the command decides: "open youtube" (fast) vs "open youtube and get the
# ... prompt" (not fast — an imperative clause follows the target).
_FAST_ACTIONS = frozenset(
    {
        "open",
        "launch",
        "start",
        "run",
        "close",
        "quit",
        "exit",
        "play",
        "search",
        "find",
        "show",
        "list",
        "check",
        "status",
        "sync",
        "scan",
        "refresh",
        "discover",
        "set",
        "configure",
        "clean",
        "cleanup",
        "clear",
        "browse",
        "visit",
        # Terminal commands (TERMINAL capability). Their targets are paths / literal
        # text, so "write hello world to notes.txt" and "create testing.txt" must
        # not be flagged no_action_word and escalated to Hermes — a failed or
        # refused terminal command surfaces its own structured error instantly.
        "cd",
        "echo",
        "create",
        "write",
        "track",
        "pending",
        "update",
        "remember",
        "recall",
        "forget",
        "what",
        "how",
        "why",
        "who",
        "when",
        "where",
        "hello",
        "hi",
        "hey",
    }
)

# High-confidence one-action shapes: "<action> <target>" where the target is
# 1–3 words. Anything longer than 3 words is probably a sentence fragment.
_MAX_FAST_TARGET_WORDS = 3

# Compound connectors (regex fragments joined into _COMPOUND_RE). A bare
# "and" is deliberately NOT a connector: "open X and search/play Y" is the
# interpreter's own fast compound shape and must stay on the fast path.
_COMPOUND_CONNECTORS = (
    r"\bthen\b",
    r"\bafter\s+that\b",
    r"\bafterwards?\b",
    r"\bnext\b",
    r"\bfinally\b",
    r"\bfollowing\s+that\b",
    r"\bonce\s+(?:that|this|it)\b",
    r"\bwhile\s+(?:that|this)\b",
    r"\bmeanwhile\b",
    r"\balso\b",
)

# Copy/paste/data-flow verbs: values move between apps/sites ("take this
# and ...", "copy ... paste ...").
_DATAFLOW_VERBS = frozenset(
    {
        "copy",
        "paste",
        "transfer",
        "send",
        "forward",
        "move",
        "extract",
        "summarize",
        "summarise",
        "write",
        "draft",
        "compose",
        "generate",
        "prepare",
        "translate",
    }
)

# File/document/data work verbs. A sentence that names this kind of work
# ("find all assignment PDFs and rename them") is a task, not a command —
# and definitely not a web-search query to run literally.
_TASK_VERBS = frozenset(
    {
        "rename",
        "organize",
        "organise",
        "categorize",
        "categorise",
        "sort",
        "merge",
        "combine",
        "convert",
        "deduplicate",
        "archive",
        "download",
        "upload",
        "attach",
        "fill",
        "submit",
        "copy",
        "paste",
        "move",
        "extract",
        "summarize",
        "summarise",
        "translate",
    }
)

# A task sentence is usually long. A single task verb in a short sentence
# ("search for sort algorithms") is left alone; two task verbs, or one task
# verb in a sentence of this length or more, is a multi-step instruction.
_TASK_INSTRUCTION_MIN_WORDS = 6

# Signals that describe the shape of a verdict rather than its cause — never
# reported as the route reason when a more specific signal fired.
_GENERIC_SIGNALS = frozenset({"simple_action_word", "long_command"})

# Research/knowledge-work nouns that usually require DB context + reasoning.
_RESEARCH_NOUNS = frozenset(
    {
        "problem",
        "issue",
        "error",
        "bug",
        "latency",
        "performance",
        "architecture",
        "refactor",
        "design",
        "plan",
        "research",
        "compare",
        "analysis",
        "review",
        "solution",
        "prompt",
        "email",
        "document",
        "report",
        "code",
        "project",
        "backend",
        "database",
        "workflow",
    }
)

# A bare domain/URL token ("example.com", "https://x.io/pricing").
_URL_RE = re.compile(
    r"(?:https?://)?(?:www\.)?[a-z0-9-]+(?:\.[a-z0-9-]+){1,}(?:[/:][^\s]*)?",
    re.IGNORECASE,
)

# Compound connectors, precompiled.
_COMPOUND_RE = re.compile("|".join(_COMPOUND_CONNECTORS), re.IGNORECASE)

# Punctuation that may trail tokens (reused for token cleanup).
_TRAILING_PUNCTUATION = ".,!?;:"

# "take this/that/the problem <verb>" — deixis referring to prior context.
_DEIXIS_RE = re.compile(
    r"\b(?:take|bring|give|show|send)\s+(?:this|that|it|the|my)\b", re.IGNORECASE
)

# "ask <AI>/chatgpt/gemini ..." — an AI-interaction request is complex unless
# it is one of the deterministic chain shapes the interpreter already parses.
_ASK_AI_RE = re.compile(
    r"\b(?:ask|tell|check\s+with|consult)\s+(?:chatgpt|chat\s+gpt|gpt|openai|gemini"
    r"|claude|perplexity|grok|copilot|deepseek|the\s+ai)\b",
    re.IGNORECASE,
)

# Question marks after the first sentence — a multi-part request.
_MULTI_QUESTION_RE = re.compile(r"\?.*\?", re.DOTALL)

# The interpreter's deterministic AI-chain shape: "run/chain/automate <query>
# from <AI> to <AI>" is parsed by the automation engine and must stay fast.
# Anchored on the leading action word + a from/to clause (search with ^).
_AI_CHAIN_RE = re.compile(r"\bfrom\b.+\bto\b", re.IGNORECASE | re.DOTALL)

# "<close/quit/exit X> and <open/launch Y>" — two imperative app clauses that
# the interpreter cannot decompose (it only chains open→search/play), so this
# is a genuine two-step task for Hermes.
_APP_IMPERATIVES = {"open", "launch", "start", "run", "close", "quit", "exit", "play"}

# Sequencing/follow-up clauses that continue a task ("wait for it to load,
# then ...", "once it opens, ...") — dependency, not a single action.
_FOLLOWUP_CLAUSE_RE = re.compile(
    r"\b(?:after|once|when)\s+(?:it|that|this|the\s+(?:page|site|app|window))\b",
    re.IGNORECASE,
)

# Vocabulary that marks a "list ..." sentence as belonging to another skill
# (project tracker, memory, skills registry) — mirrors the interpreter's
# blocklist so both layers agree on what stays a filesystem listing.
_TERMINAL_LISTING_BLOCKLIST = frozenset(
    {
        "projects",
        "project",
        "github",
        "repos",
        "repositories",
        "repo",
        "pending",
        "issues",
        "issue",
        "tasks",
        "task",
        "memories",
        "memory",
        "skills",
        "commands",
    }
)


def _terminal_read_shape(raw: str) -> bool:
    """Path/listing shape for read/list/tree terminal commands.

    Mirrors the interpreter's gates so both layers agree: "read
    notes.txt", "list documents", "tree projects" are deterministic
    terminal commands; "read a book" (conversation) and "list pending
    projects" (project tracker) are not.
    """
    tokens = _tokens(raw)
    if len(tokens) < 2:
        return True  # "read"/"list"/"tree" alone -> terminal usage hint
    verb = tokens[0]
    rest = tokens[1:]
    first = rest[0]
    if first in {"file", "directory", "dir"} or first.startswith("/"):
        return True
    if "/" in first or "\\" in first or "." in first.rstrip("."):
        return True  # separator or extension in the first path token
    if first in _TERMINAL_LISTING_BLOCKLIST:
        # "tree" has no other claimant — the tracker never sees it.
        return verb == "tree" and len(rest) == 1
    return len(rest) == 1  # single plain word ("list documents")


@dataclass
class Route:
    """Result of the complexity router.

    Attributes:
        route: "fast" or "hermes".
        reason: Stable machine-readable reason (e.g. "simple_command",
            "multi_step_task").
        score: Heuristic complexity score (>= 1 means complex).
        signals: The individual indicators that fired (for logging/tests).
    """

    route: str
    reason: str
    score: int = 0
    signals: list[str] = field(default_factory=list)


def _tokens(text: str) -> list[str]:
    """Lowercased tokens without trailing punctuation."""
    return [t.lower().rstrip(_TRAILING_PUNCTUATION) for t in (text or "").split()]


def _strip_leading_slash(tokens: list[str]) -> list[str]:
    """ "/remember x" behaves like "remember x" for routing."""
    if tokens and tokens[0].startswith("/"):
        tokens = list(tokens)
        tokens[0] = tokens[0][1:]
    return tokens


def looks_like_url(text: str) -> bool:
    """Best-effort URL/domain check (mirrors the interpreter's notion)."""
    token = (text or "").strip().rstrip(_TRAILING_PUNCTUATION)
    return bool(token) and _URL_RE.fullmatch(token) is not None


def is_compound(text: str) -> bool:
    """True when the text joins clauses with sequencing/dependency words."""
    return bool(_COMPOUND_RE.search(text or ""))


def looks_like_task_instruction(text: str) -> bool:
    """True when a sentence describes multi-step work instead of one command.

    Used by the /command gate: "find all assignment PDFs and rename them
    according to subject" must not be answered by literally searching the web
    for its own words. Two task verbs, or one task verb in a sentence of
    ``_TASK_INSTRUCTION_MIN_WORDS`` words or more, marks a task instruction.
    Plain commands ("open youtube and search lofi") are never affected.

    Args:
        text: The raw user input.

    Returns:
        True when the sentence reads as a task, not a single command.
    """
    tokens = _strip_leading_slash(_tokens(text))
    if not tokens:
        return False
    task_verbs = set(tokens) & _TASK_VERBS
    if not task_verbs:
        return False
    return len(task_verbs) >= 2 or len(tokens) >= _TASK_INSTRUCTION_MIN_WORDS


def route_command(text: str) -> Route:
    """Classify one command for the fast/complex gate.

    The command is fast-path when ALL of:
      - the first meaningful word is a known single action/question word,
      - the command is short (<= _MAX_FAST_TARGET_WORDS target words),
      - no compound connector, data-flow verb, research noun, AI interaction,
        deixis, or second question is present.

    Anything else routes to Hermes ("hermes"). The deterministic pipeline is
    still attempted first inside the agent loop, so a conservative "complex"
    verdict never skips the fast path — it only adds retrieval first.
    """
    raw = (text or "").strip()
    signals: list[str] = []
    score = 0

    if not raw:
        return Route(route="fast", reason="empty_input", score=0, signals=[])

    tokens = _strip_leading_slash(_tokens(raw))

    # --- fast indicators -------------------------------------------------
    first = tokens[0] if tokens else ""
    if first in _FAST_ACTIONS:
        score -= 1
        signals.append("simple_action_word")
    else:
        score += 2
        signals.append("no_action_word")

    # --- complex indicators ----------------------------------------------
    if is_compound(raw):
        score += 2
        signals.append("compound_connector")

    words = set(tokens)
    dataflow = words & _DATAFLOW_VERBS
    if dataflow:
        score += 2
        signals.append("dataflow_verb:" + ",".join(sorted(dataflow)))

    nouns = words & _RESEARCH_NOUNS
    if nouns:
        score += 1
        signals.append("research_noun:" + ",".join(sorted(nouns)))

    if _ASK_AI_RE.search(raw):
        score += 3
        signals.append("ai_interaction")

    if _DEIXIS_RE.search(raw):
        score += 2
        signals.append("deixis_reference")

    if _MULTI_QUESTION_RE.search(raw):
        score += 1
        signals.append("multiple_questions")

    if _FOLLOWUP_CLAUSE_RE.search(raw):
        score += 2
        signals.append("followup_clause")

    # A task-shaped sentence (file/document work) is never a literal command.
    # It is also the shape the interpreter most often mis-reads as a web
    # search, so the router must call it complex even when its first word is
    # a known action ("find all assignment PDFs and rename them").
    if looks_like_task_instruction(raw):
        score += 2
        signals.append("task_instruction")

    # "<imperative X> and <imperative Y>" — two app clauses the interpreter
    # cannot decompose (it only chains open→search/play), so it is a genuine
    # two-step task. "open X and search/play Q" stays fast.
    if first in _APP_IMPERATIVES:
        rest = tokens[1:]
        if "and" in rest:
            after_and = rest[rest.index("and") + 1 :]
            if after_and and after_and[0] in _APP_IMPERATIVES - {"play"}:
                score += 2
                signals.append("dependent_open_chain")

    # The deterministic AI-chain shape ("run X from chatgpt to gemini") is
    # parsed by the automation engine — do NOT let its research-ish nouns or
    # length push it to Hermes. The check comes after scoring so it can veto
    # the long_command/complex verdicts.
    if first in {"run", "chain", "automate"} and _AI_CHAIN_RE.search(raw):
        return Route(route="fast", reason="deterministic_ai_chain", score=0, signals=signals)

    # Terminal command prefixes (cd / echo / create / write / read / list /
    # tree): the interpreter parses these deterministically and the terminal
    # skill answers every one — success or a structured usage error — in
    # milliseconds. They must never be escalated to Hermes for their
    # data-flow-ish verbs ("write") or length ("echo hello to notes.txt"):
    # a refused terminal command surfaces its own error instantly instead of
    # a slow model round-trip. read/list/tree only veto when the rest of the
    # sentence is path/listing-shaped (see _terminal_read_shape).
    if first in {"cd", "echo", "create", "write"} or (
        first in {"read", "list", "tree"} and _terminal_read_shape(raw)
    ):
        return Route(
            route="fast", reason="deterministic_terminal_command", score=0, signals=signals
        )

    # Long single-action commands tend to be sentences, not commands.
    if first in _FAST_ACTIONS and len(tokens) > _MAX_FAST_TARGET_WORDS + 1:
        score += 1
        signals.append("long_command")

    # --- verdict ----------------------------------------------------------
    if score >= 1:
        # Report the most specific signal as the reason: "simple_action_word"
        # on a hermes verdict only says the first word looked like a command,
        # which is exactly the case that confuses operators.
        reason = next(
            (s.split(":")[0] for s in signals if s.split(":")[0] not in _GENERIC_SIGNALS),
            signals[0].split(":")[0] if signals else "complex_task",
        )
        return Route(route="hermes", reason=reason, score=score, signals=signals)

    return Route(route="fast", reason="simple_command", score=0, signals=signals)
