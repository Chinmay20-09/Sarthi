# Contributing to Sarthi

Sarthi is a local-first AI desktop assistant. This guide explains how the
project is organized, who owns what, and how to add capabilities without
breaking the architecture. Read it before your first PR.

---

## Project Structure

```
brain/            Core intelligence pipeline (Interpreter → Planner →
                  Resolver → Executor). brain/engine.py is the public entry point.
hands/            Physical execution layer. The Desktop hand
                  (hands/desktop/) performs validated Windows actions
                  (launch, keyboard, clipboard, scoped files, processes);
                  hands/desktop/capabilities.py is the only action
                  allow-list. Hands execute; they never reason.
knowledge/        Entity knowledge base. KnowledgeManager (singleton) is the ONLY
                  public interface; loader.py is internal JSON I/O.
skills/           Pluggable capabilities. One folder per skill with manifest.json.
                  skills/registry.py is the ONLY discovery mechanism.
hermes/           Conversational layer: providers (local Ollama / OpenRouter /
                  OpenAI-compatible), tool bridge, sandbox execution records,
                  /hermes/* API routes.
connectors/       External service integrations (Google Calendar today).
database/         SQLite access. DatabaseManager is the only connection owner;
                  all table schemas live in database/models.py.
events/           EventBus — decoupled publish/subscribe.
speech/           Audio: recorder, Whisper transcription (push-to-talk).
utils/            Shared helpers (logger, voice announcements, telemetry).
UI/               Static web interface served by api.py (/ui).
api.py            FastAPI server — the ONLY API boundary for the UI.
config.py         Central configuration (app paths/ports; Hermes uses .env).
tests/            Pytest suite (713 tests). Run with `python -m pytest tests/`.
```

## Development Setup

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows (source .venv/bin/activate on macOS/Linux)
pip install -e ".[dev]"
# Optional capability stacks:
pip install -e ".[automation]"   # AI-chain laptop automation
pip install -e ".[browser]"      # Browser Awareness (Playwright)
```

Copy `.env.example` → `.env` and fill in secrets if you work on Hermes
providers or connectors. `.env` is gitignored — never commit it.

**Checks before committing:**

```bash
python -m pytest tests/ -q     # full suite
ruff check .                   # lint
ruff format --check .          # format
python main-test.py            # smoke test
```

Pre-commit hooks (ruff, smoke test, no-database-files guard) are configured
in `.pre-commit-config.yaml`; the same checks run in CI (`.github/workflows/ci.yml`).

## Architecture Overview

The canonical, code-verified architecture document is **`ARCHITECTURE.md`** —
read it for the pipeline, Hermes/provider abstraction, Browser Awareness,
configuration and persistence. The short version:

```
UI (static pages) ──> api.py (FastAPI) ──> BrainEngine.process(text)
                                              │  interpret → plan → resolve → execute
                                              ▼
                                     Executor dispatches to:
                                       1. built-in handlers (open/browse/remember/...)
                                       2. registered skills (fallback pool, NLP last)
                                       3. NLP skill ──> Hermes (chat or tool bridge)
