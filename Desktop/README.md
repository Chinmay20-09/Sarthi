# Sarthi Desktop client

A thin Windows client for the Sarthi Backend. The client contains **no
assistant intelligence** — it sends the user's query to the Backend API
(`POST /command`) and displays the response.

```
Desktop (sarthi.exe)  --HTTP-->  Backend (:8000)  --HTTP-->  Desktop
```

## Layout

| Path | Purpose |
| --- | --- |
| `client/sarthi_client/` | client source (tkinter GUI, controller, backend HTTP boundary, config) |
| `client/sarthi_client/gui.py` | the SARTHI window (Query textbox → Send → Response) |
| `client/sarthi_client/controller.py` | validate → send → translate (no tk, no http) |
| `client/sarthi_client/backend.py` | the ONLY module that talks HTTP — `{"query": ...}` → `/command` |
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
```

```powershell
$env:SARTHI_BACKEND_URL = "https://sarthi.example.com"   # cloud backend
```

The default stays on loopback; the Backend is not exposed publicly by
default.

## Run from source

```bash
# terminal 1 — start the backend
Backend\sarthi.bat

# terminal 2 — start the client
python Desktop/run.py
```

## Build sarthi.exe

```bash
pip install pyinstaller
pyinstaller Desktop/sarthi_client.spec --noconfirm --distpath Desktop/dist
copy Desktop\dist\sarthi.exe Desktop\sarthi.exe
```

Double-click `Desktop/sarthi.exe` → the SARTHI window opens. Type
`open chrome`, press **Send** (or Enter), and the Backend's response
appears in the response area.

## Boundary rules (locked by tests)

- The client never imports `brain`, `interpreter`, `model`, `knowledge`,
  or `executor` — only HTTP via `backend.py`.
- Backend never imports anything from `Desktop/`.
- Malformed responses and an unreachable backend become structured
  failures shown in the status bar — the GUI never crashes on them.
