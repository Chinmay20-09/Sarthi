# Sarthi Architecture

**Last verified against the code:** September 12, 2026 (client/backend restructure;
test suite green). This document is generated from the implementation, not from
intent. When code and this document disagree, fix the document or the code —
never assume one is right.

---

## 0. Client/Backend Architecture (September 12, 2026)

Sarthi is now a **client/backend system**. All intelligence lives in the
**Backend**; clients are thin interfaces that talk to it over HTTP.

```
Sarthi/
├── Backend/     # THE INTELLIGENCE — FastAPI service
│               #   api.py, main.py, main-test.py, desktop_agent.py,
│               #   config.py, sarthi.bat (launcher), .env, .env.example,
│               #   brain/ hands/ knowledge/ skills/ speech/ hermes/
│               #   connectors/ database/ events/ utils/ UI/ scripts/
│               #   runtime data: knowledge/*.json, database/sarthi.db,
│               #   sandbox/, results/, logs/
├── Desktop/     # Windows client — sarthi.exe (built from client/ source)
├── flutter/     # reserved — future Flutter client (not implemented)
├── apk/         # reserved — future Android distribution (not implemented)
├── tests/       # the single project-wide pytest suite (root, run: pytest)
└── docs/        # this document, PROJECT_STATE.md, CHANGELOG.md, ...
```

**The network boundary (the architectural rule):**

```
User
 ↓
Desktop sarthi.exe                (tkinter GUI: Query → Send → Response)
 ↓ HTTP  {"query": "open chrome"}
Backend POST /command             (FastAPI, 127.0.0.1:8000)
 ↓
Model / Interpreter / Brain / Knowledge / Skills / Executor
 ↓ HTTP  {"success": true, "response": "...", "data": {...}|null, ...}
Desktop sarthi.exe                (displays response)
```

- The Desktop client **never imports** brain/interpreter/model/knowledge/
  executor — only HTTP via `Desktop/client/sarthi_client/backend.py`.
- The Backend **never imports** Desktop UI code.
- Both rules are locked by `tests/test_architecture_boundaries.py`.
- `/command` is client-independent: `{"query": ...}` (Desktop exe, future
  Flutter/Android) and the legacy `{"text": ...}` (web UI) both flow through
  the **same** pipeline — there is exactly one command-processing path.
  Every `/command` and `/listen` response additionally carries the envelope
  `success` (bool), `response` (human-readable text), and `data`
  (structured detail or null), alongside all legacy fields.
- Backend URL configuration for the client lives in exactly one place:
  `Desktop/client/sarthi_client/config.py` — `SARTHI_BACKEND_URL` env var →
  `sarthi_client.json` → default `http://127.0.0.1:8000` (loopback; the
  backend is not exposed publicly by default).
- The Desktop exe is a build artifact produced by
  `Desktop/sarthi_client.spec` (PyInstaller); the spec is the committed
  source of truth.

**Future direction (planned, not implemented):**

```
                Sarthi Backend (:8000)
                        │
            ┌───────────┼───────────┐
            ▼           ▼           ▼
       Desktop       Flutter      Android
       sarthi.exe      UI           APK
        (today)     (reserved)   (reserved)
```

and, inside the Windows client: `Desktop client + Desktop Hand → Windows
control` — the Desktop Hand moves (or federates) into the client behind a
local IPC seam; `Backend/desktop_agent.py` (standalone hand, no Brain) is
that seam. No IPC is implemented yet.

**Import/layout notes:** the intelligence packages kept their flat names
(`from brain.engine import BrainEngine` still works everywhere): pytest adds
`Backend/` to `sys.path` (`pythonpath = ["Backend", "Desktop/client"]` in
`pyproject.toml`), the editable install exposes them via `package-dir =
{"": "Backend"}`, and `Backend/sarthi.bat` runs the API with `Backend/` as
its working directory. `config.py`'s `PROJECT_ROOT` now resolves to
`Backend/`, which keeps every runtime-data path (logs, SQLite DB, knowledge
JSON, sandbox, results) consistent without any code change.

---

## 1. System Overview

Sarthi is a local-first desktop assistant. One FastAPI process (the
**Backend**) serves both the REST API and the static UI; a layered pipeline
interprets natural-language commands and executes them through skills; a
separate conversational layer ("Hermes") handles everything the deterministic
pipeline cannot. Clients — the Desktop `sarthi.exe`, the web UI, and future
Flutter/Android apps — talk to it over HTTP (see §0).

