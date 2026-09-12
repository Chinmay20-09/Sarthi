# PROJECT_STATE — Sarthi, September 2026

**What Sarthi is:** a local-first Windows-oriented desktop assistant built as
a **client/backend system**. One FastAPI Backend process holds all the
intelligence (REST API + web UI + the deterministic pipeline: Interpreter →
Resolver → Executor over skills and knowledge); thin clients — the Windows
`sarthi.exe` Desktop client today, Flutter/Android later — talk to it over
HTTP (`POST /command`). The Desktop hand remains the physical execution layer
that touches Windows; Hermes is the conversational layer for everything else.

## Repository layout (client/backend, September 12, 2026)

```
Sarthi/
├── Backend/     # THE INTELLIGENCE — api.py, brain/, knowledge/, skills/,
│               #   hermes/, hands/, speech/, connectors/, database/, UI/,
│               #   config.py, sarthi.bat (launcher), .env
├── Desktop/     # Windows client (sarthi.exe + source in client/sarthi_client/)
├── flutter/     # reserved — future Flutter client (not implemented)
├── apk/         # reserved — future Android distribution (not implemented)
├── tests/       # the single, project-wide pytest suite (root)
└── docs/        # ARCHITECTURE.md, PROJECT_STATE.md, CHANGELOG.md, ...
```

The Desktop client contains **no** assistant intelligence: it sends
`{"query": ...}` to the Backend and displays `{success, response, data}`.
This boundary is locked by `tests/test_architecture_boundaries.py`.

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
  Standalone entry point: `Backend/desktop_agent.py` (future Desktop-Hand seam).
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
  CORS locked to local origins, single-port serving (`:8000`). `/command`
  now speaks a client-independent schema: `{"query": ...}` requests and a
  `{success, response, data}` response envelope (the legacy `{"text": ...}`
  web-UI schema goes through the same pipeline, unchanged).
- **Desktop client** (`Desktop/`, September 12) — a thin tkinter GUI
  (`sarthi.exe`, built from `Desktop/sarthi_client.spec`): Query textbox →
  Send → response area. Only talks HTTP (`Desktop/client/sarthi_client/
  backend.py`); backend URL is configured in one place (`SARTHI_BACKEND_URL`
  env var → `sarthi_client.json` → default `http://127.0.0.1:8000`).
- **Connectors** — Google Calendar (OAuth2).
- **Automation engine / ai_chain** — laptop-control RPA loop with hands-off
  voice contract, DOM-regex locating (v1.5), screen-state classifier,
  7 AI sites. Experimental by nature (depends on external site UIs).
- **Tooling** — 763 tests green (root `pytest` from `Sarthi/`), ruff
  lint/format clean on migrated code, CI on push/PR, pre-commit hooks,
  smoke test (`Backend/main-test.py`).

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
  Brain and a standalone desktop agent yet — `Backend/desktop_agent.py` is the
  seam. The Desktop **client** (`sarthi.exe`) is interface-only by design;
  moving Windows execution (Desktop Hand) into it is future work behind that
  IPC seam.
- No native tool-calling/vision/streaming in providers (prompt protocol covers
  tools; everything else is deliberately unwired).
- Hermes skill authoring: planned, not implemented.
- `settings.html` Voice & Personality / Privacy toggles are visual previews
  (no backing settings); history and the rest of the UI are wired.
- Mode/test-mode state resets on restart (process-local).
- Windows-only features: scanner, app launching, ai_chain.

## Immediate next steps

1. Untrack gitignored-but-committed runtime data:
   `git rm -r --cached Backend/sandbox Backend/sandbox_test` (paths moved
   under Backend/ in the client/backend restructure).
2. Desktop client evolution: move the Desktop Hand behind a local IPC seam
   (Backend/desktop_agent.py) so `sarthi.exe` becomes client + hand.
3. Implement Hermes skill authoring behind the propose → validate → register
   gate (model it on Browser Awareness validation).
4. Add connectors (Gmail first) and back the settings page's Voice &
   Personality / Privacy toggles with real settings.
5. Optionally retire `brain/planner.py` (or implement real decomposition) and
   the test-compat globals in `hermes/routes.py`.

The detailed, verified architecture lives in `docs/ARCHITECTURE.md`; contribution
rules in `docs/CONTRIBUTING.md`.
