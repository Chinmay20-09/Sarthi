# Independent Skill Execution Audit Matrix

Sprint: Independent Skill Execution
Scope: every skill under `backend/skills/`

## Classification Summary

| Skill | Status | Direct CLI | Reusable capability | Hard deps |
|-------|--------|-----------|---------------------|-----------|
| speech | DIRECTLY_EXECUTABLE | `python -m speech` | `record_transcribe` (mic + Whisper) | microphone, sounddevice, scipy, faster_whisper |
| scanner | DIRECTLY_EXECUTABLE | `python -m skills.scanner` | `scan_all` (pure file enumeration) | none (prints to stdout) |
| browser | DIRECTLY_EXECUTABLE | `python -m skills.browser` | `_search`, `_play`, `_get_first_youtube_video` | webbrowser + urllib (stdlib) |
| user_config | DIRECTLY_EXECUTABLE | `python -m skills.user_config` | `set_github_username` / `get_github_username` | SQLite via database.manager |
| personal_context | DIRECTLY_EXECUTABLE | `python -m skills.personal_context` | `get_field` | SQLite via database.manager + allowlisted SAFE_FIELDS |
| project_tracker | DIRECTLY_EXECUTABLE | `python -m skills.project_tracker` | `project_status` / `check_new_repositories` | GitHub username + SQLite via database.manager |
| app_launcher | DIRECTLY_EXECUTABLE | `python -m skills.app_launcher launch <app> --test` | `_launch_path` | DesktopHand (OS) |
| terminal | NOT_EXECUTABLE | (none) | e.g. `_echo` | DesktopHand (local/in-process) |
| natural_language_processor | NOT_EXECUTABLE | (none) | `_user_message` | Brain pipeline (intent) |
| browser_awareness | NOT_EXECUTABLE | (none) | `_plan` (parse only) | Browser + knowledge DB |
| automation_engine | NOT_EXECUTABLE | (none) | `_handle_chain` (parses chains) | LLM + engine |

## Details

### speech
- **Direct CLI**: `python -m speech` (from backend/) — `--help`, `--check`, `--duration`, `--language`, `--quiet`, `--filename`. Exit codes 0/1.
- **Capability**: `record_transcribe()` shared by CLI, backend/main.py, and skills/speech/main.py.
- **Dependencies**: `sounddevice` (mic), `scipy.io.wavfile`, `faster_whisper` (WhisperModel).
- **Verification**: `--check` exits 0; imports verified; transcription tested with synthetic wav.

### scanner
- **Direct CLI**: `python -m skills.scanner` — `--quiet`, `--json`, `--check`. Exit codes 0/1.
- **Capability**: `scan_all()` from `skills.scanner.application_scanner` — standard library only.
- **Dependencies**: stdlib only (pathlib, subprocess, tempfile, json).
- **Verification**: `--check` exits 0; 729 applications discovered.

### browser
- **Direct CLI**: `python -m skills.browser` — `--open <name>`, `--search <query>`, `--play <media>`, `--list`, `--check`. Exit codes 0/1.
- **Capability**: `BrowserSkill` with `_search`, `_play`, `_get_first_youtube_video` — `webbrowser` + `urllib` stdlib.
- **Verification**: `--check` exits 0; website list verified (6 sites from knowledge file).

### user_config
- **Direct CLI**: `python -m skills.user_config` — `--get`, `--set <username>`, `--check`. Exit codes 0/1.
- **Capability**: `UserConfigSkill.set_github_username()` / `get_github_username()` — SQLite via `database.manager`.
- **Verification**: `--check` exits 0; username set/get/verify round-trip tested.

### personal_context
- **Direct CLI**: `python -m skills.personal_context` — `--list`, `--get <field>`, `--check`. Exit codes 0/1.
- **Capability**: `PersonalContextService.get_field()` — SQLite via `database.manager`; allowlisted `SAFE_FIELDS`.
- **Verification**: `--check` exits 0; `list` and `get github` verified (repositories counted, field values returned).

### project_tracker
- **Direct CLI**: `python -m skills.project_tracker` — `status`, `check`, `sync`, `list`, `--check`. Exit codes 0/1.
- **Capability**: `GitHubProjectSkill.project_status()` / `check_new_repositories()` — SQLite via `database.manager`.
- **Verification**: `--check` exits 0; `status` and `list` verified (5 projects, 27 tracked).

### app_launcher
- **Direct CLI**: `python -m skills.app_launcher` — `launch <app> [--test]`, `list`, `check`. Exit codes 0/1.
- **Capability**: `AppLauncherSkill` via `KnowledgeManager.find_application()` + `_launch_path` (DesktopHand).
- **Verification**: `--check` exits 0; `launch <app> --test` verified (729 apps found, test launch of Code/notepad).