```
UI (8 static pages, served by the API at /ui)
   │  fetch() only — the UI never imports backend modules
   ▼
api.py (FastAPI, 127.0.0.1:8000)  ── also mounts /browser and /hermes routers
   │
   ▼
BrainEngine (brain/engine.py)
   interpret → plan → resolve → execute
   │                    (fuzzy resolution via knowledge layer)
   ├── built-in handlers: open → AppLauncher → Browser → needs_decision
   │                      close → knowledge → DesktopHand (close_application)
   │                      browse → BrowserAwarenessSkill (validated actions)
   │                      remember / recall / forget / clean
   ├── skills fallback pool (skills/registry.py, NLP skill registered LAST)
   └── NLP fallback skill → hermes.service.chat → HermesOrchestrator
                               ├── ToolPlanner → ToolRegistry (bounded loop)
                               └── ProviderManager → provider adapters
                                     (Ollama local / OpenRouter / any OpenAI-compatible)
   │
   ▼ (OS-level actions)
DesktopHand (hands/desktop/hand.py)  ── the physical execution layer
   open_application / close_application / open_url / type_text / hotkey /
   copy / paste / click / read_clipboard / list_windows / get_processes / ...
   │  capability allow-list, argument validation, structured DesktopResult
   ▼
Windows (processes, windows, clipboard, input, filesystem)
```

Two mantras hold the design together:

- **Sarthi core is model-agnostic.** Interpreter, resolver, executor, skills and
  knowledge never import a model provider.
- **Hermes is provider-agnostic.** The orchestrator, tool planner, routes and
  service layer never import a concrete provider adapter; provider-specific
  behavior lives only in `hermes/providers/`.

**Registries — one owner per concern (do not create parallel systems):**

| Concern | Owner | Notes |
|---|---|---|
| Skills | `skills/registry.py` | manifest.json discovery, enable/disable |
| Hermes tools | `hermes/tool_registry.py` | allow-list, argument validation, bounded loop |
| Connectors | `connectors/registry.py` | `BaseConnector` subclasses |
| Entities | `knowledge/manager.py` | applications v2 / websites v1 schemas |
| Executor handlers | `brain/executor.py` | built-in handlers + skill fallback pool (NLP last) |
| Desktop actions | `hands/desktop/capabilities.py` | the only allow-list of what Desktop may do |
| Providers | `hermes/providers/registry.py` | the only place a provider *name* maps to a class |

---

## 2. Runtime Architecture

A single Python process (plus optional helpers):

| Process | Started by | Role |
|---|---|---|
| `python api.py` (or `pythonw -m uvicorn api:app` in background mode) | `Backend/sarthi.bat` (root `start.bat` delegates to it) | FastAPI app: REST API, mounted routers, `/ui` static files. Runs **without** uvicorn reload by default so closing the server window frees port 8000. |
| `python main.py` | manual | Voice CLI: record → Whisper → same `BrainEngine` |
| `python -m hermes.main` | manual | Hermes self-test: config → provider manager → one task through the orchestrator → sandbox |

Ollama (or another configured model endpoint) is an **external** service contacted
over HTTP; nothing else runs as a Sarthi process (the Desktop exe is a thin
client, not a Sarthi process). `python api.py --reload`
re-enables hot-reload for development (the spawned reloader worker survives the
console window — see the warning in `api.py`).

---

## 3. Core Command Pipeline

The pipeline contract is the pydantic model `Intent(action, target, confidence,
site, raw_text)` (`brain/intent.py`). Skills return a plain dict
`{success, status, result, error}` (visual cards inside `result.visual`).

```
text ─▶ BrainEngine.process(text)
         1. Interpreter (brain/interpreter.py, interpret_many)
              "open X and search Y" and '.'-separated queries → List[Intent]
         2. Planner (brain/planner.py)  — documented PASS-THROUGH today;
              the interpreter already splits compound commands
         3. Resolver (knowledge/entity_resolver.py)
              RapidFuzz WRatio over names+aliases (min confidence 80,
              length-ratio guard). Entities injected from KnowledgeManager.
         4. Executor (brain/executor.py) dispatch, in order:
              a. direct action handler ("open", "browse", "remember", …)
              b. default handler (if set)
              c. registered skills, first success wins; a skill that returns
                 handled=True owns the intent even on failure (this is what
                 keeps later fallbacks from overriding real errors)
              d. no handler → structured error
         Multi-step plans execute sequentially, fail-fast, every step is
         reported to the UI as a card (steps[] in the API response).
```

**"open" resolution order (user-facing contract):**
1. `AppLauncherSkill` (favourites-gated; uncategorized apps surface a
   Favourite/Ignore/Run-Anyway decision)
2. `BrowserSkill` (known websites)
3. neither → `needs_decision` with an `open_choice` card (scan the system, or
   search in the browser and remember the site via `/websites/search-and-save`).

