# API (observed)

FastAPI app in `Backend/api.py`, served by Uvicorn on `0.0.0.0:8000`
(`sarthi.bat`, `python api.py`). Interactive docs at `/docs`; dashboard at
`/ui`. CORS restricted to the two local dashboard origins.

## Core command API

| Endpoint | Method | Purpose |
| --- | --- | --- |
| `/command` | POST | Main pipeline. Accepts `{"query"}` (clients) or `{"text"}` (legacy UI). Returns the client envelope `{success, response, data}` + legacy fields. Handles mode commands and conversation mode; hands task-shaped instructions to Hermes *before* execution (AD-04); otherwise runs the deterministic pipeline and, on failure, consults the complexity router and may run the Hermes agent |
| `/health` | GET | Liveness + version (`{"assistant": "Sarthi", "status": "Running"}`) |
| `/` | GET | Redirects to /ui |

## Mode & voice

| Endpoint | Method | Purpose |
| --- | --- | --- |
| `/mode` | GET/POST | Get/set chat mode (`default` \| `conversation`) |
| `/listen` | POST | Record + transcribe voice, then run the same pipeline |

## Knowledge & applications

| Endpoint | Method | Purpose |
| --- | --- | --- |
| `/knowledge` | GET | Knowledge-store stats |
| `/applications` | GET | Known applications |
| `/applications/categories` | GET | Category counts |
| `/applications/favourites` | GET | Favourite apps |
| `/applications/categorize` | POST | Move app to favourite/ignored/unattended |
| `/applications/run` | POST | Run Anyway (bypass favourites gate) |
| `/websites/search-and-save` | POST | Browser-search fallback for unknown "open X"; remembers the site |

## Settings & memory

| Endpoint | Method | Purpose |
| --- | --- | --- |
| `/settings` | POST | Save a key/value setting |
| `/settings/{key}` | GET | Read one setting |
| `/settings/voice-replies` | GET/POST | Spoken-replies toggle (default on) |
| `/memory` | GET | List /remember facts |
| `/memory/{key}` | DELETE | Delete one fact |
| `/command-history` | GET | Recent commands |
| `/command-history/{id}` | DELETE | Delete one history entry |

## Chat

| Endpoint | Method | Purpose |
| --- | --- | --- |
| `/chat` | GET | One session's persisted transcript |
| `/chat` | POST | Append a rendered message |
| `/chat` | DELETE | Clear a session (UI transcript + Hermes context; /remember facts kept) |

## Skills

| Endpoint | Method | Purpose |
| --- | --- | --- |
| `/skills` | GET | List discovered skills |
| `/skills/{id}` | GET | One skill's metadata |
| `/skills/{id}/enable` \| `disable` | POST | Toggle skill (runtime) |

## Connectors

| Endpoint | Method | Purpose |
| --- | --- | --- |
| `/connectors` | GET/POST | List / create connector configs |
| `/connectors/{id}` | PUT/DELETE | Update / delete |
| `/connectors/{id}/test` | POST | Test a connector |
| `/connectors/registry` | GET | Registered connector types |
| `/connectors/google_calendar/status` | GET | Auth status |
| `/connectors/google_calendar/connect` | POST | Desktop OAuth flow |
| `/connectors/google_calendar/connect-web` | POST | Web OAuth start |
| `/connectors/google_calendar/callback` | GET | OAuth callback |
| `/connectors/google_calendar/disconnect` | POST | Revoke |
| `/connectors/google_calendar/events` | GET | List events |

## Projects

| Endpoint | Method | Purpose |
| --- | --- | --- |
| `/projects` | GET/POST | List / create projects |
| `/projects/{id}` | GET/PUT/DELETE | Read / update / delete |

## System & testing

| Endpoint | Method | Purpose |
| --- | --- | --- |
| `/system/metrics` | GET | CPU/RAM/GPU readings (reading.py) |
| `/events/history` | GET | Recent event-bus events |
| `/test-mode` | GET/POST | Get/set dry-run mode |
| `/test/prompts` | GET | The 60 test prompts |
| `/test/run` | POST | Run all prompts through BrainEngine in test mode + hardware telemetry |

## Hermes router (`/hermes`, hermes/routes.py)

| Endpoint | Method | Purpose |
| --- | --- | --- |
| `/hermes/sandbox` | GET | Task list (paged) |
| `/hermes/sandbox/tasks/{id}` | GET | One task with trace |
| `/hermes/status` | GET | Provider stack status |
| `/hermes/tools` | GET | Registered tools |
| `/hermes/chat` | POST | Chat + reasoning through the single Hermes loop (`HermesOrchestrator.process` → `HermesAgent`, fast path disabled) with session history and `/remember` facts attached. Schema unchanged |

## Browser router (`/browser`, skills/browser/routes.py)

| Endpoint | Method | Purpose |
| --- | --- | --- |
| `/browser/page` | POST | Receive page data (for a future extension) |
| `/browser/selection` | POST | Receive selection |
| `/browser/current` | GET | Cached current page |
| `/browser/session` | GET | Cached session |
| `/browser/action` | POST | Placeholder — returns `{"status": "pending"}` |

## Endpoint count: 46 (34 api.py + 5 hermes + 5 browser + / + /docs-related)
