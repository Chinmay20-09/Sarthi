# Architecture (observed)

This document describes the architecture **as it exists in the code today**.
Every claim is backed by a file path. See [DOCUMENTATION_RULES.md](DOCUMENTATION_RULES.md)
for how this document is maintained.

## The one-sentence version

A FastAPI backend (`Backend/api.py`) receives commands from a tkinter desktop
client or a browser dashboard, runs them through a deterministic NLP pipeline
(`Backend/brain/`), and falls back to a bounded LLM agent (`Backend/hermes/`)
when the deterministic pipeline cannot handle the request.

## Canonical terminology map

Sarthi's architecture uses precise, non-interchangeable roles. This is the
authoritative mapping between the canonical model and the code; every other
document in this tree uses these terms the same way.

| Canonical role | Sarthi implementation | Status | Evidence |
| --- | --- | --- | --- |
| **Sarthi Brain** — deterministic orchestrator | `BrainEngine` (`brain/engine.py`): interpret → plan → resolve → execute over registered skills | IMPLEMENTED | `brain/engine.py` |
| **Hermes** — complex/model-driven orchestrator (NOT interchangeable with the Brain) | `HermesAgent` (`hermes/agent.py`): one bounded reasoning loop (retrieval → model → validated tool call), reached only when deterministic orchestration is insufficient (complexity router, task-shaped escalation) | IMPLEMENTED (escalation path) | `hermes/agent.py`, `hermes/router.py`, `api.py` fallback |
| **Model** — a component used by the complex orchestrator | LLM access via provider manager (local Ollama default) | IMPLEMENTED | `hermes/providers/` |
| **Skill** — capability-oriented subsystem grouping related behaviour | 10 manifest-discovered skills (app_launcher, automation_engine, browser, browser_awareness, natural_language_processor, personal_context, project_tracker, scanner, speech, user_config) | IMPLEMENTED (exactly these 10) | `skills/registry.py`, SKILLS.md |
| **Tool** — specific structured operation exposed to the orchestrator (name, purpose, parameters, semantics — never arbitrary code execution) | 10 registered Hermes tools; model output is parsed, validated (`hermes/validator.py`) and dispatched (`hermes/tool_registry.py`) | IMPLEMENTED | TOOLS.md, `hermes/tools/` |
| **Capability** — abstract ability required to perform an action (terminal, browser, clipboard, filesystem…) | Desktop allow-list of declared, auditable capabilities (APPLICATION_LAUNCH, WINDOW_READ, BROWSER_CONTROL, KEYBOARD, MOUSE, CLIPBOARD, FILESYSTEM_READ/WRITE, PROCESS_CONTROL); `PLANNED_CAPABILITIES` holds declared-but-unregistered ones (WINDOW_CONTROL, SHELL) | IMPLEMENTED (Desktop Hand scope) | `hands/desktop/capabilities.py` |
| **Provider** — concrete implementation of a capability | No separate provider-discovery layer exists. Concrete implementations are the hand's backend modules (`hands/desktop/input.py`, `processes.py`, `windows.py`, `filesystem.py`, `browser.py`) plus browser engines (Selenium/Playwright) and AI providers. There is no runtime capability→provider→Hand registry. | PARTIAL (no discovery/registry) | `hands/desktop/` |
| **Hand** — execution layer: receives validated structured requests, resolves the action, performs the physical operation, returns a structured result. Never reasons. | `DesktopHand` (Windows) behind the `Hand` interface (`hands/base.py`) | IMPLEMENTED (Desktop only) | `hands/desktop/hand.py`, `hands/base.py` |
| **Memory** — private/user context (conversations, preferences, state). NOT the capability registry. | `/remember` facts (`knowledge_memory`), session history (`conversation_messages`, `chat_messages`), task sandbox | IMPLEMENTED | MEMORY.md |
| **Knowledge** — what Sarthi knows about its available capabilities (entities, skills, tools, hands) | Today: the applications/websites entity store + entity resolver. Skills/tools are registered in code (`skills/registry.py`, `hermes/tool_registry.py`), NOT stored in a knowledge registry. A unified capability registry is PLANNED. | PARTIAL | KNOWLEDGE.md, `knowledge/` |
| **Database** — persistent system state | SQLite sarthi.db (10 tables) + sandbox + knowledge JSON. Stores memory/history/settings/projects — NOT skills, tools, capabilities or hands. | IMPLEMENTED (partial scope) | DATABASE.md |
| **Sarthi Server** — server-oriented runtime independent of physical Hands | FastAPI backend hosting Brain + Hermes + Memory + Knowledge + Skills + Tools. It runs on the same machine as the only Hand; no server↔Hand protocol exists. | TARGET (single-machine today) | `api.py`, AD-16 |
| **Android / Browser / IoT Hands** | Not implemented | PLANNED | PROJECT_STATE.md |
| **Capability discovery** (a Hand reports what it can provide) | `DesktopHand.capabilities()` reports statically; no registration/discovery protocol between Brain and Hands | PLANNED (report only) | `hands/base.py` |

