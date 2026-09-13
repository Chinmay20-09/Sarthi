# CLI (observed)

All entry points verified in the working tree.

## Backend

| Command | What it does | Source |
| --- | --- | --- |
| `Backend\sarthi.bat` | Starts the API server in a visible window; health-checks and prints Local/LAN URLs | Backend/sarthi.bat |
| `Backend\sarthi.bat background` | Windowless server via pythonw + uvicorn | Backend/sarthi.bat |
| `python Backend/api.py` | Direct server start (uvicorn run in-module) | api.py |
| `python Backend/main.py` | Voice CLI: ENTER to speak → record → whisper → BrainEngine → print intent/result | Backend/main.py |
| `python Backend/main-test.py` | Smoke test: a few prompts through BrainEngine (NOT the test suite) | Backend/main-test.py |
| `python Backend/desktop_agent.py --capabilities` | Print the Desktop hand's implemented/planned capability report | Backend/desktop_agent.py |
| `python Backend/desktop_agent.py --self-test` | Read-only actions (active window, clipboard, process list) | Backend/desktop_agent.py |
| `python Backend/desktop_agent.py --exec ACTION key=value` | Run one explicit hand action (validation-gated) | Backend/desktop_agent.py |
| `python -m skills.automation_engine.ai_chain.calibrate [opts]` | Show/record ai_chain site calibration points | ai_chain/calibrate.py |
| `python Backend/scripts/clean_sandbox.py` | Clean the Hermes sandbox from the CLI | Backend/scripts/clean_sandbox.py |

## Desktop client

| Command | What it does | Source |
| --- | --- | --- |
| `python Desktop/run.py` | Launch the tkinter client in dev mode | Desktop/run.py |
| `Desktop/dist/sarthi.exe` | Packaged client (PyInstaller, `sarthi_client.spec`) | build output |

## Hermes standalone

| Command | What it does | Source |
| --- | --- | --- |
| `python -m hermes.main` | Single test prompt through the orchestrator; prints provider status and response | hermes/main.py |

## Tests

| Command | What it does |
| --- | --- |
| `pytest` | The root suite (pyproject: testpaths=tests, pythonpath=Backend+Desktop/client) |
| `POST /test/run` | In-app runner: 60 prompts through BrainEngine in test mode + telemetry (not pytest) |

## Notes

- There is no argparse-driven main CLI beyond the flags above; the API is the
  primary interface.
- `main.py` requires microphone + whisper stack; everything else runs without.
