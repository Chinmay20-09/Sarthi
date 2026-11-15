# Sarthi Desktop client

A thin Windows client for the Sarthi Backend. The client contains **no
assistant intelligence** — it sends a query and conversation session to
`POST /desktop/query` and displays the backend's response and action status.

```text
Desktop client --HTTP /desktop/query--> Backend / configured model
       ▲                                     │
       └── validated pet/browser action ─────┤
                                             └── validated Hand action → Windows
```text

The backend owns provider selection, conversation history, action selection,
and response wording. Window reads, typing, and key actions go through the
validated Desktop Hand. Two actions belong to the desktop client itself:
changing Hitori's pet image and opening an HTTP(S) URL in the user's default
browser. The backend returns those as a narrow `client_action`; the GUI
validates the action type and arguments before applying it locally. This keeps
YouTube/browser launches on the desktop where the user is interacting.

## Layout

| Path | Purpose |
| --- | --- |
| `client/sarthi_client/` | client source (tkinter GUI, controller, backend HTTP boundary, config) |
| `client/sarthi_client/gui.py` | the SARTHI window (model profile selector, query textbox, response) |
| `client/sarthi_client/controller.py` | query/profile coordination (no tk, no http) |
| `client/sarthi_client/backend.py` | the ONLY module that talks HTTP — query and profile settings |
| `client/sarthi_client/config.py` | single mechanism for the Backend URL (see below) |
| `run.py` | run from source: `python Desktop/run.py` |
| `sarthi_client.spec` | PyInstaller spec → builds `Desktop/sarthi.exe` |
| `sarthi.exe` | built executable (build artifact, gitignored) |

## Backend URL configuration

Resolved in `client/sarthi_client/config.py` — the single mechanism.
Priority order:

1. `SARTHI_BACKEND_URL` environment variable
2. `backend_url` key in `sarthi_client.json` (next to `sarthi.exe`, or
   next to the package in a source checkout)
3. default `http://127.0.0.1:8000` (the locally running backend)

Examples:

```json
// sarthi_client.json — point the client at a LAN backend
{ "backend_url": "http://192.168.1.20:8000" }
```text

```powershell
$env:SARTHI_BACKEND_URL = "https://sarthi.example.com"   # cloud backend
```text

The default stays on loopback; the Backend is not exposed publicly by
default.

## Run from source

```bash
# terminal 1 — start the backend
Backend\sarthi.bat

# terminal 2 — start the client
python Desktop/run.py
```text

For a shortcut-friendly GUI launch, create a Windows shortcut to
`Desktop\Start Sarthi Desktop.bat`. It starts the GUI without opening a
console when the project virtual environment is available. Start the backend
separately with the root `start.bat` first.

Configure the model in `Backend/.env` (copy `Backend/.env.example`): the
default provider is local Ollama. The selected model profile controls the
actual model: `low` uses `hermes3:3b`, `medium` uses
`hermes3:8b-llama3.1-q3_K_M`, and `high` uses `LOCAL_HERMES_MODEL` (default
`hermes3:8b`). Install the model for the selected profile with `ollama pull
<model-name>`, or change the Hermes profile in the backend Settings. Start
the backend with `Backend\sarthi.bat` (or the root `start.bat`), then run the
client. `Desktop\sarthi.exe` is the client only; it does not launch the
backend. Set `SARTHI_BACKEND_URL` only when the backend is not at
`http://127.0.0.1:8000`.

The backend launcher starts the local Ollama service when its configured
Ollama endpoint is on this computer and is not already responding. It reports
if the selected model is missing, but does not download model weights; install
the selected profile's model separately with `ollama pull <model-name>`.

Example queries: `Why is the sky blue?`, `What window is active?`,
`turn sad`, `make Hitori happy`, `turn sleeping`, `play youtube`,
`play lost in love on youtube`, `turn sad and play lost in love on youtube`,
`Open https://example.com`, or
`Type hello into the active window`.
Direct pet mood commands are resolved deterministically by the backend and
map to the Windows client's Hitori images (sleeping, happy, thinking, working,
and sad; confused reuses the sad image). They do not invoke the language model.
YouTube play requests are resolved to the first matching video by the backend;
the desktop client opens its watch URL so playback happens in the user's
browser. If resolution cannot find a video, the current resolver falls back to
the YouTube search page. For the supported compound pet plus YouTube
command, Hermes runs once to split the request; the backend validates every
subcommand against its deterministic allowlist, then sends the ordered actions
to the client. The client executes them in order and stops if one fails.
Choose Low, Medium, or High in the desktop window and press **Save** to
persist the profile through the backend; it applies to the next query.

## Build sarthi.exe

```bash
pip install pyinstaller
pyinstaller Desktop/sarthi_client.spec --noconfirm --distpath Desktop/dist
copy Desktop\dist\sarthi.exe Desktop\sarthi.exe
```text

Double-click `Desktop/sarthi.exe` → the SARTHI window opens. Type
`open chrome`, press **Send** (or Enter), and the Backend's response
appears in the response area.

## Boundary rules (locked by tests)

- The client never imports `brain`, `interpreter`, `model`, `knowledge`,
  or `executor` — only HTTP via `backend.py`.
- Backend never imports anything from `Desktop/`.
- Malformed responses and an unreachable backend become structured
  failures shown in the status bar — the GUI never crashes on them.