The `AppLauncher`/`Browser` handlers instantiate their skills directly — they
are the built-in core actions, not part of the fallback pool.

---

## 4. Hermes

Hermes is the conversational/orchestration layer — **not a second brain and not
a skill author** (that is planned, not implemented).

**Boundaries:**
- May: answer conversationally, request *registered* tools, record every task in
  the sandbox, observe pages in Browser Awareness.
- Must not: execute code/shell/filesystem operations, bypass the ToolRegistry,
  control the browser, or modify core files.

**Orchestration (`hermes/orchestrator.py`):**

```
Task(prompt, instructions, history, memory)
   │ process()                          ── tool path
   ▼
ToolPlanner  (bounded loop: MAX_TOOL_CALLS_PER_TASK = 5)
   decision prompt → model replies {"tool_call": {...}} (strict JSON, parsed
   tolerantly: fences, embedded braces, doubled braces)
   → ToolRegistry.execute(tool, args)  (validation; unknown tool → graceful text)
   → follow-up prompt with the ToolResult → final answer
   │ chat()                             ── plain chat path: NO tools at all
   ▼
ProviderManager.generate() ── primary provider ──▶ ProviderResponse
        └── on failure: generate_fallback() (local Ollama, remote modes only)
   ▼
TaskSandbox.save()  — sandbox/tasks/<id>/ + sandbox/index.json (query index)
```

**Sandbox:** every Hermes execution (chat and tool paths) is persisted under
`HERMES_SANDBOX_PATH` (default `sandbox/`), indexed by normalized query.
`/clean` (and `scripts/clean_sandbox.py`) delete successful tasks and keep
failed ones for review. The sandbox is personal runtime data and is gitignored.

**Default tools (`hermes/tools/`, registered by `register_default_tools`):**
`open_app`, `open_website`, `github`, `personal_context` — each wraps an
existing Sarthi capability. Adding a tool to the registry is a security-relevant
change (see CONTRIBUTING.md).

---

## 5. Desktop Hand (physical execution layer)

`hands/desktop/` is Sarthi's hand on the computer. The chain is:

```
Brain (decides)  →  Executor / Skill  →  DesktopHand (performs)  →  Windows
```

The hand executes explicit, validated operations and never reasons. It
contains no model, no interpreter, no resolver, and no policy beyond its
validation gate. "open chrome" is *decided* by the brain + knowledge
layer; the hand only ever receives an explicit path, pid, URL, or text.

```
hands/
└── desktop/
    ├── __init__.py       public exports (DesktopHand, models, backends)
    ├── hand.py           DesktopHand: execute(action, target, **kwargs)
    ├── capabilities.py   the action allow-list (per-capability arg specs)
    ├── models.py         DesktopRequest / DesktopResult contracts
    ├── processes.py      launch (CreateProcess/ShellExecute, never shell),
    │                     terminate, list (psutil)
    ├── windows.py        window enumeration / foreground window (pywin32,
    │                     optional — degrades gracefully)
    ├── input.py          keyboard / mouse (pyautogui) + clipboard
    │                     (pyperclip) — optional automation extra
    ├── filesystem.py     scoped file ops (allowed roots, 1 MB cap)
    ├── browser.py        open_url (http/https only)
    └── README.md         module documentation
```

**Contract:** `desktop.execute(action, target=None, **kwargs)` returns a
structured dict `{success, action, target, message, error?, data?}` — a
`DesktopResult`. Failures are returned, never raised past the boundary
and never hidden. Every action is logged:
`[Desktop] action=... target=... status=...`.

**Safety model:**
- The action table in `capabilities.py` is the only thing the hand can
  do; unknown actions and unexpected/wrong-typed arguments are rejected
  before anything runs.
- No shell execution and no arbitrary code execution exist anywhere in
  the package (locked by a test that greps the sources).
- Name→path resolution happens upstream (knowledge layer); the hand
  needs explicit paths and pids.
- Filesystem actions are scoped to allowed roots (default: the user
  profile) with a 1 MB read/write cap.
- Optional backends (pyautogui/pyperclip/pywin32) degrade to structured
  failures when not installed — the hand never fakes success.

**Capabilities implemented today** (see `hands/desktop/README.md` for the
full table): APPLICATION_LAUNCH, APPLICATION_CLOSE, WINDOW_READ,
BROWSER_CONTROL, KEYBOARD, MOUSE, CLIPBOARD, FILESYSTEM_READ,
FILESYSTEM_WRITE, PROCESS_CONTROL. Planned and deliberately not
registered: WINDOW_CONTROL, SHELL.

