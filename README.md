# 🧠 Sarthi — Local-First AI Desktop Assistant

**Sarthi** is a local-first, privacy-respecting AI Desktop Assistant that runs entirely on your machine. It understands natural language commands, recognizes speech, discovers installed applications, and executes tasks through a modular skill system.

> **Version:** 1.0.4 Hyperion
> **Status:** Production-ready
> **Python:** 3.10+

---

## ✨ Features

| Capability | Description |
|---|---|
| 🎤 **Speech Recognition** | Wake-word detection and Whisper-based transcription |
| 🧠 **Brain Pipeline** | Interpret → Plan → Resolve → Execute |
| 📱 **Entity Resolution** | Fuzzy matching for 1,000+ discovered applications |
| 🛠️ **Skill System** | Pluggable skills: GitHub tracker, automation engine, browser |
| 🗄️ **Knowledge Base** | Auto-discovers apps and stores entity data |
| 🌐 **FastAPI Server** | REST API with CORS for the web UI |
| 🎨 **Web UI** | 6-page dashboard with sidebar, dock, and HUD-style interface |
| 🏠 **Privacy-First** | 100% local — no cloud dependencies |

---

## 🏛️ Architecture

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
│     └── Executor     (dispatch to handlers)              │
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
│   ├── interpreter.py  # Text → Intent parser
│   ├── planner.py      # Multi-step plan decomposer
│   ├── resolver.py     # Fuzzy entity matcher
│   ├── executor.py     # Handler dispatcher
│   ├── intent.py       # Intent data model
│   ├── context.py      # Pipeline runtime context
│   └── response.py     # Standardized response model
│
├── knowledge/      # Entity knowledge base
│   ├── manager.py      # KnowledgeManager (singleton)
│   ├── loader.py       # Pure JSON I/O
│   ├── scanners/       # Application discovery
│   └── *.json          # Entity data files
│
├── database/       # Persistent storage
│   ├── manager.py      # DatabaseManager (SQLite)
│   ├── models.py       # Table schemas
│   └── cache.py        # In-memory query cache
│
├── skills/         # Pluggable capabilities
│   ├── base.py         # BaseSkill ABC
│   ├── manager.py      # Skill loader
│   ├── project_tracker/# GitHub integration
│   └── automation_engine/# Code automation
│
├── speech/         # Audio processing
│   ├── recorder.py     # Microphone recording
│   ├── speech_to_text.py # Whisper transcription
│   └── wake_word.py    # Wake word detection
│
├── actions/        # Built-in action handlers
│   ├── apps.py         # Application launcher
│   ├── browser.py      # Website opener
│   └── executor.py     # Legacy dispatcher
│
├── utils/          # Shared utilities
│   ├── logger.py       # Centralized logging setup
│   └── helpers.py      # Misc helpers
│
├── UI/             # Web interface
│   ├── components/     # Shared sidebar + footer
│   ├── components.js   # Component loader
│   ├── dashboard.html  # Main HUD
│   ├── skills.html     # Skill repository
│   ├── memory.html     # Neural context engine
│   ├── knowledge.html  # Knowledge database
│   ├── history.html    # Command timeline
│   └── settings.html   # System settings
│
├── api.py          # FastAPI server
├── main.py         # CLI entry point
├── config.py       # Central configuration
└── tests/          # 109+ pytest unit tests
```

---

## 🚀 Getting Started

### Prerequisites

- **Python 3.10+**
- **Windows** (for speech/UI features; core logic is cross-platform)
- **Microphone** (for voice commands)

### Installation

```bash
# 1. Clone the repo
git clone https://github.com/your-username/sarthi.git
cd sarthi

# 2. Create virtual environment
python -m venv .venv
.venv\Scripts\activate    # Windows
source .venv/bin/activate # macOS/Linux

# 3. Install dependencies
pip install fastapi uvicorn

# 4. Install dev dependencies (optional)
pip install ruff mypy pre-commit
pre-commit install

