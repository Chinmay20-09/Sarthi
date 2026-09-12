# PROJECT_STATE — Sarthi, September 2026

**What Sarthi is:** a local-first Windows-oriented desktop assistant. One
FastAPI process serves a REST API and the web UI; a deterministic pipeline
(Interpreter → Resolver → Executor) runs skills against discovered knowledge;
the Desktop hand is the physical execution layer that touches Windows; Hermes
is the conversational layer for everything else.

## Implemented and stable

- **Core pipeline** — interpreter (compound commands), entity resolution
  (RapidFuzz over 700+ scanned apps + curated websites), executor with
  built-in handlers (open, close, browse, remember/recall/forget, clean) and
  a skill fallback pool. Locked by boundary tests.
- **Desktop hand** (`hands/desktop/`) — the physical execution layer:
  launch/close apps by explicit path/pid, open http/https URLs, keyboard,
  mouse, clipboard, scoped filesystem reads/writes, process and window
  enumeration. Capability allow-list + argument validation + structured
  `DesktopResult`; every action logged; no shell, no code execution, no
  coordinate guessing. Executor and app launcher delegate OS actions to it.
  Standalone entry point: `desktop_agent.py` (future `Sarthi.exe` seam).
- **Skills** — 10 skills with manifest-based discovery, enable/disable, DI
  (knowledge + events). NLP fallback registered last.
- **Knowledge** — scanner → applications.json (v2 categories: favourite /
  ignored / unattended) → EntityResolver; websites with search-and-save
  learning.
- **Hermes** — provider-agnostic orchestrator: local Ollama default,
  OpenRouter / any OpenAI-compatible endpoint opt-in with automatic local
  fallback. Bounded tool loop (4 tools), JSON-validated, sandbox records every
  task and indexes them by query. `GET /hermes/status` for diagnostics.
- **Browser Awareness** — Playwright inspection of arbitrary sites, model
  observes and recommends, pure validation gate, allow-listed safe executor,
  isolated temporary Chrome profile. Independent of the configured provider.
- **Memory & chat** — `/remember` facts (SQLite), persisted chat transcripts,
  per-session Hermes history, conversation mode.
- **API/UI** — complete contract (all UI fetches verified against routes),
  CORS locked to local origins, single-port serving (`:8000`).
- **Connectors** — Google Calendar (OAuth2).
- **Automation engine / ai_chain** — laptop-control RPA loop with hands-off
  voice contract, DOM-regex locating (v1.5), screen-state classifier,
  7 AI sites. Experimental by nature (depends on external site UIs).
- **Tooling** — 713 tests green, ruff lint/format clean, CI on push/PR,
  pre-commit hooks, smoke test.

## Experimental / partially implemented

- **ai_chain** — works, but fragile against site redesigns by design;
  calibration per monitor recommended.
- **Desktop hand input/clipboard/window backends** — depend on the optional
  `automation` extra (pyautogui, pyperclip) and pywin32; without them the
  hand returns structured failures instead of fake successes.
- **Connectors framework** — one real connector; generic "test" endpoint does
  not validate credentials.
- **Test-runner page** (`/test/run` + telemetry dashboard) — functional but
  hardware-metric dependent.

## Known limitations (top ones)

- Planner is a documented pass-through; the interpreter owns compound commands.
- Desktop WINDOW_CONTROL and SHELL capabilities are declared but deliberately
  not implemented (SHELL needs a review gate first). No local IPC between the
  Brain and a standalone desktop agent yet — `desktop_agent.py` is the seam.
- No native tool-calling/vision/streaming in providers (prompt protocol covers
  tools; everything else is deliberately unwired).
- Hermes skill authoring: planned, not implemented.
- `settings.html` Voice & Personality / Privacy toggles are visual previews
  (no backing settings); history and the rest of the UI are wired.
- Mode/test-mode state resets on restart (process-local).
- Windows-only features: scanner, app launching, ai_chain.

## Immediate next steps

1. Untrack gitignored-but-committed runtime data:
   `git rm -r --cached sandbox sandbox_test`.
2. Implement Hermes skill authoring behind the propose → validate → register
   gate (model it on Browser Awareness validation).
3. Add connectors (Gmail first) and back the settings page's Voice &
   Personality / Privacy toggles with real settings.
4. Optionally retire `brain/planner.py` (or implement real decomposition) and
   the test-compat globals in `hermes/routes.py`.

The detailed, verified architecture lives in `docs/ARCHITECTURE.md`; contribution
rules in `docs/CONTRIBUTING.md`.