**Browser rule:** the hand never guesses coordinates as a strategy. The
project priority is DOM/browser automation → accessibility/semantic UI →
visual/UI automation → calibrated coordinate fallback (never random).
Element discovery stays in Browser Awareness (`skills/browser_awareness/`)
and the ai_chain DOM layer; Desktop provides only the physical primitives
at the end of that chain.

**Executor delegation:** `AppLauncherSkill._launch_path` delegates to
`hands.desktop.processes` (same CreateProcess/ShellExecute rules as
before), and the executor's built-in `close` handler resolves the target
via knowledge, finds matching processes through the hand's read-only
`find_application_process`, then terminates by explicit pid. Existing
open/search/play flows behave exactly as before.

**Independence:** `Backend/desktop_agent.py` runs the hand standalone
(`--capabilities`, `--self-test`, `--exec ACTION key=value`). This is the
seam for a future `Sarthi.exe` desktop runtime: a small local IPC layer
(serving `DesktopRequest` → `DesktopResult`) can be added there without
touching any Brain module. No IPC is implemented yet.

## 6. Provider Architecture

The chain below is the verified conceptual boundary:

```
Sarthi (brain, skills, api) ── never touches a provider
   ▼
hermes.service / orchestrator        (Task / ProviderResponse)
   ▼
hermes.providers.registry            (name → adapter; ONLY place this mapping exists)
   ▼
ProviderManager                      (normalizes Task|ModelRequest → ModelRequest;
   ▼                                  owns primary + fallback)
AIProvider (hermes/providers/base.py)  generate(ModelRequest) -> ProviderResponse
   ▼                                        capabilities() -> ModelCapabilities
Provider adapters
   ├── LocalHermesProvider   — Ollama /api/chat (local_timeout 180s, one retry on
   │                           pure timeout for cold model loads)
   ├── OpenAICompatibleProvider — any /v1/chat/completions endpoint; keyless
   │                             local servers send no Authorization header
   └── OpenRouterProvider    — thin subclass (endpoint/key/extra headers),
                               fails fast without a key
```

**Data contracts** (`hermes/models.py`, `hermes/providers/base.py`):
`Task` → `Task.to_request()` → `ModelRequest(prompt, instructions, history,
memory, tools, structured_output, images, temperature)` → wire format (built
inside the adapter) → `ProviderResponse{success, provider, model, text, error,
tool_used, data, usage, raw}`. Adapters never see orchestration metadata; Hermes
core never sees provider payloads.

**Provider selection** (`HERMES_PROVIDER`, resolved in
`hermes/providers/registry.py`):

| Value | Primary | Fallback |
|---|---|---|
| `local` / `ollama` (**default**) | LocalHermesProvider | none (local-only) |
| `openrouter` | OpenRouterProvider | local Ollama |
| `openai_compatible` / `openai` | OpenAICompatibleProvider | local Ollama |

Unknown values fall back to the **local** provider with a logged error — a typo
must never spend cloud credits. Changing provider/model is configuration-only
(`.env` → `hermes/config/loader.py` → `HermesConfig`, cached after first load).

**Adding a provider = 2 code files + config:** one adapter subclassing
`AIProvider` (place in `hermes/providers/`), one entry in
`registry.py` (`create_primary`/aliases), plus `HERMES_PROVIDER` documentation in
`.env.example`/`README_ENV.md`. No core, brain, skill, or API changes.

**Capability matrix (what adapters actually implement today):**

| Capability | Ollama | OpenAI-compatible | Notes |
|---|---|---|---|
| `structured_output` | ✔ (`format=json`) | ✔ (`response_format=json_object`) | Hermes always parses+validates JSON regardless |
| `tool_calling` | ✘ | ✘ | prompt-based tool protocol everywhere |
| `vision` | ✘ | ✘ | `ModelRequest.images` is never sent |
| `streaming` | ✘ | ✘ | non-streaming requests only |
| `context_window` | `None` | `None` | not detected |

Capabilities are declared by the *adapter*, not assumed from the upstream API.
An endpoint that rejects `response_format` surfaces a graceful provider error.

**Failure handling:** timeout / HTTP error / malformed payload / null content /
missing endpoint / missing key → `ProviderResponse(success=False, error=...)`.
The orchestrator then tries the fallback (remote modes) and finally returns a
graceful combined failure. `/hermes/status` exposes the active stack (no secrets).

---

## 7. Browser Awareness

The non-deterministic extension of "open": inspect an arbitrary website and act
on it with validated steps. Location: `skills/browser_awareness/`.
Element discovery here is the semantic front of the browser priority chain
(see §5): DOM/accessibility first, coordinates only as a calibrated last
resort — the Desktop hand supplies the physical primitives afterwards.

