# Development guide

How to set up, navigate and safely modify Sarthi.

## Development setup

1. **Requirements**: Windows 10/11 (the Desktop hand, TTS and ai_chain
   laptop control are Windows-specific), Python ≥ 3.10, Git.
   Optional: Ollama (local LLM), Chrome (browser automation), a microphone
   (voice input).
2. **Clone and create a virtual environment**:

   ```bash
   python -m venv .venv
   source .venv/Scripts/activate   # Git Bash on Windows
   ```

3. **Install**:

   ```bash
   pip install -e .                # core runtime
   pip install -e ".[dev]"         # + ruff, pytest
   pip install -e ".[automation]"  # + laptop control (pyautogui/keyboard/pywin32)
   pip install -e ".[browser]"     # + selenium/beautifulsoup4/playwright
   pip install sounddevice faster-whisper   # voice input (undeclared extras)
   ```

4. **Configure**: copy `.env.example` to `.env` and set provider settings.
   Default is the local Ollama provider (`HERMES_PROVIDER=local`,
   `LOCAL_HERMES_MODEL=hermes3:8b`) — no API keys needed. If you run Ollama,
   `ollama pull hermes3:8b` (or point `LOCAL_HERMES_MODEL` at a model you
   have). Desktop Agent IPC settings (`SARTHI_DESKTOP_AGENT_*`) also live in
   `.env` — see [ARCHITECTURE.md](ARCHITECTURE.md#brain--desktop-agent-ipc-implemented-2026-09-16).
5. **Verify**: `start.bat` (or `Backend\sarthi.bat`), then open
   <http://127.0.0.1:8000> — the dashboard should load and `/health` should
   report `{"assistant": "Sarthi", "status": "Running"}`.

## Repository structure (useful level)

```text
Backend/
  api.py            FastAPI app — all HTTP endpoints, /command pipeline
  config.py         central constants (paths, speech, API bind, DESKTOP_AGENT_*)
  brain/            deterministic pipeline (the Sarthi Brain)
  hermes/           LLM layer: agent loop, router, validator, tools, providers
  skills/           11 manifest-discovered skills
  hands/            execution layer: base.py (Hand), desktop/ (local),
                    local.py (mode selection), remote.py + transport.py (IPC)
  knowledge/        apps/websites JSON store + entity resolver + memory
  database/         SQLite manager + schema + profiles + caches
  connectors/       Google Calendar connector (+ registry)
  events/           in-process pub/sub event bus
  speech/           recorder + faster-whisper STT
  utils/            logger, TTS voice, spoken replies, telemetry
  desktop_agent.py  standalone hand CLI + IPC server (--server)
  UI/               static dashboard served at /ui
  scripts/          clean_sandbox.py, check_no_db_staged.py
Desktop/
  client/sarthi_client/   tkinter client (HTTP-only boundary in backend.py)
  run.py            dev launcher; dist/sarthi.exe = packaged client
tests/              56 test files (50 pytest-collected); see TESTING.md
docs/               client/ dev/ agent/ archive/
flutter/, apk/      reserved placeholders — nothing implemented
start.bat           root launcher delegating to Backend\sarthi.bat
```

## Important commands

| Command | Purpose |
| --- | --- |
| `start.bat` / `Backend\sarthi.bat` | Start the backend (visible window); `background` for windowless |
| `python Backend/api.py` | Direct server start |
| `python Desktop/run.py` | Run the desktop client in dev mode |
| `pytest` | Full test suite (see [TESTING.md](TESTING.md)) |
| `ruff check Backend tests` | Lint; `ruff format` to format |
| `python Backend/desktop_agent.py --capabilities` | Inspect the hand's capability report |
| `python Backend/scripts/clean_sandbox.py` | Clean the Hermes sandbox |
| `POST /test/run` | In-app smoke runner (60 prompts, test mode, telemetry) |

## Adding or changing a skill

1. Create `Backend/skills/<id>/` with two files:
   - `manifest.json` — metadata (id, name, version, description, actions).
     Copy the shape from an existing skill.
   - `main.py` — must export a `BaseSkill` subclass
     (`skills/base.py`): implement `execute(intent: Intent) -> dict`.
2. Follow the **result contract**: return a plain dict
   `{success, status, result, error, handled?}` — never raise for control
   flow. Set `handled: True` only when your skill owns a failed intent
   (the executor stops the skill walk there).
3. Honour test mode: check `brain.modes.get_test_mode()` for anything that
   touches the real machine (see `skills/browser_awareness` for the pattern).
4. The registry discovers the skill automatically on next start
   (`skills/registry.py` scans `*/manifest.json`). No code registration is
   needed.
5. Add tests under `tests/test_<id>.py` mirroring existing skill tests.

## Working with the backend

- **Entry point for everything is `BrainEngine.process`** (`brain/engine.py`);
  API routes should stay thin and delegate into brain/skills.
- **Never import `hermes/` from `brain/`** — the only sanctioned brain-side
  path into the LLM layer is the NLP fallback skill importing
  `hermes.service.chat`. The architecture-boundary tests
  (`tests/test_architecture_boundaries.py`) lock this.
- **Hermes tools must delegate** to existing skills/executor — never add
  shell/eval/subprocess execution. New tools go in `hermes/tools/`,
  register in `hermes/tools/__init__.py::register_default_tools`, and must
  pass the `hermes/validator.py` gate.
- **All OS interaction goes through the Hand.** Use
  `hands.local.get_desktop_hand()`; never import Windows-only modules outside
  `hands/desktop/`. `hands/transport.py` and `hands/remote.py` must stay
  importable on Linux/Android (no Windows imports there).
- **All SQL goes through `DatabaseManager`** (`database/manager.py`) — never
  open SQLite directly from a skill. Schema changes go in
  `database/models.py` (idempotent `CREATE TABLE IF NOT EXISTS`).
- **Sandbox paths** must go through `hermes.sandbox.resolve_sandbox_root` —
  never resolve `HERMES_SANDBOX_PATH` against the cwd (AD-01).
- **Line references in docs**: prefer naming functions over line numbers;
  line numbers drift.

## Working with the desktop client

- The client lives in `Desktop/client/sarthi_client/` (gui, controller,
  backend, config). It must talk to the backend **only over HTTP** via
  `backend.py` — the import boundary is test-locked.
- Dev run: `python Desktop/run.py`. Packaging: PyInstaller via
  `Desktop/sarthi_client.spec` (output `Desktop/dist/sarthi.exe`).
- Client dependencies: tkinter (stdlib) + httpx2 only. Do not add backend
  imports to the client.

## Development conventions

- **Lint/format**: ruff (config in `pyproject.toml`; line length 100,
  target py310). Run `ruff check` before committing.
- **Type checking**: mypy is configured but currently cannot run in this
  environment (it aborts on a `.venv/numpy` stub issue — pre-existing, not
  related to project code).
- **Pre-commit**: `.pre-commit-config.yaml` exists; hooks include the DB
  guard.
- **Never commit**: `Backend/database/sarthi.db` (guarded by
  `Backend/scripts/check_no_db_staged.py`), `.env`, `sandbox/`,
  `results/`, `ai_chain/calibration.json`, `Desktop/dist/`.
- **Commits**: one logical change per commit; documentation for a
  structural change belongs in the same change.
- **Testing**: run the relevant tests after any modification — see
  [TESTING.md](TESTING.md) for what is covered and what must be validated
  manually.

## Critical workflow for modifying Sarthi safely

1. Read [ARCHITECTURE.md](ARCHITECTURE.md) for the subsystem you are touching
   and [PROJECT_STATE.md](PROJECT_STATE.md) for its current state.
2. **Respect the boundaries** — deterministic-first routing, one Hermes loop,
   the validator as the only tool gate, the Hand as the only OS surface, the
   HTTP-only client boundary. These are enforced by tests
   (`test_architecture_boundaries.py`, `test_brain_hand_boundary.py`,
   `test_consolidation_routing.py`), so violations fail the suite.
3. Make the change; keep behaviour-preserving edits separate from behaviour
   changes.
4. Run `ruff check` and the relevant pytest files; run the full suite before
   merging anything structural.
5. Manually validate anything the suite cannot cover (real browser, real
   laptop control, real model calls) — see [TESTING.md](TESTING.md).
6. Update the matching section in `ARCHITECTURE.md` / `PROJECT_STATE.md` when
   the change alters documented behaviour.