# 5. Run tests (optional)
python -m pytest tests/ -v
```

### Run the API Server

```bash
python api.py
# → http://127.0.0.1:8000
```

### Run the CLI

```bash
python main.py
# → Press ENTER to speak...
```

### Open the Web UI

Open `UI/dashboard.html` in your browser while the API is running.

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

**Test count:** 109+ tests across 9 test files covering:
- Brain engine pipeline
- Entity resolution (fuzzy matching)
- Database CRUD operations
- Skill ABC enforcement
- Query cache TTL
- Knowledge manager loading/caching
- Interpreter parsing
- Executor dispatch
- Planner pass-through

---

## 🔧 Development

### Code Quality

```bash
# Format all Python files
ruff format .

# Lint and auto-fix
ruff check --fix .

# Type check (advisory)
pre-commit run --hook-stage manual mypy
```

### Pre-commit Hooks

Hooks run automatically on `git commit`:

| Hook | Action |
|---|---|
| `ruff-format` | Blocks unformatted code |
| `ruff-lint` | Auto-fixes lint issues |
| `trailing-whitespace` | Trims whitespace |
| `end-of-file-fixer` | Ensures newline at EOF |
| `check-yaml`/`check-toml` | Validates config files |
| `mypy` | Manual-only type checking |

---

## 📡 API Reference

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/` | Health check |
| `POST` | `/command` | Process text: `{"text": "open chrome"}` |
| `POST` | `/listen` | Process voice (records + transcribes) |
| `GET` | `/knowledge` | Knowledge base statistics |
| `GET` | `/applications` | List all discovered applications |
| `GET` | `/skills` | List installed skills |

### Example

```bash
curl -X POST http://127.0.0.1:8000/command \
  -H "Content-Type: application/json" \
  -d '{"text": "open chrome"}'

# Response:
# {
#   "action": "open",
#   "target": "Chrome",
#   "confidence": 1.0,
#   "status": "executed",
#   "success": true,
#   "execution_ms": 15.3
# }
```

---

## 🗺️ Architecture Phases

| # | Phase | Status |
|---|---|---|
| 1 | Pipeline fix + scanner merge | ✅ Complete |
| 2 | Brain restructure (Engine, Planner, Resolver) | ✅ Complete |
| 3 | Skill cleanup + naming standardization | ✅ Complete |
| 4 | Database package (SQLite, models, cache) | ✅ Complete |
| 5 | Centralized logging setup | ✅ Complete |
| 6 | UI consolidation (shared components) | ✅ Complete |
| 7 | Unit tests (109+ tests) | ✅ Complete |
| 8 | Automation engine cleanup | ✅ Complete |
| 9 | Linting, formatting, pre-commit hooks | ✅ Complete |
| **10** | **Documentation** | **⬅️ You are here** |
| 11+ | Memory, vision, multi-agent, CI/CD | 🔮 Future |

---

## 🔮 Roadmap

- **Memory package** — Persistent conversation history and user preferences
- **Vision package** — Screen capture and OCR
- **Multi-agent** — Collaborative AI agents for complex tasks
- **Plugin marketplace** — External skill discovery and loading
- **CI/CD** — GitHub Actions for automated testing and distribution

---

## 🧑‍💻 Contributing

1. Install pre-commit hooks: `pre-commit install`
2. Create a feature branch: `git checkout -b feat/my-feature`
3. Make changes and ensure tests pass: `python -m pytest tests/ -v`
4. Format and lint: `ruff format . && ruff check --fix .`
5. Commit (hooks will auto-check): `git commit -m "feat: add my feature"`
6. Push and open a pull request

---

## 📄 License

MIT — see [LICENSE](LICENSE) for details.

---

## 🙏 Acknowledgements

- [Whisper](https://github.com/openai/whisper) by OpenAI — speech recognition
- [FastAPI](https://fastapi.tiangolo.com/) — web framework
- [RapidFuzz](https://github.com/maxbachmann/RapidFuzz) — fuzzy string matching
- [Tailwind CSS](https://tailwindcss.com/) — UI styling
- [Material Symbols](https://fonts.google.com/icons) — icon set
