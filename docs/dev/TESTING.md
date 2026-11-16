# Testing

Use the project virtual environment. Run tests from the repository root.

## Run tests

Run the full suite:

```powershell
.\.venv\Scripts\python.exe -m pytest
```

Run focused desktop checks:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_desktop_local_router.py tests/test_desktop_client.py tests/test_architecture_boundaries.py
```

Run Ruff:

```powershell
.\.venv\Scripts\python.exe -m ruff check Backend Desktop/client tests
```

Set `SARTHI_TEST_VOICE=0` to disable test voice announcements.

## What tests cover

The suite uses fakes for models, network calls, browsers, and device actions. It checks:

- Brain parsing and routing.
- API request and response formats.
- Hermes tool validation and provider behavior.
- Hand action validation and Desktop Agent IPC.
- Database operations and knowledge lookup.
- Desktop client response handling and local app routing.
- Architecture boundaries between the client, backend, Brain, Hermes, and Hands.

The local-router tests do not launch installed apps. They replace the local hand with a fake.

## Test limits

The automated suite does not prove that:

- A real model provider works.
- A real browser or laptop action works.
- A remote Desktop Agent works across two computers.
- A packaged app works on a clean Windows account.
- The microphone or speech output works on hardware.

Do not expose the backend or Desktop Agent to a network during tests. They have no remote authentication or encrypted transport.

## Manual release checks

Before release:

1. Install the packaged app on a clean Windows account.
2. Confirm that a known app launches while the backend is stopped.
3. Confirm that an unknown or ambiguous app request does not launch another app.
4. Start the backend with `SARTHI_SERVE_UI=0`. Confirm that `/health` works and the dashboard is not mounted.
5. Stop the backend. Confirm that the desktop app reports a clear error for a request that needs the backend.
6. Confirm that the app inventory and backend database persist after a restart.
7. Test remote IPC only after authentication and encrypted transport are available.