```
"open example.com and find the pricing page"  → interpreter → action="browse"
BrowserAwarenessSkill
   test mode? → plan only (no browser)
BrowserAwarenessManager   (MAX_STEPS = 8, per-run temporary context)
   PlaywrightInspector → PageSnapshot{url, title, text(capped), elements[
       {id, kind, text, placeholder, label, name, href, selector, visible, enabled}]}
       — sensitive fields (password/token/pin) are scrubbed; never the full DOM
   HermesInspector.observe()  → strict InspectionResult JSON
       (status continue|done|blocked + at most ONE RecommendedAction)
   validate_inspection()      → pure gate: element exists/visible/enabled,
       kind matches the action, navigate is http(s) only
   SafeExecutor.perform()     → allow-list: navigate|click|type|select|check|
       uncheck|submit|scroll; inspector-generated selectors only (regex-checked,
       script/iframe tags blocked); live re-check before every action
   → reinspect → … → completed | blocked | needs_confirmation | step limit
```

- **Model independence:** the manager takes injected
  inspector/hermes/executor; `HermesInspector` defaults to a provider built via
  `hermes.providers.registry.create_local_provider()` (the configured local
  stack) — never a concrete adapter import. Any provider works; tests run with
  fakes and no browser.
- **Hermes never controls the browser** — it only observes and recommends;
  malformed recommendations become `blocked` before the executor runs.
- **Session lifecycle:** default mode launches the installed Chrome with a
  throwaway profile (deleted on every exit path); `BROWSER_AWARENESS_CDP_URL`
  attaches to an already-running Chrome and closes only its own tab. Voice
  progress announcements follow `docs/ABSOLUTE.md` (dry runs stay silent).
- **Related but separate:** the automation engine's `ai_chain` module (v1.5)
  also does DOM-regex locating through a DevTools endpoint and a screen-state
  classifier for its RPA loop; its transcript extraction uses the same local
  provider via `create_local_provider()`. It is laptop-automation, not Browser
  Awareness — see `skills/automation_engine/ai_chain/README.md`.
- **v1.7 browser automation (`ai_chain/browser_automation.py`):** the reusable
  DOM-aware layer behind multi-site chains. `resolve_element(driver, action,
  target)` parses the live page HTML with BeautifulSoup (regex fallback),
  scores candidates by semantic signals (id, aria-label, name, placeholder,
  role, associated label, visible text, data-*), produces a Selenium XPath and
  verifies the live element — no coordinate guessing. `BrowserAutomation`
  wraps navigate/click/copy/paste with per-action verification and explicit
  `ChainState`; `run_browser_chain(steps)` executes declarative
  open→copy→open→paste chains with values passed between sites through chain
  state (physical clipboard only when the user asks). The v1.0 multi-point
  scan grid is disabled by default (`AI_CHAIN_COORDINATE_SCAN=1` re-enables
  the legacy behaviour).

---

## 8. Skills

Discovery (`skills/registry.py`, the single mechanism): scan `skills/` for
`manifest.json` → `SkillMetadata` (no code imported) → on demand, import
`skills/<id>/main.py`, find the `BaseSkill` subclass, instantiate (no-arg, or
env-var-fed constructor kwargs). `enabled` lives in the manifest; disable/enable
via `/skills/{id}/disable|enable`. `BrainEngine` sorts skills with
`fallback=True` (only the NLP skill) to the END of the executor's pool.

Current skills (10):

| Skill | What it owns |
|---|---|
| `app_launcher` | Launch installed applications (favourites gate, run_anyway) |
| `browser` | Open/search known websites (deterministic) |
| `browser_awareness` | Inspect arbitrary websites with validated actions |
| `scanner` | Application discovery (`scan_all`, merge into knowledge) |
| `project_tracker` | GitHub/Notion project tracking |
| `automation_engine` | AI-chain laptop automation + assistant metadata generation |
| `speech` | Push-to-talk mic recording + Whisper transcription |
| `user_config` | User settings (e.g. github username) |
| `personal_context` | Personal profile fields (field-scoped access) |
| `natural_language_processor` | Conversational fallback via Hermes — **registered last** |

**Hermes' view of skills:** indirect only — Hermes may call the four registered
tools, which delegate to existing capabilities. There is no path from Hermes to
the skill registry. Skill authoring by Hermes is planned and must follow the
propose → validate → register pattern (see CONTRIBUTING.md).

---

## 9. Knowledge

- **Scanner** (`skills/scanner/application_scanner.py`): Windows locations
  (Program Files, LocalAppData, Start Menu, PATH), `.exe` + `.lnk` (COM-resolved),
  alias generation, 5-tier duplicate priority. Output: `{name, aliases, path,
  category}` dicts.
