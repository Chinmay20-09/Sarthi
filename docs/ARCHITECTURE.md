# Architecture (observed)

This document describes the architecture **as it exists in the code today**.
Every claim is backed by a file path. See [DOCUMENTATION_RULES.md](DOCUMENTATION_RULES.md)
for how this document is maintained.

## The one-sentence version

A FastAPI backend (`Backend/api.py`) receives commands from a tkinter desktop
client or a browser dashboard, runs them through a deterministic NLP pipeline
(`Backend/brain/`), and falls back to a bounded LLM agent (`Backend/hermes/`)
when the deterministic pipeline cannot handle the request.

> **2026-09-14 consolidation:** Sarthi owns execution and Hermes provides
> intelligence. There is exactly one Hermes reasoning loop (`HermesAgent`),
> one tool-call gate (`hermes/validator.py`) and one sandbox root
> (`Backend/sandbox`). See [CONSOLIDATION_REPORT.md](CONSOLIDATION_REPORT.md)
> and [ARCHITECTURAL_DECISIONS.md](ARCHITECTURAL_DECISIONS.md).

## Runtime architecture (real request flow)

```
User
 │  tkinter Desktop client (Desktop/client/sarthi_client/gui.py, HTTP only)
 │  or web dashboard (Backend/UI/*.html, served at /ui)
 ▼
FastAPI  POST /command            (Backend/api.py:424)
 │    mode commands / conversation mode short-circuit here
 ▼
BrainEngine.process(text)         (Backend/brain/engine.py)
 │    1. Interpreter   interpret_many(text)      (brain/interpreter.py)
 │    2. Planner       plan(intent)  [pass-through]  (brain/planner.py)
 │    3. Resolver      EntityResolver.resolve(target) (knowledge/entity_resolver.py)
 │    4. Executor      BrainExecutor.execute(intent)  (brain/executor.py)
 │           ├── built-in handlers: open, close, browse, remember, recall, forget, clean
 │           └── registered skills (skills/registry.py), fallback skill LAST
 ▼
complexity gate / fallback        (api.py; hermes/router.py)
 │    (a) BEFORE execution: a task-shaped instruction whose only reading is
 │        a plain web search goes straight to Hermes (fast path disabled)
 │    (b) AFTER a failure: the router classifies the raw text and, when it is
 │        complex, the same Hermes loop runs (heuristic score, no model)
 ▼
HermesAgent.run(query)            (Backend/hermes/agent.py — the ONE loop)
 │    1. deterministic fast path (BrainEngine again)
 │    2. hybrid retrieval (hermes/retriever.py — SQL + knowledge + sandbox + history)
 │    3. bounded loop: model → tool call → validate (hermes/validator.py)
 │       → ToolRegistry.execute (hermes/tool_registry.py) → repeat
 ▼
response dict → _client_envelope  → client / dashboard
        plus: command_completed event → voice reply (utils/spoken_replies.py)
```

## Module architecture

| Package | Role | Evidence |
| --- | --- | --- |
| `Backend/api.py` | FastAPI app, all HTTP endpoints, `/command` pipeline, complexity fallback | 1956 lines, 46 routes |
| `Backend/brain/` | Deterministic pipeline: interpreter, planner, resolver wiring, executor, response models, chat modes, wordfinder | `brain/engine.py` is the single entry point |
| `Backend/knowledge/` | Applications/websites JSON store, fuzzy entity resolver, long-term memory, cache | `knowledge/manager.py` singleton |
| `Backend/skills/` | 10 discoverable skills + registry (manifest-based) | `skills/registry.py` |
| `Backend/hermes/` | LLM layer: providers, orchestrator, bounded agent loop, tool bridge, router, sandbox, conversation store | `hermes/service.py` wires it |
| `Backend/hands/` | Desktop execution layer (Windows): input, filesystem, processes, windows, browser, capability report | `hands/desktop/hand.py` |
| `Backend/connectors/` | Third-party service connectors (Google Calendar only) + registry | `connectors/registry.py` |
| `Backend/database/` | SQLite manager, schema, browser-profile store, in-memory browser cache | `database/manager.py` |
| `Backend/events/` | In-process pub/sub event bus | `events/bus.py` |
| `Backend/speech/` | Voice input (sounddevice recorder + faster-whisper STT) | `speech/recorder.py` |
| `Backend/skills/speech/` | Speech skill wrapping the above for the brain pipeline | `skills/speech/main.py` |
| `Backend/utils/` | logger, voice announcements (TTS), spoken replies responder, test telemetry | `utils/voice.py`, `utils/spoken_replies.py` |
| `Backend/UI/` | Static dashboard (7 HTML pages + components), served at `/ui` | `api.py:87` |
| `Desktop/client/` | tkinter client, HTTP-only boundary (`backend.py`), controller, GUI | `Desktop/client/sarthi_client/__init__.py` |
| `tests/` | 52 pytest files, 1021 tests (all passing at documentation time) | `pyproject.toml` pythonpath |

