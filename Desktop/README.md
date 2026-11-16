# Sarthi Desktop client

The Windows client has one local action: it can open one known app. It uses the app inventory stored on this PC. This action works when the backend is offline.

The client sends other requests to `POST /desktop/query`. The backend handles model requests and other desktop actions. The client performs approved pet and browser actions that the backend returns.

## Run from source

Start the backend in one terminal:

```powershell
Backend\sarthi.bat
```

Start the client in a second terminal:

```powershell
python Desktop/run.py
```

The backend uses local Ollama by default. Copy `Backend/.env.example` to `Backend/.env` to configure it. Install the selected model with `ollama pull <model-name>`. The backend launcher can start Ollama, but it does not download model files.

## Local app inventory

The client stores app entries in `%LOCALAPPDATA%/Sarthi/device.db`. It scans Start Menu shortcuts and executable files on `PATH` at first use. It refreshes the inventory at most once per day.

The local route accepts `open`, `launch`, `start`, or `run` followed by one app name. It requires one exact match or a known alias. It does not use fuzzy matching. It does not accept a file path from the request.

## Backend address

The default is `http://127.0.0.1:8000`. Configure another address with `SARTHI_BACKEND_URL` or `sarthi_client.json`.

The backend and Desktop Agent do not authenticate remote requests or encrypt remote traffic. Do not use a LAN or cloud address. The default loopback address is the supported setup.

## Build the Windows executable

Install PyInstaller, then run:

```powershell
python -m PyInstaller Desktop/sarthi_client.spec --noconfirm --distpath Desktop/dist
Copy-Item Desktop\dist\sarthi.exe Desktop\sarthi.exe
```

The executable is the client only. It does not start the backend.

## Client boundaries

- `controller.py` routes input and updates the result.
- `local_router.py` handles a single known app launch.
- `app_inventory.py` stores local app entries.
- `local_hand.py` launches an inventory entry.
- `backend.py` is the only client module that sends HTTP requests.
- The backend does not import the desktop client.

Run the client tests with `pytest tests/test_desktop_client.py tests/test_desktop_local_router.py`.
