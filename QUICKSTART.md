# 🚀 Sarthi Quickstart

Get Sarthi running in 5 minutes.

---

## 📦 Install

```bash
git clone https://github.com/your-username/sarthi.git
cd sarthi
python -m venv .venv
.venv\Scripts\activate       # Windows
source .venv/bin/activate     # macOS/Linux
pip install fastapi uvicorn
```

## ▶️ Run

### API Server (recommended)

```bash
python api.py
```

Open `http://127.0.0.1:8000` — you should see `{"assistant": "Sarthi", "status": "Running"}`.

### Web UI

While the API is running, open **`UI/dashboard.html`** in your browser.

### CLI (voice)

```bash
python main.py
# Press ENTER to speak a command
```

---

## 🧪 Test

```bash
python -m pytest tests/ -v
```

Expect **109 tests passing**.

---

## 🧠 Try It

```bash
# Process a text command via the API
curl -X POST http://127.0.0.1:8000/command \
  -H "Content-Type: application/json" \
  -d '{"text": "open chrome"}'

# See what apps are discovered
curl http://127.0.0.1:8000/applications

# List installed skills
curl http://127.0.0.1:8000/skills
```

---

## 📁 Key Files

| File | Purpose |
|---|---|
| `main.py` | CLI voice loop |
| `api.py` | FastAPI REST server |
| `config.py` | Central settings |
| `brain/engine.py` | Brain pipeline orchestrator |
| `utils/logger.py` | Logging config |

---

## 🔧 Dev Setup

```bash
# Install dev tools
pip install ruff mypy pre-commit

# Install git hooks
pre-commit install

# Format & lint
ruff format .
ruff check --fix .

# Run type checker (manual)
pre-commit run --hook-stage manual mypy
```

---

## 📚 Documentation

| File | Description |
|---|---|
| `README.md` | Full architecture, setup, development guide |
| `QUICKSTART.md` | This file — get running in 5 minutes |
| `KNOWLEDGE_BASE.md` | Knowledge system deep-dive |
| `DELIVERABLES.md` | Implementation deliverables checklist |
| `IMPLEMENTATION_SUMMARY.md` | Detailed implementation notes |

---

## 🔮 What's Next?

- [ ] **Memory** — persistent user preferences
- [ ] **Vision** — screen OCR and image recognition
- [ ] **Multi-agent** — collaborative AI agents
- [ ] **Plugin marketplace** — shareable skills

---

_Need help? Open an issue or check the full README.md._