- **KnowledgeManager** (`knowledge/manager.py`, singleton): the only public
  interface. Applications v2 schema — `{version: 2, last_scan, categories:
  {favourite, ignored, unattended}}`; legacy v1 `{entities: []}` loads as
  all-unattended. `merge_scan_results()` preserves user categorization and puts
  new apps in `unattended`. Websites v1 — `{version: 1, entities: [...]}` with
  `name/url/aliases`; `add_website` upserts by lowercase name.
- **EntityResolver** (`knowledge/entity_resolver.py`): pure DI — receives
  `[{name, aliases, category, ...}]` from `get_all_entities()`, never touches
  disk. Names are indexed before aliases so canonical names win ties.
- **Memory** (`knowledge/memory.py`): short-term TTL cache (in-process) +
  long-term `/remember` facts in SQLite; `build_memory_prompt()` injects them
  into every Hermes call as a system message.
- **Cache** (`knowledge/cache.py`): TTL cache used by memory; `clear_cache()`
  on the manager.

Data flows: Scanner → `merge_scan_results()` → applications.json →
`get_all_entities()` → EntityResolver → resolved `Intent.target` → Executor.
Boundary tests lock these shapes in `tests/test_pipeline_compatibility.py`.

---

## 10. Connectors

`connectors/base.py` defines `BaseConnector` (metadata, `get_auth_url`,
`handle_auth_callback`, `disconnect`, `is_connected`, `execute_tool`).
`connectors/registry.py` lazily registers implementations; the DB
(`connectors` table) stores user-added connector rows and the API merges live
status from the registry.

Implemented: **Google Calendar** (OAuth2 desktop flow, `list_events`) —
`/connectors/*` routes in `api.py` plus `/connectors/google_calendar/*`.
Planned (scaffolding comments only): Gmail, other services. The generic
`/connectors/{id}/test` endpoint marks a connector connected when config
exists — it does not validate credentials against the service (documented in
the route).

---

## 11. API / UI

One API process serves everything: REST under `/`, static UI at `/ui`
(mounted from `UI/`), `/` redirects to `dashboard.html`. CORS is locked to the
two local origins (`127.0.0.1:8000`, `localhost:8000`), credentials off.

Endpoint groups (all verified present):

| Group | Endpoints |
|---|---|
| Core | `GET /health`, `POST /command`, `POST /listen`, `GET/POST /mode` |
| Knowledge | `GET /knowledge`, `GET /applications`, `GET /applications/categories`, `GET /applications/favourites`, `POST /applications/categorize`, `POST /applications/run`, `POST /websites/search-and-save` |
| Memory/history | `GET /memory`, `DELETE /memory/{key}`, `GET /command-history`, `DELETE /command-history/{id}`, `GET/POST/DELETE /chat` |
| Settings | `POST /settings`, `GET /settings/{key}` |
| Skills | `GET /skills`, `GET /skills/{id}`, `POST /skills/{id}/enable|disable` |
| Hermes | `POST /hermes/chat`, `GET /hermes/tools`, `GET /hermes/sandbox`, `GET /hermes/sandbox/tasks/{id}`, `GET /hermes/status` |
| Browser (extension bridge) | `POST /browser/page`, `/browser/selection`, `/browser/action`, `GET /browser/current`, `/browser/session` |
| Connectors | `GET/POST/PUT/DELETE /connectors*`, `GET /connectors/registry`, `/connectors/google_calendar/*` |
| Diagnostics | `GET /system/metrics`, `GET /events/history`, `GET/POST /test-mode`, `GET /test/prompts`, `POST /test/run` |

`/command` responses carry `routing` ("command" vs "hermes") and `mode`, so the
UI can badge who handled a request. Conversation mode ("conversation mode" /
`/exit`) bypasses the brain pipeline entirely and goes to Hermes plain chat
(no tools).

### The two-path architecture (September 2026)

Sarthi has two execution paths, gated by a complexity router:

```
FAST PATH (simple, deterministic):        COMPLEX PATH (Hermes):
User                                      User
 ↓                                          ↓
Interpreter                              Complexity Router (hermes/router.py)
 ↓                                          ↓
Entity Resolver                          Deterministic pipeline (first try)
 ↓                                          ↓
Executor                                 Hybrid Retriever (hermes/retriever.py)
 ↓                                          ↓
Application / Website                    Bounded agent loop (hermes/agent.py)
                                          ↓
                                          Validator (hermes/validator.py) → ToolRegistry → tools
                                          ↓
                                          Hermes continues or answers
```

- The router is pure text heuristics (~0.25 ms): no model loads, no DB, no
  network. Its action-word set mirrors the interpreter's `ACTION_WORDS`, and
  the interpreter's own compound shapes ("open X and search/play Y") stay
  fast by design.
