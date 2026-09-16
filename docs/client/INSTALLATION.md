# Installation

## Requirements

| Requirement | Notes |
| --- | --- |
| **Windows 10/11** | Sarthi's desktop-control features (launching apps, TTS voice replies, AI-chain automation) are Windows-specific. Parts of the backend run elsewhere, but Windows is the supported platform. |
| **Python 3.10+** | Check with `python --version`. |
| **~2 GB disk** | Core install is small; voice input adds a Whisper model (~500 MB), AI chaining adds a Chrome profile. |
| **Microphone** (optional) | Only for voice input. |
| **Ollama** (recommended) | The default AI provider is local Ollama — no API keys or cloud accounts needed. |
| **Google Chrome** (optional) | Needed for automated browsing (browser awareness) and AI chaining. |

## Installation

1. **Get the code** (clone or download the repository) and open a terminal in
   the repository root.
2. **Create a virtual environment**:
   ```bash
   python -m venv .venv
   .venv\Scripts\activate
   ```
3. **Install Sarthi**:
   ```bash
   pip install -e .
   ```
   Optional extras:
   ```bash
   pip install -e ".[automation]"   # AI chaining / laptop control
   pip install -e ".[browser]"      # automated browsing (Selenium/Playwright)
   pip install sounddevice faster-whisper   # voice input
   ```
   The core app installs and starts fine without any of the extras — features
   degrade gracefully until you add them.
4. **Configure (optional)**: copy `.env.example` to `.env`. Defaults are
   sensible: `HERMES_PROVIDER=local` (Ollama at `localhost:11434`,
   model `hermes3:8b`). If you use Ollama, make sure it is running and pull
   the model once: `ollama pull hermes3:8b`. To use a cloud provider instead,
   set `HERMES_PROVIDER=openrouter` (or `openai_compatible`) and add your API
   key — Ollama then remains the automatic fallback.

## Starting Sarthi

- **Easiest**: double-click `start.bat` in the repository root. It starts the
  backend (a visible server window) and opens the dashboard at
  <http://127.0.0.1:8000>.
- **From the terminal**:
  ```bash
  Backend\sarthi.bat             # visible server window
  Backend\sarthi.bat background  # windowless (pythonw)
  python Backend/api.py          # direct start
  ```
- **Desktop client**: `python Desktop/run.py` (development) or
  `Desktop/dist/sarthi.exe` if present (packaged build).
- **Verify**: open <http://127.0.0.1:8000/health> — you should see
  `{"assistant": "Sarthi", "status": "Running"}`.

First start creates the database (`Backend/database/sarthi.db`) and the task
sandbox automatically. On the dashboard, run **"scan apps"** once so Sarthi
learns your installed applications.

## Required external software/services

| Software | When you need it |
| --- | --- |
| **Ollama** | Default AI provider. Install from ollama.com, keep it running, pull `hermes3:8b` (or point `LOCAL_HERMES_MODEL` at a model you have). Without it, complex requests fail gracefully while deterministic commands still work. |
| **Cloud AI key** (alternative) | Only if you set `HERMES_PROVIDER=openrouter` or `openai_compatible` in `.env`. |
| **Chrome** | Automated browsing (browser awareness) and AI chaining drive real Chrome. Selenium fetches its own driver automatically. |
| **Whisper model files** | Downloaded automatically on first voice use (model `small` by default). |

## Known setup limitations

- **Windows-centric**: voice replies (TTS) and laptop-control automation do
  not work on other operating systems; elsewhere they degrade to log lines.
- **Voice dependencies are not auto-installed**: `sounddevice` and
  `faster-whisper` must be installed manually (step 3) for voice input.
- **First voice use is slow**: the Whisper model loads on demand.
- **AI chaining needs one-time setup per site**: log in once inside the
  automation Chrome profile and run the calibration tool
  (`python -m skills.automation_engine.ai_chain.calibrate`).
- **LAN binding**: the server binds `0.0.0.0:8000` without authentication —
  fine for a home network, but do not port-forward it to the internet.
- **`sarthi.bat` and `config.py` both define the API port** (8000): if you
  change the port, update both (`Backend/config.py` and the `set` lines in
  `Backend/sarthi.bat`).
- **Advanced — Desktop Agent mode**: by default Sarthi executes actions on
  the machine it runs on (`SARTHI_DESKTOP_AGENT_MODE=local`). A `remote`
  mode exists where the brain sends actions to a separate Desktop Agent
  process (`python Backend/desktop_agent.py --server`, port 8765); it is a
  LAN/local development feature without authentication. Leave it as `local`
  unless you specifically need it.