### terminal
- **Status**: NOT_EXECUTABLE as a standalone CLI.
- **Reason**: delegates every command to `hands.local.get_desktop_hand()` (DesktopHand in-process), which opens OS-level desktop capabilities. No pure core without the hand.

### natural_language_processor
- **Status**: NOT_EXECUTABLE as a standalone CLI.
- **Reason**: `_user_message` depends on the brain intent pipeline (intent model, modes).

### browser_awareness
- **Status**: NOT_EXECUTABLE as a standalone CLI.
- **Reason**: `_plan` only parses URLs and objectives (pure), but the full skill needs a browser session and the knowledge database.

### automation_engine
- **Status**: NOT_EXECUTABLE as a standalone CLI.
- **Reason**: `_handle_chain` depends on parsing LLM-generated chains; full execution needs `AutomationEngine` (LLM).

## Common CLI Convention (Phase 2)

Every directly-executable skill uses:

- `--help`: explain available operations and arguments.
- `--check`: verify that the skill and its required dependencies can initialize.
- Capability-specific commands or arguments where meaningful.
- Clear success and error output.
- Appropriate process exit codes (0 success, 1 error).
- No mandatory API-server startup unless the skill explicitly requires an external service.

## Verification Commands

```bat
:: Speech (primary deliverable)
cd Backend
python -m speech --help
python -m speech --check
python -m speech --duration 3

:: Scanner
python -m skills.scanner --help
python -m skills.scanner --check
python -m skills.scanner --quiet

:: Browser
python -m skills.browser --help
python -m skills.browser --check
python -m skills.browser search "python tutorial" --test

:: user_config
python -m skills.user_config --help
python -m skills.user_config check
python -m skills.user_config set testuser
python -m skills.user_config get

:: personal_context
python -m skills.personal_context --help
python -m skills.personal_context check
python -m skills.personal_context list
python -m skills.personal_context get github

:: project_tracker
python -m skills.project_tracker --help
python -m skills.project_tracker check --check
python -m skills.project_tracker status
python -m skills.project_tracker list

:: app_launcher
python -m skills.app_launcher --help
python -m skills.app_launcher check --check
python -m skills.app_launcher list
python -m skills.app_launcher launch code --test
```

## Unified Entry Point — `python -m sarthi`

A single `sarthi` package (`backend/sarthi/`) serves as the unified entry point for all skills:

- `python -m sarthi list` — list all installed skills (id, name, version, commands)
- `python -m sarthi list --json` — list skills as JSON
- `python -m sarthi help` — show overview
- `python -m sarthi help <skill>` — show help for a specific skill
- `python -m sarthi <skill-id> <args>` — run any skill directly

Example:
    python -m sarthi speech --duration 3

Every skill is independently executable (via its own `__main__.py`) AND can be
triggered through the unified `sarthi` entry point. The same underlying
capability runs for both the CLI and the Sarthi skill/adapter layers.

### Delivery Summary

| Skill | Direct CLI | Status |
|-------|-----------|--------|
| speech | `python -m speech` | DIRECTLY_EXECUTABLE |
| scanner | `python -m skills.scanner` | DIRECTLY_EXECUTABLE |
| browser | `python -m skills.browser` | DIRECTLY_EXECUTABLE |
| user_config | `python -m skills.user_config` | DIRECTLY_EXECUTABLE |
| personal_context | `python -m skills.personal_context` | DIRECTLY_EXECUTABLE |
| project_tracker | `python -m skills.project_tracker` | DIRECTLY_EXECUTABLE |
| app_launcher | `python -m skills.app_launcher` | DIRECTLY_EXECUTABLE |
| terminal | (none) | NOT_EXECUTABLE |
| natural_language_processor | (none) | NOT_EXECUTABLE |
| browser_awareness | (none) | NOT_EXECUTABLE |
| automation_engine | (none) | NOT_EXECUTABLE |

### Unified Entry Point

| Command | Description |
|---------|-------------|
| `python -m sarthi list [--json] [--enabled-only]` | List all skills |
| `python -m sarthi help [<skill>]` | Show help (overview or per skill) |
| `python -m sarthi <skill-id> ...` | Run a skill directly |

## Skills Remaining Partially Executable

- **terminal**: needs DesktopHand (hardware/desktop capability).
- **natural_language_processor**: needs the brain intent pipeline.
- **browser_awareness**: needs a real browser session and the knowledge database.
- **automation_engine**: needs LLM + `AutomationEngine`.