- Inside `/command`, the router only ever promotes a request to Hermes when
  the deterministic pipeline did NOT succeed — a deterministic success always
  wins, so fast-path latency is preserved.
- The agent loop is bounded three ways: iteration cap, wall-clock budget,
  and the validator+registry gate (unknown tools and unsafe arguments never
  execute). All ten registered tools delegate to existing Sarthi skills —
  Hermes decides WHAT; Sarthi decides HOW.
- Router/retrieval/agent knobs live in `.env` (see `.env.example`):
  `HERMES_ROUTER_MODE`, `HERMES_ROUTER_MIN_SCORE`, `HERMES_AGENT_*`,
  `HERMES_RETRIEVAL_*`.

**UI → API cross-check (verified by grep):** every `fetch()` in the UI maps to
an existing endpoint; the UI never imports backend modules. Each page declares
its own API-origin constant (`components.js` exports `API`; `chat.html` uses
`SarthiAPI` to avoid a `const` collision) — a known cosmetic duplication, not a
defect. Wired pages: dashboard, chat, skills, memory, knowledge, **history**
(live `/command-history` timeline with search + delete) and **settings**
(live `/system/metrics` diagnostics, `/connectors` statuses; the Voice/Privacy
toggles are explicitly labeled visual previews without backing settings).

---

## 12. Configuration

Two small, distinct layers — there is deliberately no bigger framework:

| Layer | Mechanism | Variables |
|---|---|---|
| App config | `config.py` (plain module constants) | paths, `API_HOST`/`API_PORT` (8000), Whisper settings, log format |
| Hermes config | `.env` → `hermes/config/loader.py` → `HermesConfig` (cached) | `HERMES_PROVIDER`, `HERMES_MODEL`, `HERMES_TEMPERATURE`, `HERMES_TIMEOUT`, `HERMES_SANDBOX_PATH`, `LOCAL_HERMES_*`, `OPENROUTER_*`, `OPENAI_COMPATIBLE_*` |
| ai_chain tuning | env vars + `calibration.json` (git-ignored) | `AI_CHAIN_*` (CDP URL, DOM switches, per-site overrides) |
| Browser Awareness | env vars | `BROWSER_AWARENESS_CDP_URL`, `BROWSER_AWARENESS_HEADLESS` |

Canonical references: `.env.example` (copy to `.env`; never commit) and
`README_ENV.md`. Hardcoded values that are intentional: port 8000 in
`api.py`/`sarthi.bat` (single local instance), CORS origins, sandbox default
path, and the Desktop client's default backend URL (`127.0.0.1:8000`).

---

## 13. Persistence

| Store | Location | Owner | Content |
|---|---|---|---|
| SQLite | `database/sarthi.db` | `DatabaseManager` (single connection, WAL + synchronous=NORMAL, busy_timeout, connection lock) | command_history, knowledge_memory, settings, chat_messages, conversation_messages, connectors |
| Applications | `knowledge/applications.json` | KnowledgeManager | v2 categorized entities |
| Websites | `knowledge/websites.json` | KnowledgeManager | v1 entities |
| Hermes sandbox | `sandbox/` (gitignored) | TaskSandbox | tasks + query index |
| AI-chain runs | `results/ai_chain/<ts>_<slug>/` | chain module | transcripts, images |
| Test-run reports | `results/run_*.json|csv|png` | `/test/run` | metrics (30-day retention) |

The SQLite file holds personal data and is blocked from commits by a pre-commit
hook; `sandbox/` and `sandbox_test/` are runtime data (gitignored — see
CONTRIBUTING for the untracking caveat).

`DatabaseManager` behavior that callers can rely on:

- **Self-healing schema** — on connect it creates every canonical table and
  index from `database/models.py` (`ALL_TABLES` / `ALL_INDEXES`); callers do
  not need to run `CREATE TABLE IF NOT EXISTS` first.
- **`session_id` indexes** on the chat/conversation tables — per-session
  reads, trims, and resets are index scans, verified by `EXPLAIN QUERY PLAN`
  tests in `tests/test_database_optimizations.py`.
- **Thread-safe shared connection** — access is serialized by a lock;
  FastAPI threadpool workers can write concurrently (5 s busy_timeout).
- **`db.transaction()`** — groups writes into one atomic commit with
  rollback on error (`tx.execute` / `tx.fetch_one`); never call the
  manager's own `fetch_*`/`execute` inside an open transaction — the
  non-reentrant lock deadlocks. `ConversationStore.add_turn` inserts and
  trims in one transaction.

---

## 14. Testing