Skills ──> KnowledgeManager ──> KnowledgeLoader ──> knowledge/*.json
Hermes ──> ToolRegistry ──> existing skills (never a second executor)
Brain ──> BrowserAwarenessSkill ──> inspector ─> Hermes observes ─> validate ─> executor
Executor/Skills ──> DesktopHand (hands/desktop/) ──> Windows
                    (explicit paths/pids only; capability allow-list;
                     structured DesktopResult; no shell, no code execution)
```

**Data contract of the pipeline:** `Intent(action, target, confidence, site, raw_text)`.
Skills receive an `Intent` and return a dict with `success`, `status`, `result`
(visual cards go in `result.visual`), and `error`. Skills that own an intent
they cannot fulfill return `handled: True` so later fallbacks don't override them.

**Registries (one owner per concern — do not create parallel systems):**

| Registry | Module | Owns |
|---|---|---|
| Skills | `skills/registry.py` | skill discovery + enable/disable |
| Hermes tools | `hermes/tool_registry.py` | tools Hermes may request |
| Connectors | `connectors/registry.py` | external service connectors |
| Entities | `knowledge/manager.py` | application/website/device knowledge |

## Module Ownership

| Module | Owner responsibility | Don't touch without discussion |
|---|---|---|
| `brain/` | Pipeline orchestration, intent model | `brain/executor.py` dispatch semantics |
| `knowledge/` | Entity data + resolution | `knowledge/manager.py` schema (applications.json v2 categories) |
| `skills/registry.py` | Skill discovery | `skills/base.py` interface |
| `hermes/` | Conversational layer + tool bridge | `hermes/tool_registry.py` allow-list |
| `hermes/providers/` | Provider adapters + registry | `registry.py` selection/fallback semantics |
| `skills/browser_awareness/` | Validated web inspection | `schemas.py` validation gate, `executor.py` allow-list |
| `connectors/` | External integrations | `connectors/base.py` interface |
| `database/models.py` | All table schemas | schema changes need a migration note |

## Where to Add Things

### Adding a Skill

1. Create `skills/<skill_id>/` with:
   - `manifest.json` — `id`, `name`, `description`, `version`, `enabled`,
     `commands` (see `skills/app_launcher/manifest.json` for the shape).
   - `main.py` — a `BaseSkill` subclass implementing `execute(intent) -> dict`.
     Constructor-inject `knowledge_manager` / `event_bus` via `BaseSkill`
     when you need them (`self.knowledge`, `self.events`).
2. That's it. `skills/registry.py` auto-discovers the folder; `BrainEngine`
   registers it with the executor on startup.
3. Version rule: a skill's version is bumped whenever its code changes after
   the day it was created — bump **both** `manifest.json` and the
   `BaseSkill.version` attribute in `main.py`.
4. Add tests under `tests/test_<skill_id>.py`.

### Adding a Provider (Hermes)

1. Create `hermes/providers/<name>.py` — a subclass of `AIProvider`
   (`hermes/providers/base.py`): map `ModelRequest` → the provider's wire
   format and the response → `ProviderResponse`; override `capabilities()`
   with only what you actually implement.
2. Register it in `hermes/providers/registry.py` (`create_primary` + aliases).
3. Document the env vars in `.env.example` and `README_ENV.md`.
4. Add tests modeled on `tests/test_provider_abstraction.py` (no live API
   needed — assert on the normalized `ModelRequest`).

That is the entire integration: no Hermes core, Brain, skill, or API changes.
Hermes core must never import a concrete adapter — only the registry may.

### Adding a Desktop Action

1. Add the action (and its argument spec) to a capability in
   `hands/desktop/capabilities.py` — the allow-list is the security
   boundary, so review additions like a security change.
2. Implement the backend (a private method on `DesktopHand` in
   `hand.py`, or a function in the relevant module: `processes.py`,
   `windows.py`, `input.py`, `filesystem.py`, `browser.py`).
3. Return a plain dict (`message` + payload keys) or a `DesktopResult`
   — never raise past `execute()` for expected failures.
4. Add tests to `tests/test_desktop_hand.py` with mocked OS backends.

Never: execute shell commands or arbitrary code, resolve names to paths
inside the hand (that is the knowledge layer's job), or guess screen
coordinates as a strategy. Planned capabilities (WINDOW_CONTROL, SHELL)
must not be implemented without a design review — SHELL in particular
needs an explicit allow-list gate.

### Adding a Connector

1. Create `connectors/<service>/` with a `BaseConnector` subclass
   (see `connectors/google_calendar/` for the reference implementation).
2. Implement `metadata`, `get_auth_url()`, `handle_auth_callback()`,
   `disconnect()`, `is_connected()`, `execute_tool()`.
3. Register it in `connectors/registry.py` `discover()`.
4. Add API endpoints under the `api.py` connectors section, or your own
   router included in `api.py`.

Connectors are independent: adding one never requires changes to `brain/`,
`knowledge/`, or the executor.

### Adding an API endpoint

Routes belong in `api.py` or a router mounted there (see `hermes/routes.py`,
`skills/browser/routes.py`). The UI talks to the API only — never to internal
modules directly. Update the API table in `README.md` when you add an endpoint.

## Hermes Contribution Boundary

Hermes is the conversational/orchestration layer — **it is not a second
brain and it does not author code**. Today Hermes:

- answers conversationally (NLP fallback skill),
- requests *registered* tools through `hermes/tool_registry.py` (argument
  validation before any tool runs, bounded loop, no code/shell access),
- records every task in the sandbox (`hermes/sandbox.py`),
- observes pages in Browser Awareness but never controls the browser
  (its recommendations pass `validate_inspection` before execution).

Hermes **may** use existing skills, the tool bridge, the sandbox, Browser
Awareness, and knowledge lookups. Hermes **must not** rewrite brain,
interpreter, resolver, executor, or arbitrary core files, and must not
bypass `ToolRegistry` or the browser-action validation gates.

**Planned (not yet implemented):** skill authoring by Hermes. When that
lands, it must follow the same pattern as Browser Awareness — Hermes
*proposes* (skill folder + manifest + tests), the Brain *validates*
(manifest shape, `BaseSkill` interface, tests pass), and only then the
skill is *registered*. Never register a failed/unvalidated proposal.

## Testing

```bash
python -m pytest tests/ -q            # everything
python -m pytest tests/test_<area>.py  # one area
```

Boundary tests live in `tests/test_pipeline_compatibility.py` — if you
change the shape of scanner output, knowledge entities, `Intent`, or the
skill result dict, run that file first.

Rules:

- New skills and connectors must ship with tests.
- Tests must not require a live Ollama, Chrome, or real hardware —
  mock providers/skills/browser components (see
  `tests/test_browser_awareness.py` for the pattern).
- Never write to the real `knowledge/*.json`, the database, or `sandbox/`
  from a test — use `tmp_path` fixtures.

## Documentation Rules

- **Code is the source of truth.** README, docs/, and this file must
  describe reality.
- Update `README.md` when you add an endpoint, skill, or dependency.
- Update `docs/ARCHITECTURE_NOTES.md` when you move a module or change a
  canonical import.
- Mark planned functionality as planned. Never document an endpoint or
  feature as implemented unless it exists.
- If a doc and the code disagree, fix the doc unless the architecture
  clearly requires a code change.

## Files You Should NOT Modify (without discussion)

- `knowledge/applications.json` — generated by the scanner; edit the
  scanner, not the output (it is gitignored and machine-specific).
- `database/sarthi.db` and any `*.db*` files — personal data, never
  committed (a pre-commit hook blocks them).
- `sandbox/`, `sandbox_test/` — Hermes runtime records (gitignored; the
  tracked copies predate the ignore rule — they get untracked, not edited).
- `hermes/tool_registry.py` allow-list — adding a tool here grants Hermes
  a new capability; review it like a security change.
- `brain/executor.py` dispatch order — the NLP fallback must stay last.
- `hands/desktop/capabilities.py` — this allow-list defines everything the
  Desktop hand may ever do; adding an action grants a new OS capability.
- `skills/browser_awareness/executor.py` selector allow-list and
  `schemas.py` validation gate — these are the browser safety boundary.

## Getting Help

Open an issue with the affected module. Include the output of
`python -m pytest tests/test_<area>.py -q` and, for pipeline issues,
`python -m pytest tests/test_pipeline_compatibility.py -q`.