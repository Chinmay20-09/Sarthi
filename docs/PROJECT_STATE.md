# Project state (observed)

Snapshot of the repository, updated after the 2026-09-14 architectural
consolidation pass (see CONSOLIDATION_REPORT.md). Facts only; plans are
clearly separated.

## Current architecture (one paragraph)

FastAPI backend (`Backend/api.py`, 46 endpoints) serving a tkinter desktop
client and a static web dashboard. Commands flow through a deterministic
pipeline — interpreter → pass-through planner → fuzzy resolver →
handler/skill executor — and reach Hermes in two cases: before execution when
a task-shaped sentence's only reading is a plain web search, and after a
failure when the heuristic router calls the request complex. Hermes is one
bounded loop (`hermes/agent.py`: retrieval → model → validated tool call,
≤3 iterations) behind one validator and one tool registry; it never controls
the machine directly. Ten manifest-discovered skills provide apps, browser,
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
- AutomationEngine: assistant registration + `assistant.json` generation only;
  the unreachable event pipeline was removed, and a trigger-based lifecycle is
  planned (AD-14)
- Browser extension bridge: `/browser/action` placeholder, no extension
- Desktop hand: production use limited to close/launch; standalone agent has
  no IPC server (manual CLI only)

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

## Current agents (3)

HermesAgent (the one reasoning loop, used by `/command` and `/hermes/chat`),
BrainAssistant (assistant.json generator), Browser Awareness manager loop.
`HermesOrchestrator` is provider wiring + the plain-chat path — it delegates
to HermesAgent and implements no loop of its own.

## Current storage

SQLite `Backend/database/sarthi.db` (10 tables), Hermes sandbox
(**one canonical root** `Backend/sandbox`, resolved cwd-independently by
`hermes.sandbox.resolve_sandbox_root`; `tasks/` + `index.json`), knowledge
JSON files, ai_chain run folders, skill manifests, calibration files.
A stray gitignored repo-root `sandbox/` (4 stale queries) is left in place but
no longer written to.

## Current tests

54 files / 1059 tests, all passing (283 s). See TESTING.md for the untested
surface (real RPA runs, real LLM/browser I/O, CLIs, /test/run).

## Known limitations

- Voice CLI and /listen require the undeclared sounddevice/faster-whisper
  stack; voice output requires Windows.
- Real AI-chain runs need one-time logins in the automation Chrome profile
  and site calibration; UI changes can degrade to the page-copy fallback
  (the coordinate scan grid is disabled unless `AI_CHAIN_COORDINATE_SCAN=1`).
- The complexity router keys part of its verdict on the first word; polite
  prefixes ("please open chrome") score as complex, but the deterministic
  pipeline handles them first, so the verdict never costs a model call.
- A long search query that mentions task verbs ("…and rename them") is
  escalated to Hermes by the task-shaped gate rather than searched literally;
  Sarthi has no filesystem/file tool yet, so Hermes can reason about such a
  task but not execute it (AD-04).
- LAN exposure (0.0.0.0 bind) has no authentication by design decision
  recorded in api.py CORS comments.

## Known divergence & dead/unused components

See [DIVERGENCE.md](DIVERGENCE.md) (12 items, now carrying a status per row),
[DEAD_CODE&Duplicate.md](DEAD_CODE&Duplicate.md) and
[ARCHITECTURAL_DECISIONS.md](ARCHITECTURAL_DECISIONS.md). After the
2026-09-14 pass: one Hermes loop (the duplicate ToolPlanner loop removed),
one sandbox root, the chain-intent misfire closed as not reproducible, the
unreachable automation event pipeline + `analyze` stub + pystray removed.
Still open (deferred, with reasons): the chain's private control layer vs
Hands, browser DOM-reader unification, sandbox→knowledge promotion, the
automation lifecycle, the unified observation contract, `handled` vs
`success` skill semantics, and the `sarthi.bat` bind-address duplication.
Remaining candidates for removal: `ai_chain/browser_automation.py` (v1.7) and
`assistants/brain_assistant/analyzer.py`.

## PLANNED (not implemented — placeholder evidence only)

- Flutter client (`flutter/README.md` — reserved, empty)
- Android APK distribution (`apk/README.md` — reserved, empty)
- Brain ↔ Desktop-agent IPC (`desktop_agent.py` docstring seam)
- Real multi-step planning in the brain pipeline
