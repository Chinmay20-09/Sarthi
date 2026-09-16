# Architecture

This is the main technical architecture document for Sarthi. It describes the
system **as it exists in the code today**; every claim is backed by a file
path. Plans and unfinished work live in [PROJECT_STATE.md](PROJECT_STATE.md).

Sources consolidated here (2026-09-16, now archived in
`docs/archive/documentation-reset-2026-09/`): ARCHITECTURE, RUNTIME_FLOW,
MODULE_MAP, DATA_FLOW, SKILLS, TOOLS, AGENTS, AUTOMATION, CHAINING,
BROWSER_AUTOMATION, KNOWLEDGE, MEMORY, DATABASE, API.

## The one-sentence version

A FastAPI backend (`Backend/api.py`) receives commands from a tkinter desktop
client or a browser dashboard, runs them through a deterministic NLP pipeline
(`Backend/brain/`), and falls back to a bounded LLM agent (`Backend/hermes/`)
when the deterministic pipeline cannot handle the request.

## Canonical terminology map

Sarthi's architecture uses precise, non-interchangeable roles. This is the
authoritative mapping between the canonical model and the code.

| Canonical role | Sarthi implementation | Status | Evidence |
| --- | --- | --- | --- |
| **Sarthi Brain** — deterministic orchestrator | `BrainEngine` (`brain/engine.py`): interpret → plan → resolve → execute over registered skills | IMPLEMENTED | `brain/engine.py` |
| **Hermes** — complex/model-driven orchestrator (NOT interchangeable with the Brain) | `HermesAgent` (`hermes/agent.py`): one bounded reasoning loop (retrieval → model → validated tool call), reached only when deterministic orchestration is insufficient (complexity router, task-shaped escalation) | IMPLEMENTED (escalation path) | `hermes/agent.py`, `hermes/router.py`, `api.py` fallback |
| **Model** — a component used by the complex orchestrator | LLM access via provider manager (local Ollama default) | IMPLEMENTED | `hermes/providers/` |
| **Skill** — capability-oriented subsystem grouping related behaviour | 11 manifest-discovered skills (see [Skills](#skills-11) below) | IMPLEMENTED (exactly these 11) | `skills/registry.py` |
| **Tool** — specific structured operation exposed to the orchestrator (name, purpose, parameters, semantics — never arbitrary code execution) | 11 registered Hermes tools; model output is parsed (`hermes/tool_planner.py`), validated (`hermes/validator.py`) and dispatched (`hermes/tool_registry.py`) | IMPLEMENTED | `hermes/tools/` |
| **Capability** — abstract ability required to perform an action (terminal, browser, clipboard, filesystem…) | Desktop allow-list of declared, auditable capabilities (APPLICATION_LAUNCH, WINDOW_READ, BROWSER_CONTROL, KEYBOARD, MOUSE, CLIPBOARD, FILESYSTEM_READ/WRITE, PROCESS_CONTROL, TERMINAL); `PLANNED_CAPABILITIES` holds declared-but-unregistered ones (WINDOW_CONTROL, SHELL) | IMPLEMENTED (Desktop Hand scope) | `hands/desktop/capabilities.py` |
| **Provider** — concrete implementation of a capability | No separate provider-discovery layer exists. Concrete implementations are the hand's backend modules (`hands/desktop/input.py`, `processes.py`, `windows.py`, `filesystem.py`, `browser.py`) plus browser engines (Selenium/Playwright) and AI providers. There is no runtime capability→provider→Hand registry. | PARTIAL (no discovery/registry) | `hands/desktop/` |
| **Hand** — execution layer: receives validated structured requests, resolves the action, performs the physical operation, returns a structured result. Never reasons. | `DesktopHand` (Windows) behind the `Hand` interface (`hands/base.py`); reachable locally or over IPC via `hands/local.py::get_desktop_hand()` | IMPLEMENTED (Desktop) | `hands/desktop/hand.py`, `hands/base.py` |
| **Memory** — private/user context (conversations, preferences, state). NOT the capability registry. | `/remember` facts (`knowledge_memory`), session history (`conversation_messages`, `chat_messages`), task sandbox | IMPLEMENTED | [Memory](#memory) |
| **Knowledge** — what Sarthi knows about its available capabilities (entities, skills, tools, hands) | Today: the applications/websites entity store + entity resolver. Skills/tools are registered in code (`skills/registry.py`, `hermes/tool_registry.py`), NOT stored in a knowledge registry. A unified capability registry is PLANNED. | PARTIAL | [Knowledge](#knowledge) |
| **Database** — persistent system state | SQLite sarthi.db (10 tables) + sandbox + knowledge JSON. Stores memory/history/settings/projects — NOT skills, tools, capabilities or hands. | IMPLEMENTED (partial scope) | [Database & storage](#database--storage) |
| **Sarthi Server** — server-oriented runtime independent of physical Hands | FastAPI backend hosting Brain + Hermes + Memory + Knowledge + Skills + Tools. With the Desktop Agent IPC (2026-09-16) the Brain can also run apart from the executing machine via `SARTHI_DESKTOP_AGENT_MODE=remote` | PARTIAL (single machine by default; remote hand implemented) | `api.py`, `hands/remote.py` |
| **Android / Browser / IoT Hands** | Not implemented | PLANNED | [PROJECT_STATE.md](PROJECT_STATE.md) |

### Deterministic-first principle

Sarthi prefers deterministic orchestration whenever a known, validated
capability path exists. Hermes is the escalation path for complexity,
ambiguity and missing deterministic routes — never the default execution
mechanism, and never a physical executor. Hands are the only execution layers.
This principle is the reason the complexity router runs *after* the
deterministic pipeline (and, for task-shaped instructions, before it only when
the interpreter's only reading is a plain search — decision AD-04 in
[archive](../archive/documentation-reset-2026-09/ARCHITECTURAL_DECISIONS.md)).

### Current vs target topology

```
CURRENT (local mode, default):
  User → Sarthi Brain → deterministic route (Skill/Tool)
              │ (no deterministic route)
              └→ Hermes (reasoning/planning → tool call → validation)
                        ↓
            structured request → DesktopHand (in-process) → Windows

CURRENT (remote mode, SARTHI_DESKTOP_AGENT_MODE=remote):
  Brain (any OS) ──HTTP/JSON──▶ Desktop Agent (--server) ──▶ DesktopHand ──▶ Windows

TARGET:  registered Hands (Desktop / Android / Browser / IoT) with
         capability discovery: capability → provider → Hand
```

The remote mode is implemented (`hands/remote.py`, `hands/transport.py`,
`desktop_agent.py --server`); capability discovery and additional Hands are
not (see [PROJECT_STATE.md](PROJECT_STATE.md)).

## Runtime architecture (real request flow)

```
User
 │  tkinter Desktop client (Desktop/client/sarthi_client/gui.py, HTTP only)
 │  or web dashboard (Backend/UI/*.html, served at /ui)
 ▼
FastAPI  POST /command            (Backend/api.py)
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
 │       caps: HERMES_AGENT_MAX_ITERATIONS (default 3), HERMES_AGENT_TIMEOUT (300 s)
 ▼
response dict → _client_envelope  → client / dashboard
        plus: command_completed event → voice reply (utils/spoken_replies.py)
```

### Path 2 details — complex (Hermes) fallback

Reached only when Path 1 returns `success: false` or the request was routed
as a task-shaped instruction.

1. **Complexity router** — `hermes.service.route_command(text)`:
   pure text heuristics (`hermes/router.py`): first-word action credit,
   compound connectors, dataflow verbs, research nouns, AI interaction,
   deixis, multiple questions, follow-up clauses, long-command penalty,
   deterministic AI-chain veto. Config knobs: `HERMES_ROUTER_MODE`
   (auto/always/off) and `HERMES_ROUTER_MIN_SCORE`.
2. **HermesAgent.run** — the single reasoning loop, also used by
   `POST /hermes/chat` via `HermesOrchestrator.process` (there with the fast
   path disabled):
   1. deterministic fast path again (cheap safety net; NLP-source results are
      deliberately not short-circuited)
   2. hybrid retrieval — `hermes/retriever.py` pulls bounded context from
      knowledge_memory, command_history, settings, knowledge entities, the
      sandbox query index and session history. No vector DB; SQL + fuzzy.
   3. bounded loop: build instructions from the query + registered tool list
      → model call via the provider manager (primary + local fallback) →
      `parse_tool_call`; a plain answer ends the loop; otherwise
      `validate_tool_call` (the only tool-call gate) → refusal fed back once →
      `ToolRegistry.execute` → follow-up instructions. Caps:
      `HERMES_AGENT_MAX_ITERATIONS` (default **3**) and
      `HERMES_AGENT_TIMEOUT` (default 300 s).
3. **Sandbox persistence** — every agent run is saved to
   `Backend/sandbox/tasks/<task_id>/` and indexed by query in
   `sandbox/index.json`. Failed runs are kept by `/clean`.
4. On agent failure the original (failed) pipeline result is returned
   unchanged.

### Voice path (input)

`POST /listen` → SpeechSkill (lazy) → `sounddevice` recording →
`faster-whisper` transcription → same mode checks and brain pipeline as text.
The pipeline's own output is tagged `routing == "speech"` so the voice
responder never double-speaks it.

### Automation path (ai_chain)

Commands matching `chain|automate` intents or the deterministic AI-chain shape
dispatch to `AutomationSkill._handle_chain` → `run_ai_chain`
(`Backend/skills/automation_engine/ai_chain/chain.py`): hands-off warning +
countdown → drive AI1 site → hand off AI1's reply via `ai_chain/handoff.py` →
drive AI2 → save every prompt/response to `results/ai_chain/<run>/` and the
Hermes sandbox. Details in [AI chaining](#ai-chaining) below.

## Module map

| Package | Role | Evidence |
| --- | --- | --- |
| `Backend/api.py` | FastAPI app, all HTTP endpoints, `/command` pipeline, complexity fallback | 46 routes |
| `Backend/brain/` | Deterministic pipeline: interpreter, planner, resolver wiring, executor, response models, chat modes, wordfinder | `brain/engine.py` is the single entry point |
| `Backend/knowledge/` | Applications/websites JSON store, fuzzy entity resolver, long-term memory, cache | `knowledge/manager.py` singleton |
| `Backend/skills/` | 11 discoverable skills + registry (manifest-based) | `skills/registry.py` |
| `Backend/hermes/` | LLM layer: providers, orchestrator, bounded agent loop, tool bridge, router, sandbox, conversation store | `hermes/service.py` wires it |
| `Backend/hands/` | Execution layer: `base.py` (Hand interface), `desktop/` (local Windows hand), `local.py` (mode selection), `remote.py` (IPC hand), `transport.py` (IPC client) | `hands/local.py::get_desktop_hand` |
| `Backend/connectors/` | Third-party service connectors (Google Calendar only) + registry | `connectors/registry.py` |
| `Backend/database/` | SQLite manager, schema, browser-profile store, in-memory browser cache | `database/manager.py` |
| `Backend/events/` | In-process pub/sub event bus | `events/bus.py` |
| `Backend/speech/` | Voice input (sounddevice recorder + faster-whisper STT) | `speech/recorder.py` |
| `Backend/skills/speech/` | Speech skill wrapping the above for the brain pipeline | `skills/speech/main.py` |
| `Backend/utils/` | logger, voice announcements (TTS), spoken replies responder, test telemetry | `utils/voice.py`, `utils/spoken_replies.py` |
| `Backend/UI/` | Static dashboard (7 HTML pages + components), served at `/ui` | `api.py` |
| `Desktop/client/` | tkinter client, HTTP-only boundary (`backend.py`), controller, GUI | `Desktop/client/sarthi_client/__init__.py` |
| `tests/` | 56 test files, 50 pytest-collected, 1172 tests (see [TESTING.md](TESTING.md)) | `pyproject.toml` pythonpath |

Backend root files: `config.py` (central constants), `main.py` (voice CLI
loop), `main-test.py` (manual smoke script), `desktop_agent.py` (standalone
hand CLI + IPC server), `reading.py` (hardware metrics), `test_prompts.json`
(60 prompts for `POST /test/run`), `sarthi.bat` (launcher).

## Skills (11)

Discovery: `skills/registry.py` scans `Backend/skills/*/manifest.json`,
instantiates `skills/<id>/main.py` (must export a `BaseSkill` subclass).
`BrainEngine._load_skills` registers every instance with the executor,
sorting fallback skills LAST (`fallback=True` attribute → NLP skill).

| Skill | Entry | What it does | Called by |
| --- | --- | --- | --- |
| app_launcher | `skills/app_launcher/main.py` | Launch desktop applications; favourites gate; needs_decision cards; honours remote mode via `get_desktop_hand()` | executor open handler; Hermes OpenAppTool |
| automation_engine | `skills/automation_engine/main.py` | (a) chain intents → ai_chain; (b) "generate assistant" → BrainAssistant | executor skill walk |
| browser | `skills/browser/main.py` | Open/search/play websites via Knowledge Layer + webbrowser | executor open handler; Hermes tools |
| browser_awareness | `skills/browser_awareness/main.py` | DOM-level inspection + action loop on arbitrary sites | executor browse handler; Hermes BrowserAskTool |
| natural_language_processor | `skills/natural_language_processor/main.py` | Conversational fallback via `hermes.service.chat`; `fallback = True` (registered last) | executor skill walk (last resort) |
| personal_context | `skills/personal_context/main.py` | User's personal context fields | Hermes tool; skill walk |
| project_tracker | `skills/project_tracker/main.py` | GitHub-backed project tracking + prompts | executor skill walk; /projects API |
| scanner | `skills/scanner/main.py` | Scan installed applications into the knowledge base | executor skill walk |
| speech | `skills/speech/main.py` | Record + transcribe voice for POST /listen | api.py /listen |
| terminal | `skills/terminal/main.py` | Terminal-style file commands — cd / echo / create / write — as structured, scoped DesktopHand actions (TERMINAL capability; no shell, no subprocess); relative paths resolve against the tracked cwd | executor skill walk; Hermes TerminalTool |
| user_config | `skills/user_config/main.py` | Set/configure actions (e.g. github_username) | executor skill walk |

Skill contract: input is always an `Intent`; output is always a plain dict —
`{success, status, result, error, handled?}`. `handled: True` means "this
skill owns the intent even though it failed" — the executor stops the skill
walk there. Skills may embed `result.visual` cards (e.g. `open_choice`) that
the UI renders. Enable/disable is runtime state via `/skills/{id}/enable|disable`.

## Tools (the Sarthi Tool Bridge)

The Hermes agent may request only tools registered in`hermes/tool_registry.py`;
`register_default_tools` (`hermes/tools/__init__.py`)
registers exactly these 11. Every tool delegates to an existing Sarthi
capability — none expose shell/code execution. Arguments are validated
(`tool_registry.validate_arguments`) and every call passes the
`hermes/validator.py` gate before dispatch.

| Tool | Delegates to | Purpose |
| --- | --- | --- |
| open_app | AppLauncherSkill | Launch an application |
| open_website | BrowserSkill (+webbrowser fallback for raw URLs) | Open a website |
| close_app | executor close path / Hand | Terminate an application |
| search_web | BrowserSkill search | Web search in browser |
| browser_ask | BrowserAwarenessSkill | High-level objective on a website, DOM-aware |
| history_search | command_history table | Search past commands |
| memory_search | knowledge_memory (/remember facts) | Recall user memories |
| project_get | projects/github_projects tables | Fetch user project context |
| github | project_tracker github client | GitHub data for configured username |
| personal_context | personal_context skill | Personal context fields |
| terminal | terminal skill → DesktopHand TERMINAL/write_file actions | cd / echo / create / write on the user's machine — scoped, structured, no shell |

Mechanics: the LLM sees `name`/`description`/`parameters` (JSON-schema subset)
via `build_decision_instructions` (`hermes/tool_planner.py`). Model output is
parsed by `parse_tool_call`; a `tool_call` object triggers validation →
execution → follow-up prompt; plain text ends the task. Hard caps: 3
iterations (default) and 300 s wall clock; a refused tool call is fed back to
the model exactly once.

**One loop, one protocol:** `hermes/agent.py` (HermesAgent) is the only
model-driven tool loop; `POST /hermes/chat` and the `/command` complex
fallback both run it. `hermes/tool_planner.py` is the shared tool-call
*protocol* (prompts + parser) with no loop of its own.

## Agents

"Agent" means a component that runs a model-driven loop until a goal is met.
Three exist — only one is a Hermes reasoning loop:

| Agent | Location | Trigger | Behaviour |
| --- | --- | --- | --- |
| **HermesAgent** (the production complex-task agent) | `hermes/agent.py` | api.py complexity fallback → `hermes.service.run_task` | fast path (deterministic) → retrieval → N model turns (parse tool call → validate → execute → feed back); bounds: 3 iterations / 300 s |
| **HermesOrchestrator** (NOT a loop) | `hermes/orchestrator.py` | `hermes.service.chat` (conversation mode + NLP fallback), `POST /hermes/chat` | provider wiring + primary/local fallback; `process()` delegates to HermesAgent with the fast path disabled; `chat()` is plain chat, no tools |
| **BrainAssistant** | `skills/automation_engine/assistants/brain_assistant/` | "generate assistant for <skill>" | read-only skill analysis → generates `assistant.json` from manifest.json |
| **Browser Awareness manager loop** | `skills/browser_awareness/manager.py` | `browse` intent or browser_ask tool | open isolated Chrome → DOM snapshot → Hermes inspector observes → schema-validated action → re-inspect; until done/blocked/step limit |

Not agents: `BrainEngine` (deterministic pipeline, no model, no loop),
`hermes/providers/*` (stateless adapters), `speech/` (recording/STT utilities).

## Knowledge

Knowledge is what Sarthi knows about its available capabilities — in the
canonical model: skills, tools, capabilities, providers, hands, supported
entities and the relationships between them. It is distinct from Memory.

**Implemented scope today:** the knowledge layer is the deterministic fact
base for apps and websites (entities + alias resolution). Skills and tools
are registered in code and Desktop capabilities are declared in
`hands/desktop/capabilities.py` — there is **no unified capability registry**
in the knowledge layer, and no known-vs-available separation from a live Hand.
That registry and discovery mechanism are PLANNED.

| Component | Location | Purpose |
| --- | --- | --- |
| KnowledgeManager | `knowledge/manager.py` | `get_manager()` singleton; loads both stores, CRUD, category/favourites management, `find_application`, `add_website` |
| EntityResolver | `knowledge/entity_resolver.py` | rapidfuzz matching of spoken names → canonical names; used by BrainEngine step 3 and the Hermes retriever |
| Loader / cache | `knowledge/loader.py`, `knowledge/cache.py` | JSON loading + caching |

Stores:

- **`applications.json`** — application entities with name, path, aliases,
  category (favourite/ignored/unattended states). Writers: scanner skill,
  /applications/categorize, /applications/run. Readers: AppLauncherSkill,
  EntityResolver, Hermes retriever.
- **`websites.json`** — website entities with URL + aliases. Writers:
  `/websites/search-and-save` (the "search on browser" fallback remembers the
  site so the next open goes direct). Readers: BrowserSkill, EntityResolver,
  retriever.

Data flow:

```
"open yt" ─▶ BrowserSkill ─▶ KnowledgeManager.find_website("yt")
                              └─ alias match ─▶ https://youtube.com ─▶ webbrowser.open
BrainEngine step 3 ─▶ EntityResolver.resolve(target)
                       └─ fuzzy vs entities ─▶ canonical name (context.resolved=True)
```

Kept distinct: the `browser_profiles` SQLite table is NOT knowledge data
(owned by `database/profiles.py`); `knowledge_memory` (user facts) is memory,
not knowledge; skills/tools/capabilities live in their own registries.

## Memory

Memory is Sarthi's private/user context — what it knows about this user,
their past conversations, preferences and task state. It is NOT the
capability registry. The implementation is local-first: data stays in the
machine's SQLite database and sandbox files. No network-isolation or
private-network security guarantee is implemented or claimed (the API binds
0.0.0.0 without authentication — see [PROJECT_STATE.md](PROJECT_STATE.md)
known limitations).

Three distinct memory systems:

1. **Long-term user memory (/remember)** — `knowledge/memory.py` →
   `knowledge_memory` table. Interface: `/remember key: value` (auto-keys
   `note_N`), `/recall [key]`, `/forget key`. Readers: Hermes retriever,
   memory_search tool, `build_memory_prompt()` injected as a system message
   into plain chat, `/memory` API. Deliberately NOT cleared by chat reset.
2. **Conversation memory (sessions)** — two tables, two writers:
   `conversation_messages` (`hermes/conversation.py`; the model's session
   context) and `chat_messages` (`POST /chat`; the rendered UI transcript).
   Both cleared together by `DELETE /chat`. **Intentionally separate** — two
   shapes of the same exchange, neither can represent the other (AD-09).
3. **Task memory (Hermes sandbox)** — `hermes/sandbox.py` →
   `Backend/sandbox/tasks/<task_id>/` + `sandbox/index.json` query index
   under the **one canonical root** (a relative `HERMES_SANDBOX_PATH` is
   resolved against the backend root, never the cwd — AD-01). Every
   Hermes/ai_chain run is saved with prompt, response, trace,
   provider/model/status/duration. Cleanup: `/clean` deletes successful
   tasks, keeps failures; `Backend/scripts/clean_sandbox.py` is the CLI twin.

Retrieval (`hermes/retriever.py`) — hybrid, bounded, no vector DB:
SQL (knowledge_memory LIKE, command_history, settings) + knowledge entities
(exact + fuzzy) + sandbox similar tasks via index.json + recent conversation
turns, assembled into bounded, source-tagged text blocks. Failures degrade to
empty context.

`command_history` records every `/command` input; surfaced via
`GET /command-history`, deletable per entry, searched by the retriever and
history_search tool.

## Database & storage

Primary database: **SQLite** `Backend/database/sarthi.db` (created on first
run; `DEFAULT_DB_PATH` in `database/manager.py`). Owner: `DatabaseManager`
(`get_database()` singleton); schema in `database/models.py` (idempotent
init). The schema stores memory, conversation, history, settings, project,
connector and browser-profile state — **not** skills, tools, capabilities,
providers or hands (those are code-registered at runtime).

| Table | Purpose | Writers | Readers |
| --- | --- | --- | --- |
| `github_projects` | tracked GitHub repos for project tracking | project_tracker skill sync | project_tracker, /projects |
| `github_summary` | cached GitHub summary data | project tracker | /projects/{id} |
| `projects` | user projects (name, github_url, terminal_path) | /projects API | /projects, project_get tool |
| `settings` | key/value user settings (github_username, voice_replies, …) | POST /settings, spoken_replies.set_enabled | GET /settings/{key} |
| `command_history` | every /command input | api.py command path | GET /command-history, retriever, history_search tool |
| `knowledge_memory` | /remember facts (key, value) | executor memory handlers | /memory, retriever, memory_search tool, chat prompt builder |
| `chat_messages` | UI-rendered chat transcript | POST /chat | GET /chat |
| `conversation_messages` | Hermes session turns | hermes/conversation.py | retriever, /hermes chat history |
| `connectors` | connector configs (e.g. google_calendar OAuth tokens) | /connectors API | connector registry |
| `browser_profiles` | persistent Chrome profile rows for browser awareness | database/profiles.py | browser_awareness driver |

File-backed stores:

| Store | Location | Owner | Notes |
| --- | --- | --- | --- |
| Hermes task sandbox | `Backend/sandbox/tasks/<id>/` + `sandbox/index.json` | hermes/sandbox.py | one canonical root, cwd-independent (AD-01); `/clean` prunes successes |
| ai_chain run folders | `Backend/results/ai_chain/<ts>_<slug>/` | ai_chain/storage.py | prompts/responses/images per run |
| Knowledge entities | `Backend/knowledge/*.json` | knowledge/manager.py | apps + websites |
| Skill manifests | `Backend/skills/*/manifest.json` | skills/registry.py | discovery metadata |
| ai_chain calibration | `ai_chain/calibration.json` (git-ignored) | calibrate.py | per-machine site tuning |
| Chrome profiles | `ai_chain/.chrome-profile/`, browser-awareness profile dirs | respective drivers | persistent logins |

In-memory (process-local): `BrowserCache` (`database/cache/browser_cache.py`),
EventBus history (`events/bus.py`, last 100 events, debugging),
chat/test mode (`brain/modes.py`), Hermes orchestrator/sandbox singletons
(`hermes/service.py`).

Access rules observed in code: all SQL goes through
`DatabaseManager.execute/fetch_one/fetch_all` (thread-safe connections);
skills never open SQLite directly; knowledge JSON is only touched via
KnowledgeManager; `Backend/scripts/check_no_db_staged.py` guards against
committing the DB.

## Hands & the Brain/Hand boundary

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

### Implementations of `Hand`

| Implementation | Location | When used |
| --- | --- | --- |
| `DesktopHand` (local, in-process) | `hands/desktop/hand.py` | default — `SARTHI_DESKTOP_AGENT_MODE=local` (or unset); backends: `input.py` (pyautogui stack), `filesystem.py`, `processes.py` (psutil), `windows.py` (pygetwindow/pywin32), `browser.py` |
| `RemoteDesktopHand` (over IPC) | `hands/remote.py` | `SARTHI_DESKTOP_AGENT_MODE=remote`; forwards every action to a Desktop Agent process |

Mode selection lives in `hands/local.py::get_desktop_hand()` — the single
seam the Brain uses; everything above the `Hand` interface never learns which
mode is active.

### Brain ↔ Desktop Agent IPC (implemented 2026-09-16)

```
Brain (any OS)                      Desktop Agent (Windows machine)
DesktopRequest ──HTTP/JSON──▶  desktop_agent.py --server
                               └─▶ DesktopHand.execute()  (same allow-list gate)
DesktopResult ◀──HTTP/JSON───  structured result
```

- **Transport** (`hands/transport.py`): `DesktopAgentClient` (httpx2) —
  `POST /execute` (one DesktopRequest), `GET /health`, `GET /capabilities`.
  Connection failures, timeouts and malformed replies are shaped into
  structured failure results (`error: "transport_unavailable"` /
  `"transport_bad_response"`) so the Brain observes them exactly like a local
  hand failure. Body limit 2 MB (`MAX_BODY_BYTES` in `desktop_agent.py`).
- **Server** (`Backend/desktop_agent.py --server`): stdlib HTTP server (no
  framework dependency), dispatches **only** through the DesktopHand action
  registry — no shell, eval, arbitrary Python or subprocess endpoint.
  One bad request can never crash the server: every handler is wrapped.
- **Validation happens twice**: request shape locally (`DesktopRequest`
  model) and the real allow-list + argument spec at the agent.
- **Cross-platform rule**: `transport.py`/`remote.py` must stay importable on
  Linux/Android — no Windows-only imports (Windows modules stay exclusively
  inside `hands/desktop/`).
- **Configuration**: `SARTHI_DESKTOP_AGENT_HOST` (default 127.0.0.1),
  `SARTHI_DESKTOP_AGENT_PORT` (8765), `SARTHI_DESKTOP_AGENT_TIMEOUT` (30 s),
  `SARTHI_DESKTOP_AGENT_MODE` (local|remote) — env-overridable, defaults in
  `Backend/config.py`. The Desktop Agent binds 0.0.0.0 when accessed from
  another machine (a LAN/local development feature, not a public service).
- Callers: the executor's `close` handler and the app launcher go through
  `get_desktop_hand()`; `desktop_agent.py` also retains the manual CLI modes
  (`--capabilities`, `--self-test`, `--exec`).

This is a LAN/local development boundary: no authentication, no device
pairing, no transport security. Authenticated/authorized request semantics,
pairing/registration and transport security remain future work (see
[PROJECT_STATE.md](PROJECT_STATE.md)).

## AI chaining

AI chaining = send the user's query to one AI website, then feed its reply to
a second AI website, hands-off. Everything lives in
`Backend/skills/automation_engine/ai_chain/`.

- **Chain request**: `ChainRequest(query, ai1, ai2, save_images)` parsed by
  `ai_chain/parsing.py::parse_chain_command` from forms:
  `chain <query> from <AI1> to <AI2>` / `run|automate <query> from <AI1> to <AI2>` /
  `open <AI1> and <query> ... to <AI2>`; no from/to → defaults `chatgpt → gemini`.
- **Steps**: always 2 (AI1 → AI2). A declarative N-step library exists
  (`ai_chain/browser_automation.py`) but has no production caller.
- **Supported sites** (`ai_chain/calibration.py::DEFAULT_SITES`): chatgpt,
  gemini, claude, perplexity, grok, deepseek, copilot (+ aliases mirrored in
  `brain/interpreter.py::_CHAIN_AI_NAMES`).

Execution flow (`ai_chain/chain.py::run_ai_chain`):

1. `resolve_site` both AIs (unknown → failed outcome, saved to sandbox).
2. `execute=None` defers to test mode: dry-run `_plan_only` (no machine
   control) — this is what unit tests and `POST /test/run` exercise.
3. Real run: HANDS-OFF banner + 5 s countdown + TTS announcement; abort via
   Ctrl+Alt+X hotkey or mouse-corner failsafe (`control.py`).
4. Step 1: `WebAiDriver.ask(spec1, query)` — open site, paste prompt, wait for
   reply, Ctrl+A/Ctrl+C capture, `extract_reply` pulls the answer from the
   transcript, saved to `0N_stepN_<site>_response.txt`.
5. Handoff: the prompt for AI2 is the **saved backend copy** of AI1's reply
   (`handoff.load("step1_response")`), not the clipboard.
6. Step 2: same driver against AI2. Optional image download when AI2 is
   image-capable (gemini/grok/copilot).
7. `_finish_and_record` → outcome + sandbox record (success and failure both).

Failure handling: unknown site → immediate failed outcome; AI1 failure →
failed outcome with error recorded; login screen detected → driver reports
(user must log in once in the automation profile); no reply found in
transcript → `needs_awareness` → AwarenessExtractor asks the local Hermes
model to make sense of the page text; user abort → aborted outcome + TTS
"Automation cancelled".

DOM assist: before clicking, `ai_chain/dom.py` (+ `selenium_dom.py` primary,
Playwright fallback) attaches read-only to the automation Chrome, parses page
HTML with BeautifulSoup, locates the affordance (composer/copy/download
button), and converts its bounding box to a window-fraction point for the
controller. If attachment or lookup fails, the driver falls back to the
v1.0 estimate + scan-grid + full-page copy. The coordinate scan grid is
disabled unless `AI_CHAIN_COORDINATE_SCAN=1` (semantic targeting is the
default; AD-11).

The chain is a **capability**, not a second brain: Hermes/tools never call it
directly, and it never executes arbitrary commands (no shell path exists). Its
private control layer (`ai_chain/control.py`) duplicates the low-level input
boundary in `hands/desktop/input.py`; merging them is deferred (AD-12)
because real (non-dry-run) control is untested by the suite.

State & artifacts: run folders `Backend/results/ai_chain/<timestamp>_<slug>/`;
persistent Chrome profile with remembered logins `ai_chain/.chrome-profile/`;
calibration overrides `ai_chain/calibration.json` via
`python -m skills.automation_engine.ai_chain.calibrate`; sandbox
`task_type="ai_chain"`.

## Browser automation

Three distinct browser mechanisms coexist:

| Stack | Where | Mechanism | Used for |
| --- | --- | --- | --- |
| **1. BrowserSkill** (default browser, deterministic) | `skills/browser/main.py` | `webbrowser.open` — the OS default browser; builds search URLs | "open X", "search Y", "play Z" — the deterministic fast path |
| **2. Browser Awareness** (isolated Chrome, DOM-level) | `skills/browser_awareness/` | Selenium (primary) with Playwright fallback (`BROWSER_AWARENESS_DRIVER`); BeautifulSoup; CDP direct-attach mode (`BROWSER_AWARENESS_CDP_URL`); isolated per-session profile by default, persistent profile via `browser_profiles` table / `database/profiles.py` | `browse` intents on non-deterministic domains and the `browser_ask` Hermes tool |
| **3. ai_chain** (automation Chrome + RPA hybrid) | `skills/automation_engine/ai_chain/` | dedicated Chrome with `--remote-debugging-port` + persistent profile; PyAutoGUI drives clicks/typing; DOM assist (v1.5) converts element boxes to window-fraction points; v1.7 `browser_automation.py` DOM engine exists but has **no production caller** | AI chains (ChatGPT → Gemini etc.) |

Notes: Browser Awareness never guesses coordinates. Both Selenium stacks rely
on lazy imports: without the `browser` extra the app imports and tests run
fine (graceful degradation is test-locked). `hands/desktop/browser.py` opens
URLs as a DesktopHand action (used by the close/agent seam, not by the three
stacks above). The deterministic-vs-awareness split for "open a website" is
intentional, decided in the interpreter (`_DETERMINISTIC_DOMAINS`,
`_extract_bare_domain`) — deterministic domains go to the default browser,
bare/unknown domains to awareness.

## Automation engine

"Automation" means two distinct things, both under
`Backend/skills/automation_engine/`:

1. **Assistant generation** — `AutomationEngine` (`engine.py`) is an
   assistant registry (`register_assistant`, `run_assistant`); the wired
   assistant analyses a skill folder and generates an `assistant.json` config
   from its `manifest.json`. Trigger: intents containing "generate".
   Reality check: PARTIAL — there is no automation *lifecycle*; a
   trigger-based, Sarthi-owned automation lifecycle is planned (AD-14).
2. **AI chaining** — delegated entirely to the `ai_chain/` package (above).

## HTTP API

FastAPI app in `Backend/api.py`, served by Uvicorn on `0.0.0.0:8000`
(`sarthi.bat`, `python api.py`). Interactive docs at `/docs`; dashboard at
`/ui`. CORS restricted to the two local dashboard origins.

### Core command API

| Endpoint | Method | Purpose |
| --- | --- | --- |
| `/command` | POST | Main pipeline. Accepts `{"query"}` (clients) or `{"text"}` (legacy UI). Returns the client envelope `{success, response, data}` + legacy fields. Handles mode commands and conversation mode; hands task-shaped instructions to Hermes *before* execution (AD-04); otherwise runs the deterministic pipeline and, on failure, consults the complexity router and may run the Hermes agent |
| `/health` | GET | Liveness + version |
| `/` | GET | Redirects to /ui |

### Mode & voice

| Endpoint | Method | Purpose |
| --- | --- | --- |
| `/mode` | GET/POST | Get/set chat mode (`default` \| `conversation`) |
| `/listen` | POST | Record + transcribe voice, then run the same pipeline |

### Knowledge & applications

| Endpoint | Method | Purpose |
| --- | --- | --- |
| `/knowledge` | GET | Knowledge-store stats |
| `/applications` | GET | Known applications |
| `/applications/categories` | GET | Category counts |
| `/applications/favourites` | GET | Favourite apps |
| `/applications/categorize` | POST | Move app to favourite/ignored/unattended |
| `/applications/run` | POST | Run Anyway (bypass favourites gate) |
| `/websites/search-and-save` | POST | Browser-search fallback for unknown "open X"; remembers the site |

### Settings & memory

| Endpoint | Method | Purpose |
| --- | --- | --- |
| `/settings` | POST | Save a key/value setting |
| `/settings/{key}` | GET | Read one setting |
| `/settings/voice-replies` | GET/POST | Spoken-replies toggle (default on) |
| `/memory` | GET | List /remember facts |
| `/memory/{key}` | DELETE | Delete one fact |
| `/command-history` | GET | Recent commands |
| `/command-history/{id}` | DELETE | Delete one history entry |

### Chat

| Endpoint | Method | Purpose |
| --- | --- | --- |
| `/chat` | GET | One session's persisted transcript |
| `/chat` | POST | Append a rendered message |
| `/chat` | DELETE | Clear a session (UI transcript + Hermes context; /remember facts kept) |

### Skills

| Endpoint | Method | Purpose |
| --- | --- | --- |
| `/skills` | GET | List discovered skills |
| `/skills/{id}` | GET | One skill's metadata |
| `/skills/{id}/enable` \| `disable` | POST | Toggle skill (runtime) |

### Connectors

| Endpoint | Method | Purpose |
| --- | --- | --- |
| `/connectors` | GET/POST | List / create connector configs |
| `/connectors/{id}` | PUT/DELETE | Update / delete |
| `/connectors/{id}/test` | POST | Test a connector |
| `/connectors/registry` | GET | Registered connector types |
| `/connectors/google_calendar/status` | GET | Auth status |
| `/connectors/google_calendar/connect` | POST | Desktop OAuth flow |
| `/connectors/google_calendar/connect-web` | POST | Web OAuth start |
| `/connectors/google_calendar/callback` | GET | OAuth callback |
| `/connectors/google_calendar/disconnect` | POST | Revoke |
| `/connectors/google_calendar/events` | GET | List events |

### Projects

| Endpoint | Method | Purpose |
| --- | --- | --- |
| `/projects` | GET/POST | List / create projects |
| `/projects/{id}` | GET/PUT/DELETE | Read / update / delete |

### System & testing

| Endpoint | Method | Purpose |
| --- | --- | --- |
| `/system/metrics` | GET | CPU/RAM/GPU readings (reading.py) |
| `/events/history` | GET | Recent event-bus events |
| `/test-mode` | GET/POST | Get/set dry-run mode |
| `/test/prompts` | GET | The 60 test prompts |
| `/test/run` | POST | Run all prompts through BrainEngine in test mode + hardware telemetry |

### Hermes router (`/hermes`, hermes/routes.py)

| Endpoint | Method | Purpose |
| --- | --- | --- |
| `/hermes/sandbox` | GET | Task list (paged) |
| `/hermes/sandbox/tasks/{id}` | GET | One task with trace |
| `/hermes/status` | GET | Provider stack status |
| `/hermes/tools` | GET | Registered tools |
| `/hermes/chat` | POST | Chat + reasoning through the single Hermes loop (fast path disabled) with session history and /remember facts attached |

### Browser router (`/browser`, skills/browser/routes.py)

| Endpoint | Method | Purpose |
| --- | --- | --- |
| `/browser/page` | POST | Receive page data (for a future extension) |
| `/browser/selection` | POST | Receive selection |
| `/browser/current` | GET | Cached current page |
| `/browser/session` | GET | Cached session |
| `/browser/action` | POST | Placeholder — returns `{"status": "pending"}` |

Endpoint count: 46 (34 api.py + 5 hermes + 5 browser + / + /docs-related).

## Data flow (important structures)

> **Security boundary (canonical).** Model/Hermes decisions reach execution
> only as structured tool/action requests: model output → `parse_tool_call` →
> `validate_tool_call` (Brain-side validation gate, `hermes/validator.py`) →
> capability/action resolution → Hand-side allow-list + argument validation →
> physical execution → structured result. There is no path in which the
> model, Hermes or the Brain runs a shell, evals Python, or executes
> arbitrary subprocesses.

| Structure | Produced by | Consumed by | Defined in |
| --- | --- | --- | --- |
| `Intent(action, target, site, confidence, raw_text)` | interpreter | planner, resolver, executor, every skill | `brain/intent.py` |
| `BrainResponse` / `to_api_dict()` | BrainEngine | api.py, CLI, Hermes fast path | `brain/response.py` |
| `Task(prompt, task_type, history, memory)` | Hermes paths | providers, orchestrator, sandbox | `hermes/models.py` |
| `ProviderResponse(success, text, provider, model, tool_used, error)` | providers | orchestrator, agent, sandbox | `hermes/providers/base.py` |
| `Route(route, reason, score, signals)` | complexity router | api.py fallback, agent | `hermes/router.py` |
| `ChainRequest` / `ChainOutcome` | ai_chain parsing | automation skill, chain runner, sandbox | `ai_chain/models.py` |
| `Event(name, data, source)` | any publisher | event bus handlers | `events/bus.py` |
| `DesktopRequest`/`DesktopResult` dicts | callers | Hand implementations | `hands/desktop/models.py` |

Skill result contract: `{success, status, result, error, handled?}` — no
exceptions for control flow. Tool call protocol:
`model output → parse_tool_call → {"tool", "arguments"} → validate_tool_call
→ verdict → ToolRegistry.execute → ToolResult(success, tool, result, error,
invalid?, data)`.

Persistence shapes: `sandbox/index.json` =
`{query_string: [{task_id, prompt, provider, model, status, tool_used, timestamp, duration_ms}]}`;
`sandbox/tasks/<id>/` = metadata.json, prompt.md, response.md, trace.json;
`results/ai_chain/<run>/` = 01_query.txt, 0N_stepN_<site>_response.txt,
harvested images.

## Dependency architecture

**Client/backend boundary (hard rule, test-locked by
`tests/test_architecture_boundaries.py`):** the Desktop client never imports
`brain`, `interpreter`, `model`, `knowledge`, or backend internals. It talks
HTTP only through `Desktop/client/sarthi_client/backend.py`.

**Inside the backend:**

- `brain/` imports `knowledge/` (resolver) and dispatches to `skills/` via the
  registry; it never imports `hermes/`.
- The NLP fallback *skill* (`skills/natural_language_processor/`) imports
  `hermes.service.chat` — the only brain-side path into the LLM layer.
- `hermes/` tools delegate to existing capabilities (`skills.browser`,
  `skills.app_launcher`, `skills.browser_awareness`, `knowledge.memory`,
  `connectors`) — no parallel execution system.
- `hands/` is called by the `close` executor handler and the app launcher via
  `hands.local.get_desktop_hand()`; the import lock (`hands/` imports nothing
  from `brain`/`hermes`/`knowledge`/`skills` — locked by
  `tests/test_brain_hand_boundary.py`) is enforced.
- `utils/voice` + `utils/spoken_replies` are leaf utilities (imported by
  ai_chain, browser_awareness, api.py startup).

## Control flow — who decides what

| Decision | Decider | Evidence |
| --- | --- | --- |
| Intent parsing | `brain/interpreter.py` (regex + keyword tables, deterministic) | `interpret_many()` |
| Multi-step planning | `brain/planner.py` — **pass-through**, returns `[intent]` | `planner.py` |
| Entity resolution | `knowledge/entity_resolver.py` (rapidfuzz) | `resolve()` |
| Execution dispatch | `brain/executor.py`: built-in handlers → default handler → skills (fallback NLP last) | `execute()` |
| Complexity routing | `hermes/router.py` heuristics; consulted before execution for task-shaped instructions and after a failed deterministic run (`api.py`) | `route_command()`, `looks_like_task_instruction()` |
| Tool selection (complex path) | the LLM, parsed by `hermes/agent.py` (`parse_tool_call`), validated by `hermes/validator.py` | `_loop()` |
| Failure handling | pipeline: fail-fast per step (`engine._execute_plan`); agent: bounded retries + refusal feedback | `agent.py` |
| Conversation mode | `brain/modes.py` — skips the brain pipeline entirely | `api.py` |

## Architectural decisions (summary)

The decision log with full problem/evidence/rejected-alternative reasoning is
archived at
[`docs/archive/documentation-reset-2026-09/ARCHITECTURAL_DECISIONS.md`](../archive/documentation-reset-2026-09/ARCHITECTURAL_DECISIONS.md).
Accepted decisions, in brief:

| ID | Decision | Status |
| --- | --- | --- |
| AD-01 | One canonical sandbox root (`Backend/sandbox`), cwd-independent | ACCEPTED |
| AD-02 | One Hermes reasoning loop (HermesAgent); the ToolPlanner loop is removed | ACCEPTED |
| AD-03 | `POST /hermes/chat` runs the canonical loop, fast path disabled | ACCEPTED |
| AD-04 | Task-shaped instructions escalate to Hermes *before* execution | ACCEPTED |
| AD-05 | Retry bound = 3 automatic iterations | ACCEPTED |
| AD-06 | Unreachable automation scaffolding + `pystray` removed | ACCEPTED |
| AD-07 | AI-chain intent collision: not reproducible, locked by tests | ACCEPTED |
| AD-08 | `/chain` keeps the chatgpt → gemini default AIs | ACCEPTED |
| AD-09 | Two conversation tables stay — different semantic states | ACCEPTED |
| AD-10 | Memory vs Knowledge boundary documented (placement unchanged) | ACCEPTED |
| AD-11 | Browser stacks stay separate; coordinate guessing stays opt-in | ACCEPTED |
| AD-16 | Brain/Hand boundary: `Hand` interface, `DesktopHand` is the local implementation | ACCEPTED |
| AD-12 | AI chain keeps its own control layer instead of delegating to Hands | DEFERRED |
| AD-13 | Sandbox → Knowledge promotion lifecycle | DEFERRED |
| AD-14 | AutomationEngine as a trigger-based, Sarthi-owned automation lifecycle | DEFERRED |
| AD-15 | Unified execution-observation contract | DEFERRED |

## Configuration

Configuration lives in three layers (verified against `Backend/config.py`,
`Backend/hermes/config/`, `.env.example`):

### Backend/config.py (static constants)

| Key | Value | Used by |
| --- | --- | --- |
| PROJECT_ROOT / SKILLS_DIR / KNOWLEDGE_DIR / UI_DIR | Backend paths | many |
| SAMPLE_RATE / RECORDING_DURATION / RECORDING_FILE | 16000 / 5 s / temp.wav | speech recorder |
| WHISPER_MODEL / _DEVICE / _COMPUTE_TYPE | small / cpu / int8 | speech_to_text |
| API_HOST / API_PORT | 0.0.0.0 / 8000 | api.py, sarthi.bat (kept in sync manually) |
| DESKTOP_AGENT_HOST / _PORT / _TIMEOUT / _MODE | 127.0.0.1 / 8765 / 30.0 / local | hands transport, desktop_agent.py |
| LOG_LEVEL / LOG_FORMAT | INFO / default fmt | utils/logger |

### Hermes environment variables (hermes/config/loader.py)

Core provider:

| Var | Default | Meaning |
| --- | --- | --- |
| HERMES_PROVIDER | `local` | `local` \| `openrouter` \| `openai_compatible` \| `openai` |
| HERMES_MODEL | `openai/gpt-5` | model id for the primary provider |
| HERMES_TEMPERATURE / HERMES_TIMEOUT | 0.2 / 60.0 | generation knobs |
| HERMES_SANDBOX_PATH | `sandbox` | TaskSandbox root (resolved against Backend/ — AD-01) |
| LOCAL_HERMES_URL / _API_KEY / _MODEL / _TIMEOUT | localhost:11434 / — / hermes3:8b / 180 | Ollama fallback |
| OPENROUTER_API_KEY / _URL / _HTTP_REFERER / _X_TITLE | — | OpenRouter |
| OPENAI_API_KEY (+ per-provider keys) | — | OpenAI-compatible endpoints |

Agent loop + router:

| Var | Default | Meaning |
| --- | --- | --- |
| HERMES_AGENT_MAX_ITERATIONS | 3 | tool-requesting turns per complex task |
| HERMES_AGENT_TIMEOUT | 300 | wall-clock budget (s) |
| HERMES_ROUTER_MODE | auto | auto \| always \| off |
| HERMES_ROUTER_MIN_SCORE | 1 | heuristic score threshold |

### Feature-specific environment variables

| Var | Feature | Meaning |
| --- | --- | --- |
| BROWSER_AWARENESS_DRIVER | browser awareness | `selenium` (default) \| `playwright` |
| BROWSER_AWARENESS_HEADLESS | browser awareness | run without a window |
| BROWSER_AWARENESS_PROFILE_DIR | browser awareness | persistent profile dir override |
| BROWSER_AWARENESS_CDP_URL | browser awareness | attach to an existing Chrome via CDP |
| AI_CHAIN_PROFILE_DIR | ai_chain | automation Chrome profile override |
| AI_CHAIN_AUTOMATION_PROFILE | ai_chain | profile switch control |
| AI_CHAIN_DOWNLOADS_DIR | ai_chain | where generated images are downloaded |
| AI_CHAIN_COORDINATE_SCAN | ai_chain | enable the legacy coordinate scan grid (=1) |
| SARTHI_DESKTOP_AGENT_* | IPC | host/port/timeout/mode (see the IPC section) |

### Settings table (runtime, user-facing)

`settings` table in sarthi.db via POST/GET `/settings`:

| Key | Set by | Meaning |
| --- | --- | --- |
| github_username | user_config skill / UI | GitHub identity for project tracking |
| voice_replies | POST /settings/voice-replies | spoken replies on/off (default on) |

Loading order: `config.py` imports are plain constants. Hermes config is read
per `ConfigLoader().load()` call (env + .env via python-dotenv; the result is
cached) — changes apply to newly built components. The settings table is read
on each access.

## Dependencies

Sources: `pyproject.toml`, actual imports in `Backend/` and
`Desktop/client/`, and the test suite.

### Runtime dependencies (pyproject [project.dependencies])

fastapi, uvicorn, httpx2 (Desktop client, project_tracker, connectors),
python-dotenv, pillow (test-runner dashboard images), psutil (hand processes,
scanner, telemetry), rapidfuzz (entity resolver), google-auth-oauthlib
(Google Calendar connector).

### Optional extra `automation` (laptop control, lazily imported)

pyautogui≥0.9.54, keyboard≥0.13.5 (abort hotkey), pyperclip≥1.8,
pywin32≥306 (SAPI TTS; voice degrades to PowerShell without it).

### Optional extra `browser` (DOM stacks, lazily imported)

selenium≥4.20, beautifulsoup4≥4.12, playwright≥1.40.

### Speech stack (NOT declared in pyproject)

sounddevice (speech/recorder.py) and faster-whisper (speech/speech_to_text.py)
are undeclared runtime dependencies of the voice CLI / `/listen` (lazy
imports; everything else runs without them).

### Dev dependencies

ruff (lint/format), pytest (tests/).

### System dependencies

- **Ollama** (local LLM) — default `HERMES_PROVIDER=local`; runtime-checked,
  graceful fallback errors.
- **Chrome** — browser awareness + ai_chain automation (Selenium Manager
  fetches the matching chromedriver automatically).
- **Windows** — TTS (SAPI/PowerShell), Desktop hand (pywin32/pygetwindow),
  ai_chain laptop control. Non-Windows degrades (voice → log line) or is
  unsupported (desktop hand actions).
- **Microphone + Whisper model files** — voice input only.

### Client (Desktop) dependencies

tkinter (stdlib) + httpx2 only — verified: `Desktop/client/sarthi_client/`
imports nothing else from third parties.

## CLI entry points

| Command | What it does |
| --- | --- |
| `Backend\sarthi.bat` | Starts the API server in a visible window; health-checks and prints Local/LAN URLs |
| `Backend\sarthi.bat background` | Windowless server via pythonw + uvicorn |
| `python Backend/api.py` | Direct server start (uvicorn run in-module) |
| `python Backend/main.py` | Voice CLI: ENTER to speak → record → whisper → BrainEngine → print intent/result |
| `python Backend/main-test.py` | Smoke test: a few prompts through BrainEngine (NOT the test suite) |
| `python Backend/desktop_agent.py --capabilities` | Print the Desktop hand's implemented/planned capability report |
| `python Backend/desktop_agent.py --self-test` | Read-only actions (active window, clipboard, process list) |
| `python Backend/desktop_agent.py --exec ACTION key=value` | Run one explicit hand action (validation-gated) |
| `python Backend/desktop_agent.py --server [--host H --port P]` | Serve the Desktop hand over HTTP IPC |
| `python -m skills.automation_engine.ai_chain.calibrate [opts]` | Show/record ai_chain site calibration points |
| `python Backend/scripts/clean_sandbox.py` | Clean the Hermes sandbox from the CLI |
| `python Desktop/run.py` | Launch the tkinter client in dev mode |
| `Desktop/dist/sarthi.exe` | Packaged client (PyInstaller, `sarthi_client.spec`) |
| `python -m hermes.main` | Single test prompt through the orchestrator |
| `pytest` | The root suite (pyproject: testpaths=tests, pythonpath=Backend+Desktop/client) |
| `POST /test/run` | In-app runner: 60 prompts through BrainEngine in test mode + telemetry (not pytest) |

There is no argparse-driven main CLI beyond the flags above; the API is the
primary interface. `main.py` requires microphone + whisper stack; everything
else runs without.