### Deterministic-first principle

Sarthi prefers deterministic orchestration whenever a known, validated
capability path exists. Hermes is the escalation path for complexity,
ambiguity and missing deterministic routes — never the default execution
mechanism, and never a physical executor. Hands (today: the Desktop Hand) are
the only execution layers. This principle is the reason the complexity router
runs *after* the deterministic pipeline (and, for task-shaped instructions,
before it only when the interpreter's only reading is a plain search — AD-04).

### Current vs target topology

```
CURRENT:  User → Sarthi Brain → deterministic route (Skill/Tool)
                │ (no deterministic route)
                └→ Hermes (reasoning/planning → tool call → validation)
                          ↓
              structured request → Desktop Hand → provider backend → execution

TARGET:   Sarthi Server (Brain/Hermes/Memory/Knowledge/Skills/Tools)
                ↓ structured request over a protocol (PLANNED)
          registered Hands (Desktop / Android / Browser / IoT) with
          capability discovery: capability → provider → Hand
```

Only the CURRENT half describes code that exists. The TARGET half (server
independence, remote Hands, discovery/registration) is documented as PLANNED
in PROJECT_STATE.md and AD-16 — it is intent, not implementation.

> **2026-09-14 consolidation:** Sarthi owns execution and Hermes provides
> intelligence. There is exactly one Hermes reasoning loop (`HermesAgent`),
> one tool-call gate (`hermes/validator.py`) and one sandbox root
> (`Backend/sandbox`). See [CONSOLIDATION_REPORT.md](CONSOLIDATION_REPORT.md)
> and [ARCHITECTURAL_DECISIONS.md](ARCHITECTURAL_DECISIONS.md).
>
> **2026-09-15 Brain/Hand boundary (AD-16):** Backend = Brain, Desktop = Hand.
> The Brain programs against the `Hand` interface (`hands.base.Hand`); the
> local implementation is `DesktopHand`. See
> [BRAIN_HAND_BOUNDARY_REPORT.md](BRAIN_HAND_BOUNDARY_REPORT.md).

## Runtime architecture (real request flow)

```
User
 │  tkinter Desktop client (Desktop/client/sarthi_client/gui.py, HTTP only)
 │  or web dashboard (Backend/UI/*.html, served at /ui)
 ▼
FastAPI  POST /command            (Backend/api.py:424)
 │    mode commands / conversation mode short-circuit here
 ▼
Sarthi Brain: BrainEngine.process  (Backend/brain/engine.py)
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
| `tests/` | 55 test files, 49 pytest-collected, 1127 tests (all passing 2026-09-16; see TESTING.md) | `pyproject.toml` pythonpath |

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

## Backend = Brain, Desktop = Hand

Sarthi thinks through the Backend (the Sarthi Brain) and acts through the
Desktop Hand:

| | Backend / Brain | Desktop / Hand |
| --- | --- | --- |
| **Owns** | interpretation, complexity routing, Hermes reasoning, memory/knowledge/retrieval, planning, task state, tool selection, action validation, deciding the next step, producing the final response | executing authorized actions (mouse, keyboard, files, apps, browser, processes) and observing device state (windows, processes, clipboard, execution outcomes) |
| **Must never** | touch the OS directly | interpret natural language, call Hermes/LLMs, plan, decide complexity or the next step, accept un-authorized actions |
| **Code** | `brain/`, `hermes/`, `knowledge/`, `skills/` (capability logic), `api.py` | `hands/` (validated OS backends), `Desktop/client/` (HTTP-only shell) |

The contract between them is the **`Hand` interface** (`hands/base.py`):
`execute(action, target, **kwargs) -> dict`, `capabilities()`,
`find_application_process(exe_name)`. Every action is allow-listed and
argument-validated by the hand before anything runs; results are structured
`DesktopResult`-shaped dicts — failures are returned as observations, never
raised.

**Current (local) and target (network) topology** — the Brain's code does not
differ between them (see the canonical terminology map above for the full
CURRENT/TARGET split):

```
CURRENT:  Backend Brain ──in-process──► DesktopHand ──► same computer
TARGET:   Backend Brain ──network protocol──► RemoteDesktopHand ──► target device
```

A `RemoteDesktopHand` is **not implemented**; the interface and the import
boundary (`hands/` imports nothing from `brain`/`hermes`/`knowledge`/`skills` —
locked by `tests/test_brain_hand_boundary.py`) are the prepared ground. Future
protocol work will need: authenticated, authorized request→execution→result
semantics, pairing/registration of a device, and transport security — none of
which exists yet.

Known, documented divergences from the pure boundary: the AI chain keeps its
own low-level control layer (AD-12, deferred) and `webbrowser.open` is called
directly by `skills/browser` and `hermes/tools/open_website.py` (both
validated capability surfaces, neither a second hand).