`python -m pytest tests/ -q` from `Sarthi/` — **763 tests, 45 files, all
passing** (plus 1
benign deprecation warning from FastAPI's test client). Lint/format: `ruff
check .` and `ruff format --check .` are clean. Smoke test: `python
`Backend/main-test.py` (9 checks, no LLM call). Pytest config lives in
`pyproject.toml` (`testpaths = ["tests"]`, `pythonpath = ["Backend",
"Desktop/client"]`); the root `tests/` folder is the single suite and the
only place tests live.

Boundary tests live in `tests/test_pipeline_compatibility.py` (Scanner →
Knowledge → Resolver, Brain → Hermes) and `tests/test_provider_abstraction.py`
(provider interface, normalization, capability detection, failure modes,
Browser Awareness decoupling). Tests must not require a live Ollama, Chrome, or
real hardware — providers, skills and browser components are faked (see
`tests/test_browser_awareness.py`).

CI (`.github/workflows/ci.yml`, branches master/testing): lint, format check,
pytest, smoke test. Local pre-commit hooks mirror it (plus a no-DB-files guard).

---

## 15. Extension Points

| I want to add a… | Do this | Never |
|---|---|---|
| **Skill** | `skills/<id>/` with `manifest.json` + `BaseSkill` subclass in `main.py` | scan the skills dir yourself; touch `skills/base.py` casually |
| **Hermes tool** | `hermes/tools/<name>.py` (`BaseTool`), register in `hermes/tools/__init__.py` | expose code/shell/filesystem execution |
| **Provider** | `hermes/providers/<name>.py` (`AIProvider` subclass) + registry entry + `.env` docs | import a concrete adapter outside `hermes/providers/` |
| **Connector** | `connectors/<service>/` (`BaseConnector` subclass) + `registry.discover()` entry | wire it into the executor or brain |
| **Browser capability** | extend `skills/browser_awareness/` schemas + validation rules + `SafeExecutor`; add tests | let the model inject selectors or call the executor directly |
| **Desktop action** | add the action to a capability in `hands/desktop/capabilities.py`, implement its backend, add tests | bypass the allow-list, execute shell/code, guess coordinates |
| **Knowledge source** | JSON file + loader wiring in `KnowledgeManager`; `get_all_entities()` already normalizes | bypass the manager |
| **API endpoint** | `api.py` or a mounted router; update the README table | let the UI call internal modules |
| **UI page** | `UI/<page>.html` using `components.js` sidebar/footer | duplicate the sidebar markup |
| **Client** | extend `Desktop/client/sarthi_client/` (GUI → controller → backend.py); rebuild the exe via `Desktop/sarthi_client.spec` | import Backend internals in the client; talk HTTP anywhere but `backend.py` |

Full integration paths and review rules: `CONTRIBUTING.md`.

---

## 16. Current Limitations

Explicit, verified:

1. **Planner is a pass-through** (`brain/planner.py`) — compound-command
   splitting lives in the interpreter. The file says so honestly.
2. **Hermes skill authoring is not implemented** — planned; the safety boundary
   already exists, the build/validate/register path does not.
2a. **Desktop WINDOW_CONTROL and SHELL are planned, not implemented** — the
    capability list declares them; no action uses them. SHELL in particular
    needs a review gate before any code exists.
3. **No native tool calling, vision, or streaming** in any adapter — the
   prompt-based tool protocol covers tool calls; images/streaming are unwired.
4. **ModelCapabilities.context_window is never populated** — no context-limit
   management exists.
5. **One connector** (Google Calendar); the generic connector "test" endpoint
   does not validate credentials.
6. **UI gaps:** the Voice & Personality / Privacy & Security toggles on
   `settings.html` (and the UI-customization section) are visual previews —
   no backing settings exist; diagnostics and connector statuses on that page
   are live.
7. **Resolver quirk:** a machine-scanned app can shadow a website alias when
   both clean to the same string (canonical names indexed before aliases).
   Deterministic; websites remain reachable by canonical name.
8. **Windows-oriented:** scanner, app launching, ai_chain automation and the
   Desktop hand assume Windows; core pipeline/API/tests are cross-platform
   (CI runs on Ubuntu). Desktop input/clipboard/window backends degrade to
   structured failures without their optional dependencies.
9. **Mode/test-mode state is process-local** — a restart resets it.
10. **`hermes/routes.py` keeps module-level `_orchestrator`/`_sandbox` globals**
    solely for test compatibility; the real singletons live in
    `hermes.service`. Harmless, scheduled for cleanup.
11. **`sandbox/`/`sandbox_test/` are gitignored but still tracked** (committed
    before the ignore was added). Untrack with `git rm -r --cached sandbox
    sandbox_test` in the next commit.
12. **uvicorn `--reload` leaks its worker** on window close (documented in
    `api.py`); the default single-process mode is the safe path.
