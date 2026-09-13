# Project state (observed)

Snapshot of the repository as of this documentation reset (2026-09-13).
Facts only; plans are clearly separated.

## Current architecture (one paragraph)

FastAPI backend (`Backend/api.py`, 46 endpoints) serving a tkinter desktop
client and a static web dashboard. Commands flow through a deterministic
pipeline — interpreter → pass-through planner → fuzzy resolver →
handler/skill executor — and, when that fails and a heuristic router calls
the request complex, through a bounded Hermes agent loop (retrieval → model →
validated tools). Ten manifest-discovered skills provide apps, browser,
browser-awareness, project tracking, speech, scanning, personal context,
user config, conversational fallback, and AI chaining. LLM access is
provider-abstracted with a local Ollama default.

## Working capabilities (verified by code + passing tests)

- Deterministic command pipeline with compound command support
  ("open X and search/play Y"), slash commands, site-aware search/play
- Open/close apps and websites; unknown-app scan/browser-search fallback
- AI chaining (ChatGPT→Gemini by default; 7 sites) with dry-run planning,
  DOM-assisted locating, hands-off safety, run transcripts, sandbox records
- Browser awareness loop for arbitrary sites (Selenium/Playwright + bs4)
- Bounded Hermes agent with 10 whitelisted tools and hybrid retrieval
- Complexity router (pure heuristics) gating the fallback
- /remember memory, session history, sandbox with /clean semantics
- Project tracking over GitHub; Google Calendar connector (OAuth web + desktop)
- Voice input (faster-whisper) and voice output (SAPI TTS + spoken replies
  for every response, toggleable)
- Skill registry with enable/disable; event bus; test (dry-run) mode
- In-app test runner with hardware telemetry

## Partially implemented

- Multi-step planning: `brain/planner.py` is a locked pass-through
- AutomationEngine assistant generation: `analyze` stub, `run(event)` unused
- Browser extension bridge: `/browser/action` placeholder, no extension
- Desktop hand: production use limited to `close`; standalone agent has no
  IPC server (manual CLI only)

## Current entry points

- `Backend/sarthi.bat` / `python Backend/api.py` (server)
- `python Desktop/run.py` / `Desktop/dist/sarthi.exe` (client)
- `python Backend/main.py` (voice CLI), `Backend/desktop_agent.py` (hand CLI)
- `python -m hermes.main`, `python -m ...ai_chain.calibrate`,
  `python Backend/scripts/clean_sandbox.py`

## Current skills (10)

app_launcher, automation_engine, browser, browser_awareness,
natural_language_processor, personal_context, project_tracker, scanner,
speech, user_config — all registered and enabled.

## Current agents (4)

HermesAgent (production loop), HermesOrchestrator+ToolPlanner (chat/task
processor), BrainAssistant (assistant.json generator), Browser Awareness
manager loop.

## Current storage

SQLite `Backend/database/sarthi.db` (10 tables), Hermes sandbox
(`sandbox/tasks` + index.json), knowledge JSON files, ai_chain run folders,
skill manifests, calibration files.

## Current tests

52 files / 1021 tests, all passing at documentation time. See TESTING.md for
the untested surface (real RPA runs, real LLM/browser I/O, CLIs, /test/run).

## Known limitations

- Voice CLI and /listen require the undeclared sounddevice/faster-whisper
  stack; voice output requires Windows.
- Real AI-chain runs need one-time logins in the automation Chrome profile
  and site calibration; UI changes can degrade to coordinate-scan fallback.
- The complexity router keys the fast-path verdict on the first word; polite
  prefixes ("please open chrome") route to Hermes (costs a retrieval, not a
  failure).
- `HERMES_SANDBOX_PATH` is cwd-relative → two sandbox roots can exist.
- LAN exposure (0.0.0.0 bind) has no authentication by design decision
  recorded in api.py CORS comments.

## Known divergence & dead/unused components

See [DIVERGENCE.md](DIVERGENCE.md) (12 items) and
[DEAD_CODE.md](DEAD_CODE.md) (9 items). Highlights: two model-driven tool
loops in production; chain-default misfires on AI-mentioning commands; two
conversation tables; two live sandbox roots; pystray declared but unimported;
v1.7 DOM chain engine production-dead.

## PLANNED (not implemented — placeholder evidence only)

- Flutter client (`flutter/README.md` — reserved, empty)
- Android APK distribution (`apk/README.md` — reserved, empty)
- Brain ↔ Desktop-agent IPC (`desktop_agent.py` docstring seam)
- Real multi-step planning in the brain pipeline
