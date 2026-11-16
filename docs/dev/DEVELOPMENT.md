# Development guide

Use this guide to set up, run, and change Sarthi.

## Requirements

- Windows 10 or 11 for the Desktop Hand and desktop client.
- Python 3.10 or later.
- Git.
- Ollama for local model use. This is optional.
- Chrome and browser extras for browser automation. These are optional.

## Set up the project

From the repository root, run:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

Install optional features only when needed:

```powershell
python -m pip install -e ".[automation]"
python -m pip install -e ".[browser]"
```

Copy `Backend/.env.example` to `Backend/.env`. The default provider is local Ollama. The backend launcher can start Ollama. It does not download model files. Install the model for the selected profile with `ollama pull <model-name>`.

## Run Sarthi

Start the backend:

```powershell
start.bat
```

Start the desktop client in a second terminal:

```powershell
python Desktop/run.py
```

Check backend status at `http://127.0.0.1:8000/health`. The backend binds to loopback by default. Do not expose it to a network. It has no remote authentication or encrypted transport.

To run the API without the dashboard, set `SARTHI_SERVE_UI=0` in the backend environment before startup.

## Repository map

| Path | Purpose |
| --- | --- |
| `Backend/api.py` | FastAPI service and API routes |
| `Backend/brain/` | Deterministic request pipeline |
| `Backend/hermes/` | Model routing, retrieval, validation, and tools |
| `Backend/hands/` | Validated device actions and Desktop Agent transport |
| `Backend/skills/` | Registered capabilities |
| `Backend/knowledge/` | Application and website records |
| `Backend/database/` | Backend SQLite data |
| `Desktop/client/sarthi_client/` | Windows GUI, local app route, inventory, and HTTP client |
| `tests/` | Automated tests |
| `docs/` | User, developer, product, and archive documents |

## Change rules

- Start with [Architecture](ARCHITECTURE.md) and [Project State](PROJECT_STATE.md).
- Keep direct, known actions deterministic. Use Hermes for requests that need model reasoning.
- Send physical computer actions through a Hand. Do not add shell or arbitrary code execution.
- Validate all model-selected tool calls in `hermes/validator.py`.
- Keep HTTP calls from the desktop client in `sarthi_client/backend.py`.
- Keep Windows-only imports inside the Desktop Hand or Windows client.
- Use `DatabaseManager` for backend SQLite data. Add backend table definitions to `Backend/database/models.py`.
- Update the related guide when behavior changes.
- Run Ruff and relevant tests. Read [Testing](TESTING.md) for coverage limits.

## Add a skill

1. Add `Backend/skills/<name>/manifest.json` and `main.py`.
2. Make the skill extend `BaseSkill` and implement `execute(intent)`.
3. Return a structured result. Do not use exceptions for normal control flow.
4. Check test mode before a real device action.
5. Add tests in `tests/`.

The registry loads skills from their manifests at startup.

## Package the desktop client

Use `Desktop/sarthi_client.spec` with PyInstaller. The client does not import backend packages. Keep that boundary intact.
