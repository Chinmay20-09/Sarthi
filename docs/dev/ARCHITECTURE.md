# Architecture

This guide describes the current code. It does not describe planned work as complete. See [Project State](PROJECT_STATE.md) for status.

## System layers

```text
Windows desktop app
  ├─ direct single-app launch → local inventory → LocalDesktopHand → Windows
  └─ other request → FastAPI backend → Brain → skill or Hermes
                                      └─ validated action → Desktop Hand
```

The desktop client owns one local route: an explicit request to open one app. It matches the app against the local inventory. It sends unknown, compound, and other requests to the backend.

The backend runs without the dashboard. Set `SARTHI_SERVE_UI=0` before startup to disable the static UI. The backend and Desktop Agent bind to `127.0.0.1` by default. Do not expose either service to a network. Neither service has remote authentication or encrypted transport.

## Main components

| Component | Code | Responsibility |
| --- | --- | --- |
| Desktop GUI | `Desktop/client/sarthi_client/gui.py` | Accept user input and show results. |
| Local router | `Desktop/client/sarthi_client/local_router.py` | Match a narrow, explicit app-launch request. |
| Local inventory | `Desktop/client/sarthi_client/app_inventory.py` | Store apps found in Start Menu folders and `PATH`. |
| Local hand | `Desktop/client/sarthi_client/local_hand.py` | Launch an existing inventory entry. |
| HTTP client | `Desktop/client/sarthi_client/backend.py` | Send backend requests and receive structured responses. |
| API | `Backend/api.py` | Validate requests and call backend services. |
| Brain | `Backend/brain/` | Parse direct requests, resolve targets, and call handlers or skills. |
| Hermes | `Backend/hermes/` | Use a model for requests that need reasoning. Validate each tool call before execution. |
| Skills | `Backend/skills/` | Group backend capabilities. |
| Desktop Hand | `Backend/hands/desktop/` | Perform allow-listed Windows actions. |
| Database | `Backend/database/` | Store backend memory, history, settings, and other service data. |

## Request routing

### Local app launch

1. `SarthiController` calls the local router.
2. The router accepts only `open`, `launch`, `start`, or `run` followed by one app name.
3. The inventory returns a match only when the name maps to one entry.
4. `LocalDesktopHand` checks that the entry is an existing absolute `.lnk` or `.exe` path.
5. The hand launches the entry. The backend is not required.

If there is no unique match, the client sends the request to the backend. The router does not use fuzzy matching. It does not accept a path from user text.

### Backend request

`Desktop/client/sarthi_client/backend.py` sends requests to `POST /desktop/query`. The API calls `hermes.desktop_query.run_desktop_query`. Hermes can call a model and request one of the registered desktop actions. The action name and arguments pass validation before the Desktop Hand runs them.

The legacy `POST /command` route remains available to the dashboard and other callers. It runs the Brain pipeline. Some compound commands produce multiple intents and execute them in order. The Brain Planner itself remains a pass-through.

## Brain and Hermes

The Brain handles recognized requests without a model. Its main stages are:

1. Parse text into one or more intents.
2. Pass each intent through the Planner.
3. Resolve known entities.
4. Run the matching handler or skill.

The API can escalate some requests to Hermes. Hermes retrieves bounded context, calls the configured model, validates any tool request, and runs an approved tool. Its loop has iteration and time limits. Hermes does not perform physical computer actions by itself. A Hand performs those actions.

The configured provider can be local Ollama or a supported remote provider. Provider settings are in `Backend/.env`. Never store real secrets in a tracked file.

## Hands and action validation

`Backend/hands/base.py` defines the Hand contract. `DesktopHand` implements Windows actions. It rejects unknown actions and invalid arguments. It returns structured results for success and failure.

`RemoteDesktopHand` sends structured requests to `Backend/desktop_agent.py`. The agent validates each request through the same Desktop Hand. This IPC path has no authentication or encrypted transport. Use loopback only.

Do not add shell, `eval`, arbitrary code execution, or an unvalidated subprocess action.

## Data stores

| Data | Location | Owner |
| --- | --- | --- |
| Desktop app inventory | `%LOCALAPPDATA%/Sarthi/device.db` | Windows desktop client |
| Backend database | `Backend/database/sarthi.db` | `DatabaseManager` |
| App and website entities | `Backend/knowledge/*.json` | `KnowledgeManager` |
| Hermes task records | `Backend/sandbox/` | Hermes sandbox |

The local inventory and backend app records do not sync. Backend memory is separate from device inventory. The client refreshes its inventory at first use and then at most once per day.

Use `DatabaseManager` for backend SQLite operations. Define backend schema in `Backend/database/models.py`. Do not commit database files, `.env` files, sandbox output, or build output.

## API and runtime

The FastAPI app is in `Backend/api.py`. It provides `/health`, `/command`, `/desktop/query`, settings, memory, history, projects, skills, connectors, and other routes. Review `api.py` for the current endpoint list.

Start the backend with `start.bat` or `Backend/sarthi.bat`. Start the desktop client with `python Desktop/run.py`. The packaged executable is a client; it does not start the backend.

The dashboard is served at `/ui` when enabled. The root route redirects to the dashboard. When the dashboard is disabled, the root route returns service status.

## Configuration

| Setting | Purpose | Default |
| --- | --- | --- |
| `SARTHI_SERVE_UI` | Enable or disable the dashboard mount | `1` |
| `API_HOST` in `Backend/config.py` | Backend bind address | `127.0.0.1` |
| `SARTHI_DESKTOP_AGENT_MODE` | Select local or remote hand | `local` |
| `SARTHI_DESKTOP_AGENT_HOST` | Agent address | `127.0.0.1` |
| `SARTHI_DESKTOP_AGENT_PORT` | Agent port | `8765` |
| `SARTHI_BACKEND_URL` | Backend address for the desktop client | `http://127.0.0.1:8000` |

Remote bind addresses are not production-ready. The API and Desktop Agent do not authenticate remote clients.

## Dependency boundary

- Keep backend logic out of the desktop client.
- Keep all desktop HTTP calls in `sarthi_client/backend.py`.
- Keep Windows APIs inside the Windows client or `Backend/hands/desktop/`.
- Keep model tool calls behind `hermes/validator.py`.
- Keep OS actions behind a Hand.
- Keep skills and tools registered through their current registries.

See [Development](DEVELOPMENT.md), [Testing](TESTING.md), and [Project State](PROJECT_STATE.md) for work rules, test coverage, and remaining gaps.
