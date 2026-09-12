# 🧠 Sarthi — Local-First AI Desktop Assistant

**Sarthi** is a local-first, privacy-respecting AI Desktop Assistant that runs entirely on your machine. It understands natural language commands, recognizes speech, discovers installed applications, and executes tasks through a modular skill system.

> **Version:** 1.0.4 Hyperion
> **Status:** Production-ready
> **Python:** 3.10+

---

- [Features](#-features)
- [Quick Start](#-quick-start)
- [Architecture](#-architecture)
  - [Brain Pipeline](#brain-pipeline)
  - [Knowledge System](#knowledge-system)
  - [Skill System](#skill-system)
  - [Clean Architecture Refactoring](#clean-architecture-refactoring)
- [Knowledge Base System (Deep Dive)](#-knowledge-base-system-deep-dive)
  - [Application Scanner](#1-application-scanner)
  - [Knowledge Loader](#2-knowledge-loader)
  - [Knowledge Manager](#3-knowledge-manager)
  - [Entity Resolver](#4-entity-resolver)
  - [Application Executor](#5-application-executor)
  - [Future Entity Types](#6-future-entity-types)
- [API Reference](#-api-reference)
- [Web UI](#-web-ui)
- [Testing](#-testing)
- [Development](#-development)
- [Roadmap](#-roadmap)
- [Contributing](#-contributing)
- [License](#-license)

> **Docs:** this README covers setup and a high-level tour. The verified,
> detailed architecture lives in **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)**;
> current status/limitations in **[docs/PROJECT_STATE.md](docs/PROJECT_STATE.md)**;
> contribution rules in **[docs/CONTRIBUTING.md](docs/CONTRIBUTING.md)**; provider
> environment variables in **[docs/README_ENV.md](docs/README_ENV.md)**.

---

## ✨ Features

| Capability | Description |
|---|---|
| 🎤 **Speech Recognition** | Whisper-based transcription of voice commands |
| 🧠 **Brain Pipeline** | Interpret → Plan → Resolve → Execute |
| 📱 **Entity Resolution** | Fuzzy matching for 700+ discovered applications + websites |
| 🛠️ **Skill System** | Pluggable skills: GitHub tracker, automation engine, browser |
| 🗄️ **Knowledge Base** | Auto-discovers apps via scanner; stores entity data in JSON |
| 🌐 **FastAPI Server** | REST API with CORS for the web UI |
| 🎨 **Web UI** | 6-page dashboard with sidebar, dock, and HUD-style interface |
| 🏠 **Privacy-First** | 100% local — no cloud dependencies |
| 📦 **700+ Discovered Apps** | Automatic scanning of Windows locations |

---

## 🚀 Quick Start

### Prerequisites

- **Python 3.10+**
- **Windows** (for speech/scanner features; core logic is cross-platform)
- **Microphone** (for voice commands)

### Installation

```bash
# 1. Clone the repo
git clone https://github.com/your-username/sarthi.git
cd sarthi

# 2. Create virtual environment
python -m venv .venv
.venv\Scripts\activate       # Windows
source .venv/bin/activate    # macOS/Linux

# 3. Install dependencies (editable install pulls everything from pyproject.toml)
pip install -e .

# Optional capability stacks (installed lazily, not required for core)
pip install -e ".[automation]"   # AI-chain laptop automation
pip install -e ".[browser]"      # Browser Awareness (Playwright)

# 4. Install dev dependencies (optional)
pip install -e ".[dev]"

# 5. Run tests (optional)
python -m pytest tests/ -v
```

### Run the API Server

```bash
python api.py
# → http://127.0.0.1:8000 (redirects to UI)
# → http://127.0.0.1:8000/health (health check)
```

### Run the Scanner

```bash
python -c "from knowledge.manager import get_manager; get_manager().refresh_applications()"
# Discovers 700+ applications and saves to knowledge/applications.json
```

### Run the CLI (Voice)

```bash
python main.py
# Press ENTER to speak a command
```

### Run Sarthi Windowless (Optional)

`start.bat background` starts the API and UI servers under `pythonw` (no
console windows) and opens your browser once the API is healthy — useful
for launching Sarthi from a script or shortcut. Run `start.bat` manually
for the classic dev experience with visible server windows.

### Open the Web UI

Open `http://127.0.0.1:8000` in your browser while the API is running — it automatically serves the dashboard.

### Try It via cURL

```bash
# Process a text command
curl -X POST http://127.0.0.1:8000/command \
  -H "Content-Type: application/json" \
  -d '{"text": "open chrome"}'

# See what apps are discovered
curl http://127.0.0.1:8000/applications

# List installed skills
curl http://127.0.0.1:8000/skills

# Get knowledge base stats
curl http://127.0.0.1:8000/knowledge
```

---

## 🏛️ Architecture

### Brain Pipeline

```
┌─────────────────────────────────────────────────────────┐
│                        UI Layer                          │
│              dashboard / skills / memory / etc.          │
├─────────────────────────────────────────────────────────┤
│                        API Layer                         │
│              FastAPI  http://127.0.0.1:8000              │
├─────────────────────────────────────────────────────────┤
│                      Brain Layer                         │
│   BrainEngine                                            │
│     ├── Interpreter  (text → Intent)                     │
│     ├── Planner      (Intent → List[Intent])             │
│     ├── Resolver     (fuzzy entity matching)             │
│     └── Executor     (dispatch to handlers/skills)       │
├─────────────────────────────────────────────────────────┤
│                     Hands Layer                          │
│   DesktopHand (hands/desktop/) — physical execution      │
│     launch/close apps · URLs · keyboard · mouse ·        │
│     clipboard · scoped filesystem · processes · windows  │
├─────────────────────────────────────────────────────────┤
│                      Skills Layer                        │
│   BaseSkill                                              │
│     ├── GitHubProjectSkill  (project tracking)           │
│     ├── AutomationSkill     (code generation)            │
│     └── Browser/App handlers (built-in)                  │
├─────────────────────────────────────────────────────────┤
│                   Data / Knowledge Layer                  │
│   KnowledgeManager  ←  KnowledgeLoader  ←  JSON files   │
│   DatabaseManager   ←  SQLite                           │
│   SpeechService     ←  Whisper model                    │
└─────────────────────────────────────────────────────────┘
```

### Package Structure

```
sarthi/
├── brain/          # Core intelligence pipeline
│   ├── engine.py       # BrainEngine orchestrator
│   ├── interpreter.py  # Text → Intent(s) parser (compound commands)
│   ├── planner.py      # Documented pass-through (interpreter owns splitting)
│   ├── executor.py     # Handler dispatcher (built-ins + skill pool, NLP last)
│   ├── intent.py       # Intent data model (pipeline contract)
│   ├── modes.py        # default / conversation mode + test mode
│   ├── context.py      # Pipeline runtime context
│   └── response.py     # Standardized response model
│
├── hands/          # Physical execution layer (hands do, brains think)
│   └── desktop/        # DesktopHand: capability-gated Windows actions
│       ├── hand.py         # execute(action, **kwargs) → DesktopResult
│       ├── capabilities.py # The action allow-list (per-capability specs)
│       ├── models.py       # DesktopRequest / DesktopResult contracts
│       ├── processes.py    # Launch/terminate/list (never via shell)
│       ├── windows.py      # Window enumeration (optional pywin32)
│       ├── input.py        # Keyboard/mouse/clipboard (optional pyautogui)
│       ├── filesystem.py   # Scoped file ops (allowed roots, 1 MB cap)
│       └── browser.py      # open_url (http/https only)
│
├── knowledge/      # Entity knowledge base
│   ├── manager.py      # KnowledgeManager (singleton, ONLY public interface)
│   ├── loader.py       # Pure JSON I/O
│   ├── entity_resolver.py  # Fuzzy entity matcher (dependency injection)
│   ├── memory.py       # /remember facts + command history (SQLite)
│   ├── cache.py        # TTL cache
│   ├── applications.json  # Discovered apps (v2 categories; gitignored)
│   └── websites.json      # Curated websites
│
├── database/       # Persistent storage
│   ├── manager.py      # DatabaseManager (SQLite, single connection)
│   └── models.py       # Table schemas
│
├── skills/         # Pluggable capabilities (one folder + manifest.json each)
│   ├── base.py         # BaseSkill ABC
│   ├── registry.py     # Skill discovery (single mechanism)
│   ├── app_launcher/   # Launch installed applications
│   ├── browser/        # Open/search known websites + /browser/* routes
│   ├── browser_awareness/ # Inspect arbitrary websites (Playwright, validated)
│   ├── scanner/        # Application discovery engine
│   ├── project_tracker/# GitHub integration
│   ├── automation_engine/# AI-chain laptop automation (ai_chain/ v1.5)
│   ├── natural_language_processor/ # Conversational fallback (Hermes, last)
│   └── ...             # speech, user_config, personal_context
│
├── hermes/         # Conversational layer + tool bridge
│   ├── orchestrator.py  # HermesOrchestrator (chat + bounded tool loop)
│   ├── service.py       # Shared wiring (singletons)
│   ├── tool_registry.py # Tools Hermes may request (allow-list)
│   ├── providers/       # Provider adapters + registry (config-driven)
│   ├── config/          # HermesConfig loader (.env)
│   ├── models.py        # Task + provider-neutral ModelRequest
│   └── routes.py        # /hermes/* FastAPI routes
│
├── connectors/     # External service integrations
│   ├── base.py         # BaseConnector ABC
│   ├── registry.py     # Connector discovery
│   └── google_calendar/# OAuth2 Google Calendar connector
│
├── speech/         # Audio processing (push-to-talk, no wake word)
│   ├── recorder.py     # Microphone recording
│   └── speech_to_text.py # Whisper transcription (lazy model)
│
├── utils/          # Shared utilities
│   ├── logger.py       # Centralized logging setup
│   ├── voice.py        # Spoken announcements (automation contract)
│   └── telemetry.py    # Hardware telemetry
│
├── UI/             # Web interface (served by the API at /ui)
│   ├── components/     # Shared sidebar + footer
│   ├── components.js   # Component loader (declares the API origin)
│   ├── dashboard.html  # Main HUD
│   ├── chat.html       # Chat / memory / sandbox viewer / test runner
│   ├── skills.html     # Skill repository
│   ├── memory.html     # Knowledge + memory + history
│   ├── knowledge.html  # Connectors
│   ├── history.html    # Command timeline (live /command-history)
│   └── settings.html   # Settings (live metrics + connectors; cosmetic toggles)
│
├── api.py          # FastAPI server (API + static UI, one process)
├── main.py         # CLI entry point (voice)
├── main-test.py    # Smoke test
├── desktop_agent.py  # Standalone Desktop hand entry point (Sarthi.exe seam)
├── start.bat       # Dev / windowless launcher for the API
├── config.py       # Central configuration (paths, ports, Whisper)
└── tests/          # Pytest suite (713 tests)
```

### Knowledge System

```
┌──────────────────────────────────────────────────────────────┐
│                    PRESENTATION LAYER                         │
│  Skills (Apps, Browser, Future...)                           │
│  EntityResolver (Entity Resolution)                          │
└────────────────────┬─────────────────────────────────────────┘
                     │ Uses only this interface
                     ↓
┌──────────────────────────────────────────────────────────────┐
│                  BUSINESS LOGIC LAYER                         │
│              KnowledgeManager (Singleton)                     │
│                                                               │
│  Methods:                                                     │
│  - load_applications()  [Lazy + cached]                       │
│  - load_websites()      [Lazy + cached]                       │
│  - find_entity(query)   [Fuzzy search]                        │
│  - find_application()   [App search]                          │
│  - find_website()       [Website search]                      │
│  - get_all_entities()   [For EntityResolver]                  │
│  - refresh_applications() [Rescan system]                     │
└────────────────────┬────────────────────────────┬────────────┘
                     │                            │
         Coordinates │                            │
                     ↓                            ↓
┌───────────────────────────────┐   ┌──────────────────────────┐
│    DATA ACCESS LAYER          │   │   DISCOVERY LAYER        │
│  KnowledgeLoader              │   │  Scanner                 │
│                               │   │                          │
│  Methods:                     │   │  - scan_program_files()  │
│  - load()    [Read JSON]      │   │  - scan_start_menu()     │
│  - save()    [Write JSON]     │   │  - scan_path()           │
│  - is_valid()                 │   │  - scan_all() [List]     │
└───────────┬───────────────────┘   └──────────────┬───────────┘
            │                                      │
            ↓                                      │
   ┌────────────────┐                              │
   │ JSON Files     │◄─────────────────────────────┘
   │                │
   │ applications.  │
   │ json (700+ apps)
   │                │
   │ websites.json  │
   │ (5 sites)      │
   │                │
   │ devices.json   │
   │ (future)       │
   └────────────────┘
```

### Skill System

Skills are auto-loaded on startup and registered with the executor.

```python
# skills/base.py — All skills inherit from BaseSkill
class BaseSkill(ABC):
    name: str
    description: str
    version: str

    @abstractmethod
    def execute(self, intent: Intent) -> dict: ...
```

**Current Skills:**

| Skill | Version | Description |
|---|---|---|
| `project_tracker` | 1.1.0 | GitHub & Notion project tracking |
| `automation_engine` | 1.1.0 | AI-chain laptop automation + code generation |
| `app_launcher` | 1.2.0 | Launch installed applications (delegates to the Desktop hand) |
| `browser` | 1.1.0 | Open/search known websites (deterministic) |
| `scanner` | 1.1.0 | Application discovery engine |
| `natural_language_processor` | 1.1.0 | Conversational fallback (Hermes chat) |
| `speech` | 1.1.0 | Push-to-talk voice input (mic + Whisper) |
| `user_config` | 1.1.0 | User settings (github username, etc.) |
| `personal_context` | 1.0.0 | Personal context (never changed since creation) |
| `browser_awareness` | 1.0.0 | Inspect arbitrary websites (new in this release) |

> **Version rule:** a skill's version is bumped (`1.0.0 → 1.1.0 → 1.2.0 …`)
> whenever its code changes after the day it was created — bump **both**
> `manifest.json` and the `BaseSkill.version` attribute in its `main.py`.
> Any skill still at its creation version (`1.0.0`) has never been
> modified, so a glance at the version column shows what has updates.

### Clean Architecture Refactoring

The codebase was refactored from a tightly-coupled architecture to clean architecture.

**Before (Tightly Coupled):**
```
EntityResolver  ──┐
BrowserSkill    ──┼──> knowledge.loader ──> applications.json
AppExecutor     ──┘
     (All importing loader directly)
```

**After (Clean Architecture):**
```
Skills → KnowledgeManager (business logic) → KnowledgeLoader (JSON I/O)
EntityResolver depends on List[Dict] (dependency injection)
Scanner returns list (no direct file writes)
```

**Key Principles Applied:**
- **Single Responsibility**: Loader = JSON I/O only, Manager = business logic, Scanner = discovery only
- **Dependency Injection**: Entities passed to resolver, not imported
- **Open/Closed**: Adding new entity types requires no code changes
- **Singleton Pattern**: `get_manager()` returns single instance

**Coupling Score: OPTIMAL** ✅

---

## 🗄️ Knowledge Base System (Deep Dive)

### 1. Application Scanner

**File:** `skills/scanner/application_scanner.py`

Ships as the **scanner** skill, exposed via `ScannerSkill` (`skills/scanner/main.py`).
`KnowledgeManager.refresh_applications()` delegates here.

Automatically discovers installed applications from standard Windows locations.

#### Scan Locations

- `C:\Program Files`
- `C:\Program Files (x86)`
- `%LOCALAPPDATA%\Programs`
- Windows Start Menu (current user)
- Windows Start Menu (all users)
- Every directory in `PATH` environment variable

#### File Types Discovered

- `.exe` executables
- `.lnk` shortcuts (resolved via COM API)

#### Alias Generation

Aliases are automatically generated using metadata + pattern matching:

```
Code.exe  →  ["code", "vscode", "vs code", "visual studio code"]
```

#### Duplicate Handling

When the same application is found in multiple locations, a 5-tier priority system keeps the best entry:
1. Program Files
2. Program Files (x86)
3. LocalAppData
4. Start Menu
5. PATH

#### Usage

```python
from skills.scanner.application_scanner import scan_all

# Run full scan — returns list of dicts
applications = scan_all()

# Save via manager
manager.save_applications(applications)
```

### 2. Knowledge Loader

**File:** `knowledge/loader.py`

**Responsibility:** Pure JSON I/O only.

```python
from knowledge.loader import KnowledgeLoader

loader = KnowledgeLoader()
data = loader.load()           # Read JSON from disk
loader.save(data)              # Write JSON to disk
loader.is_valid()              # Validate structure
```

**What it does NOT do:** Searching, business logic, merging, caching, alias generation.

### 3. Knowledge Manager

**File:** `knowledge/manager.py`

**Responsibility:** Centralized knowledge system — the single source of truth for all entity access.

```python
from knowledge.manager import get_manager

manager = get_manager()

# Load entity types
apps = manager.load_applications()   # 700+ apps
sites = manager.load_websites()      # 5+ sites

# Search
app = manager.find_application("vscode")
site = manager.find_website("google")
entity = manager.find_entity("vscode")

# Get all for EntityResolver
entities = manager.get_all_entities()  # List[Dict]

# Refresh
manager.refresh_applications()
```

### 4. Entity Resolver

**File:** `knowledge/entity_resolver.py`

Uses dependency injection — entities are passed in, not imported.

```python
from knowledge.entity_resolver import EntityResolver
from knowledge.manager import get_manager

# Injection
entities = manager.get_all_entities()
resolver = EntityResolver(entities=entities)

# Resolve
result = resolver.resolve("open visual studio code")
# → "open Code"

# Empty resolver (no entities to match)
resolver = EntityResolver()
```

### 5. Application Executor

**File:** `skills/app_launcher/main.py` (AppLauncherSkill)

Launches applications resolved via KnowledgeManager.

```python
from skills.app_launcher import AppLauncherSkill

skill = AppLauncherSkill()
skill.execute(intent)   # Or: BrainEngine().process("open vscode")
```

### 6. Future Entity Types

Adding new entity types requires **no code changes** — just add a JSON file:

```json
knowledge/devices.json
{
  "version": 1,
  "last_scan": "2026-07-10T00:00:00",
  "devices": [
    {
      "name": "Printer",
      "aliases": ["printer"],
      "ip": "192.168.1.100"
    }
  ]
}
```

The Entity Resolver consumes all types automatically.

---

## 📡 API Reference

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/` | Redirects to `/ui/dashboard.html` |
| `GET` | `/health` | Health check |
| `POST` | `/command` | Process text: `{"text": "open chrome"}` |
| `POST` | `/listen` | Process voice (records + transcribes via Whisper) |
| `GET`/`POST` | `/mode` | Get/switch chat mode (default \| conversation) |
| `GET`/`POST` | `/test-mode` | Dry-run mode for skills |
| `GET` | `/knowledge` | Knowledge base statistics |
| `GET` | `/applications` | List all discovered applications |
| `GET`/`POST` | `/applications/*` | Categories, favourites, categorize, run |
| `POST` | `/websites/search-and-save` | Browser-search fallback + remember site |
| `GET` | `/memory`, `/command-history`, `/chat` | Memory, history, transcripts |
| `POST`/`GET` | `/settings` | User settings (key/value) |
| `GET` | `/skills`, `/skills/{id}` | List/inspect skills (+ enable/disable) |
| `POST` | `/hermes/chat` | Hermes chat (tool bridge enabled) |
| `GET` | `/hermes/tools`, `/hermes/sandbox`, `/hermes/status` | Tool list, query index, provider diagnostics |
| `*` | `/browser/*` | Browser extension bridge |
| `*` | `/connectors/*` | Connector CRUD + Google Calendar OAuth2 |
| `GET` | `/system/metrics`, `/events/history` | Hardware telemetry, event log |
| `GET`/`POST` | `/test/prompts`, `/test/run` | Prompt-suite test runner |

The full request/response shapes are documented in **docs/ARCHITECTURE.md → API/UI**.

### Example Response

```json
{
  "action": "open",
  "target": "Chrome",
  "confidence": 1.0,
  "status": "executed",
  "success": true,
  "execution_ms": 15.3
}
```

---

## 🎨 Web UI

The web UI is served directly from the FastAPI server at `http://127.0.0.1:8000`. It features 6 pages:

| Page | Route | Description |
|---|---|---|
| **Home** | `dashboard.html` | Main HUD with status, stats, command input |
| **Chat** | `chat.html` | Conversation, memory, sandbox viewer, test runner |
| **Skills** | `skills.html` | Skill repository and management |
| **Memory** | `memory.html` | Neural context engine |
| **Knowledge** | `knowledge.html` | Knowledge database + connectors |
| **History** | `history.html` | Command timeline |
| **Settings** | `settings.html` | System configuration |

Built with:
- **Tailwind CSS** — Utility-first styling
- **Material Symbols** — Icon set
- **CSS custom properties** — For theming and glassmorphism effects
- **Backdrop filters** — Glass/neomorphic HUD design

---

## 🧪 Testing

```bash
# Run all tests
python -m pytest tests/ -v

# Run specific test file
python -m pytest tests/test_interpreter.py -v

# Run with coverage
python -m pytest tests/ --cov=.
```

**713 tests** across 41 test files. Key coverage:

| Test File | Coverage |
|---|---|
| `test_brain_engine.py` | Brain pipeline orchestration |
| `test_interpreter.py` | Text → Intent parsing |
| `test_executor.py` | Handler dispatch + skills |
| `test_resolver_matching.py` | Fuzzy matching quality (nonsense rejection) |
| `test_knowledge_manager.py` | Loading, caching, categorization, entities |
| `test_scanner.py` | Scanner data model + merge priority |
| `test_pipeline_compatibility.py` | Scanner → Knowledge → Resolver, Brain → Hermes |
| `test_hermes_api.py` | `/hermes/chat` endpoint |
| `test_tool_bridge.py` | Hermes → Tool Registry loop |
| `test_browser_awareness.py` | Browser Awareness safety gate + manager loop |
| `test_browser.py` | Browser skill routes |
| `test_connectors.py` | Connector registry + models |
| `test_desktop_hand.py` | Desktop hand: capabilities, validation, delegation |

### Verification

```
python -m pytest tests/ -q
# 713 passed
```

---

## 🔧 Development

### Code Quality

```bash
# Format all Python files
ruff format .

# Lint and auto-fix
ruff check --fix .

# Type check (advisory)
mypy .
```

### Verification Checklist

- [x] All hardcoded application definitions removed
- [x] 700+ applications automatically discovered
- [x] Intelligent alias generation
- [x] Smart deduplication with 5-tier priority
- [x] Zero hardcoded values (except metadata)
- [x] Entity Resolver uses dependency injection
- [x] No circular dependencies
- [x] Centralized KnowledgeManager (singleton)
- [x] Clean separation: Loader / Manager / Scanner
- [x] All tests passing
- [x] Type hints (mypy advisory/progressive — not 100%)
- [x] Backward compatible — no breaking changes

### Performance Benchmarks

| Operation | Time |
|---|---|
| Initial scan | 10-15 seconds (one-time) |
| Cached lookup | < 1ms |
| Entity resolution | < 10ms |
| Memory usage | ~5MB (700+ apps cached) |

---

## 📦 Deliverables & Verification

### Code Artifacts

| Module | Status |
|---|---|
| `skills/scanner/application_scanner.py` | ✅ Production-ready |
| `knowledge/loader.py` | ✅ Production-ready |
| `knowledge/manager.py` | ✅ Production-ready |
| `knowledge/entity_resolver.py` | ✅ Refactored (DI) |
| `knowledge/applications.json` | ✅ Generated (700+ apps) |
| `knowledge/websites.json` | ✅ Curated (5 sites) |
| `skills/app_launcher/main.py` | ✅ Refactored |
| `skills/browser/main.py` | ✅ Refactored |
| `skills/browser_awareness/` | ✅ New (Playwright inspection) |
| `hermes/` | ✅ Conversational layer + tool bridge |
| `connectors/` | ✅ External service integrations |

### Quality Metrics

| Metric | Score |
|---|---|
| Type coverage | Advisory (mypy progressive mode) |
| Error handling | Comprehensive |
| Test suite | 713 passing tests |
| Performance | Optimized |
| Maintainability | High |

### Architecture Phases

| # | Phase | Status |
|---|---|---|
| 1 | Pipeline fix + scanner merge | ✅ Complete |
| 2 | Brain restructure (Engine, Planner, Resolver) | ✅ Complete |
| 3 | Skill cleanup + naming standardization | ✅ Complete |
| 4 | Database package (SQLite, models, cache) | ✅ Complete |
| 5 | Centralized logging setup | ✅ Complete |
| 6 | UI consolidation (shared components) | ✅ Complete |
| 7 | Unit tests (713 tests) | ✅ Complete |
| 8 | Automation engine cleanup | ✅ Complete |
| 9 | Linting, formatting | ✅ Complete |
| 10 | Clean architecture refactoring (Knowledge System) | ✅ Complete |
| 11 | Hermes provider abstraction (local / OpenRouter / OpenAI-compatible) | ✅ Complete |
| 12 | Wake-word removal; single-port serving (API + UI on :8000) | ✅ Complete |
| **13** | **Canonical docs (ARCHITECTURE.md, PROJECT_STATE.md)** | **⬅️ This pass** |
| 14+ | Hermes skill authoring, vision, more connectors | 🔮 Future |

---

## 🔮 Roadmap

**Implemented:**
- **Memory** — Persistent conversation history, /remember facts, settings (SQLite)
- **CI/CD** — GitHub Actions (`.github/workflows/ci.yml`): lint, format, tests, smoke test
- **Connectors** — Google Calendar (OAuth2); Gmail/email/IoT planned via `connectors/`
- **Hermes integration** — Conversational fallback, tool bridge, sandbox execution records
- **Browser Awareness** — Playwright-based inspection of arbitrary websites

**Planned (future):**
- **Vision package** — Screen capture and OCR
- **Multi-agent** — Collaborative AI agents for complex tasks
- **Plugin marketplace** — External skill discovery and loading
- **More entity types** — Devices, contacts, plugins (no code changes needed)
- **Hermes skill authoring** — validated creation/registration of new skills by Hermes (see `docs/CONTRIBUTING.md` boundary; **planned, not implemented**)
- **Gmail / IoT connectors** — registry scaffolding exists in `connectors/`

---

## 🧑‍💻 Contributing

See [docs/CONTRIBUTING.md](docs/CONTRIBUTING.md) — it covers project structure, module
ownership, the Hermes contribution boundary, and how to add a skill or a
connector without touching core.

Quick start:
1. Create a feature branch: `git checkout -b feat/my-feature`
2. Make changes and ensure tests pass: `python -m pytest tests/ -v`
3. Format and lint: `ruff format . && ruff check --fix .`
4. Commit: `git commit -m "feat: add my feature"`
5. Push and open a pull request

---

## 📄 License

MIT — intended licensing; a LICENSE file is not yet present in the repository.

---

## 🙏 Acknowledgements

- [Whisper](https://github.com/openai/whisper) by OpenAI — speech recognition
- [FastAPI](https://fastapi.tiangolo.com/) — web framework
- [RapidFuzz](https://github.com/maxbachmann/RapidFuzz) — fuzzy string matching
- [Tailwind CSS](https://tailwindcss.com/) — UI styling
- [Material Symbols](https://fonts.google.com/icons) — icon set
- [pywin32](https://github.com/mhammond/pywin32) — Windows COM API integration