## Dependency architecture

**Client/backend boundary (hard rule, test-locked by `tests/test_architecture_boundaries.py`):**
the Desktop client never imports `brain`, `interpreter`, `model`, `knowledge`,
or backend internals. It talks HTTP only through
`Desktop/client/sarthi_client/backend.py`.

**Inside the backend:**

- `brain/` imports `knowledge/` (resolver) and dispatches to `skills/` via the
  registry; it never imports `hermes/`.
- The NLP fallback *skill* (`skills/natural_language_processor/`) imports
  `hermes.service.chat` — the only brain-side path into the LLM layer.
- `hermes/` tools delegate to existing capabilities (`skills.browser`,
  `skills.app_launcher`, `skills.browser_awareness`, `knowledge.memory`,
  `connectors`) — no parallel execution system.
- `hands/desktop` is called by the `close` executor handler and is designed as
  a standalone agent seam (`Backend/desktop_agent.py`), no IPC implemented.
- `utils/voice` + `utils/spoken_replies` are leaf utilities (imported by
  ai_chain, browser_awareness, api.py startup).

## Data flow (important structures)

| Structure | Produced by | Consumed by | Defined in |
| --- | --- | --- | --- |
| `Intent(action, target, site, confidence, raw_text)` | interpreter | planner, resolver, executor, every skill | `brain/intent.py` |
| `BrainResponse` / `to_api_dict()` | BrainEngine | api.py, CLI, Hermes fast path | `brain/response.py` |
| `Task(prompt, task_type, history, memory)` | Hermes paths | providers, orchestrator, sandbox | `hermes/models.py` |
| `ProviderResponse(success, text, provider, model, tool_used, error)` | providers | orchestrator, agent, sandbox | `hermes/providers/base.py` |
| `Route(route, reason, score, signals)` | complexity router | api.py fallback, agent | `hermes/router.py` |
| `ChainRequest` / `ChainOutcome` | ai_chain parsing | automation skill, chain runner, sandbox | `ai_chain/models.py` |
| `Event(name, data, source)` | any publisher | event bus handlers | `events/bus.py` |
| `DesktopRequest`/`DesktopResult` dicts | callers | DesktopHand.execute | `hands/desktop/models.py` |

## Control flow — who decides what

| Decision | Decider | Evidence |
| --- | --- | --- |
| Intent parsing | `brain/interpreter.py` (regex + keyword tables, deterministic) | `interpret_many()` |
| Multi-step planning | `brain/planner.py` — **pass-through**, returns `[intent]` | `planner.py:36-48` |
| Entity resolution | `knowledge/entity_resolver.py` (rapidfuzz) | `resolve()` |
| Execution dispatch | `brain/executor.py`: built-in handlers → default handler → skills (fallback NLP last) | `execute()` |
| Complexity routing | `hermes/router.py` heuristics; consulted before execution for task-shaped instructions and after a failed deterministic run (`api.py`) | `route_command()`, `looks_like_task_instruction()` |
| Tool selection (complex path) | the LLM, parsed by `hermes/agent.py` (`parse_tool_call`), validated by `hermes/validator.py` | `_loop()` |
| Failure handling | pipeline: fail-fast per step (`engine._execute_plan`); agent: bounded retries + refusal feedback | `agent.py:305-315` |
| Conversation mode | `brain/modes.py` — skips the brain pipeline entirely | `api.py:355-360` |
