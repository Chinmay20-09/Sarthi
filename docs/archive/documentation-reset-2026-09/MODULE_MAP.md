# Module map (observed)

Every package and significant file, what it does, and who calls it.

## Backend root

| File | Purpose | Callers |
| --- | --- | --- |
| `api.py` | FastAPI app (46 routes), `/command` pipeline, complexity fallback, voice-reply wiring, test runner endpoints | Uvicorn (`sarthi.bat`, `python api.py`), tests |
| `config.py` | Central constants: paths, speech settings, API host/port, logging | many modules |
| `main.py` | Voice CLI loop (record → whisper → BrainEngine) | manual run |
| `main-test.py` | Smoke test: a few prompts through BrainEngine | manual run |
| `desktop_agent.py` | Standalone Desktop-hand process: `--capabilities`, `--self-test`, `--exec` (no IPC server) | manual run |
| `reading.py` | System hardware readings (CPU/RAM/GPU) for `/system/metrics` and telemetry | api.py, utils/telemetry |
| `test_prompts.json` | 60 prompts for `POST /test/run` | api.py test runner |
| `sarthi.bat` | Backend launcher (dev window / background mode) | user |

## Backend/brain/ — deterministic pipeline (the Sarthi Brain)

| Module | Purpose |
| --- | --- |
| `engine.py` | BrainEngine orchestrator: interpret → plan → resolve → execute. Loads skills via registry. Single public entry point |
| `interpreter.py` | Text → `Intent` list: sentence split, slash commands, chain shapes, open+search/play compounds, domain/browse routing, wordfinder targets |
| `intent.py` | `Intent` model — primary data contract |
| `planner.py` | Pass-through planner (returns `[intent]`) — multi-step decomposition NOT implemented |
| `executor.py` | Dispatch: built-in handlers (open/close/browse/remember/recall/forget/clean), then skills |
| `response.py` | `BrainResponse`, `step_payload` (per-step API cards) |
| `context.py` | `BrainContext` — per-run state |
| `modes.py` | default/conversation chat mode + test (dry-run) mode |
| `wordfinder.py` | Keyword DB for stopping `open ...` targets (`brain/keywords.json`) |

## Backend/knowledge/ — knowledge layer

| Module | Purpose |
| --- | --- |
| `manager.py` | `get_manager()` singleton; loads applications.json + websites.json, CRUD, `find_application` |
| `entity_resolver.py` | rapidfuzz resolution of spoken names → canonical entity names |
| `memory.py` | `/remember` long-term memory (knowledge_memory table), `build_memory_prompt` |
| `loader.py` | JSON loading helpers |
| `cache.py` | knowledge caching |
| `applications.json`, `websites.json` | the knowledge data itself |

## Backend/hermes/ — LLM layer (Hermes, the complex orchestrator)

| Module | Purpose |
| --- | --- |
| `service.py` | Wiring: orchestrator/sandbox singletons, `chat`, `route_command`, `run_task` |
| `agent.py` | Bounded agent loop (fast path → retrieval → model/tool loop) |
| `router.py` | Fast/complex heuristic gate |
| `orchestrator.py` | Provider wiring + two call kinds: `chat()` (plain, no tools) and `process()` (delegates to HermesAgent with the fast path disabled) |
| `tool_planner.py` | Tool-call **protocol** only: decision/follow-up prompts + `parse_tool_call` (the loop lives in `agent.py`; the duplicate ToolPlanner loop was removed) |
| `tool_registry.py` | Whitelist registry + argument validation for Hermes tools |
| `validator.py` | Phase 3c validation gate for tool calls |
| `retriever.py` | Hybrid RAG over SQL/knowledge/sandbox/history (no vector DB) |
| `sandbox.py` | TaskSandbox + `resolve_sandbox_root` (one canonical root: `Backend/sandbox`, cwd-independent) |
| `conversation.py` | Session history in conversation_messages table |
| `models.py` | Task, ModelRequest, ProviderResponse API models |
| `routes.py` | `/hermes/*` router: sandbox, status, tools, chat |
| `config/` | `HermesConfig` dataclass + env loader |
| `providers/` | AIProvider adapters: local (Ollama), openrouter, openai_compatible + manager/registry/exceptions |
| `tools/` | The 10 registered tools (see TOOLS.md) |
| `main.py` | Standalone Hermes test loop |

## Backend/skills/ — skills

Ten skills with `manifest.json` + `main.py` (see SKILLS.md). Plus:

| Module | Purpose |
| --- | --- |
| `registry.py` | Manifest-based discovery, instantiation, enable/disable |
| `base.py` | `BaseSkill` ABC (execute(intent) → dict) |
| `automation_engine/engine.py` | Assistant registry (`register_assistant`, `run_assistant`); the unreachable `run(event)` event pipeline was removed |

## Backend/hands/desktop/ — physical layer (the Desktop Hand)

| Module | Purpose |
| --- | --- |
| `hand.py` | DesktopHand: validation-gated action dispatch |
| `input.py` | Keyboard/mouse (pyautogui stack, lazy) |
| `filesystem.py` | File actions |
| `processes.py` | Process lookup/termination (psutil) |
| `windows.py` | Window management (pygetwindow/pywin32) |
| `browser.py` | URL opening primitives |
| `capabilities.py` | Implemented/planned capability report (`--capabilities`) |
| `models.py` | DesktopRequest/DesktopResult |

## Other Backend packages

| Package | Purpose |
| --- | --- |
| `connectors/` | BaseConnector, registry, Google Calendar (service+auth+web OAuth) |
| `database/` | SQLite manager + schema (`models.py`), profiles.py (browser profiles), cache/browser_cache.py (in-memory session state) |
| `events/` | EventBus (sync pub/sub, history, wildcards) |
| `speech/` | recorder.py (sounddevice), speech_to_text.py (faster-whisper) |
| `utils/` | logger, voice.py (SAPI/PowerShell TTS), spoken_replies.py (voice responder), telemetry.py |
| `scripts/` | check_no_db_staged.py (git hook helper), clean_sandbox.py |
| `UI/` | Dashboard: chat, dashboard, history, knowledge, memory, settings, skills pages + components |

## Clients & frontends

| Path | Status |
| --- | --- |
| `Desktop/client/sarthi_client/` | tkinter client (gui/controller/backend/config); ships as `Desktop/dist/sarthi.exe` via `sarthi_client.spec` |
| `Backend/UI/` | Dashboard served at `/ui` — active |
| `flutter/` | Placeholder README only — nothing implemented |
| `apk/` | Placeholder README only — nothing implemented |

## Tests

`tests/` — 55 files (49 pytest-collected, 1127 tests; 6 manual smoke
scripts). Layout mirrors the packages
(test_brain_engine, test_hermes_*, test_ai_chain, test_backend_api, ...).
See TESTING.md.
