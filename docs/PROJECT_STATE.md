# PROJECT_STATE — Sarthi, September 2026

**What Sarthi is:** a local-first Windows-oriented desktop assistant. One
FastAPI process serves a REST API and the web UI; a deterministic pipeline
(Interpreter → Resolver → Executor) runs skills against discovered knowledge;
Hermes is the conversational layer for everything else.

## Implemented and stable

- **Core pipeline** — interpreter (compound commands), entity resolution
  (RapidFuzz over 700+ scanned apps + curated websites), executor with
  built-in handlers and a skill fallback pool. Locked by boundary tests.
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
- **Tooling** — 580 tests green, ruff lint/format clean, CI on push/PR,
  pre-commit hooks, smoke test.

## Experimental / partially implemented

- **ai_chain** — works, but fragile against site redesigns by design;
  calibration per monitor recommended.
- **Connectors framework** — one real connector; generic "test" endpoint does
  not validate credentials.
- **Test-runner page** (`/test/run` + telemetry dashboard) — functional but
  hardware-metric dependent.

## Known limitations (top ones)

- Planner is a documented pass-through; the interpreter owns compound commands.
- No native tool-calling/vision/streaming in providers (prompt protocol covers
  tools; everything else is deliberately unwired).
- Hermes skill authoring: planned, not implemented.
- `history.html` / `settings.html` UI pages are static mockups.
- Mode/test-mode state resets on restart (process-local).
- Windows-only features: scanner, app launching, ai_chain.

## Immediate next steps

1. Untrack gitignored-but-committed runtime data:
   `git rm -r --cached sandbox sandbox_test`.
2. Implement Hermes skill authoring behind the propose → validate → register
   gate (model it on Browser Awareness validation).
3. Add connectors (Gmail first) and remove the mockup status of the settings
   page or wire it.
4. Optionally retire `brain/planner.py` (or implement real decomposition) and
   the test-compat globals in `hermes/routes.py`.

The detailed, verified architecture lives in `ARCHITECTURE.md`; contribution
rules in `CONTRIBUTING.md`.
