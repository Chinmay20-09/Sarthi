# Project state

This document records the current implementation. The source code is the final authority. Check the source before you make a change.

## Implemented

- FastAPI backend with a deterministic Brain pipeline.
- Hermes model path with bounded iterations, retrieved context, registered tools, and tool validation.
- Windows Desktop Hand with an allow-list of actions and argument checks.
- Desktop Agent IPC for structured action requests. Remote security is not implemented.
- Desktop client local route for a clear, single-app launch. It uses a local per-user SQLite inventory.
- Desktop GUI that runs inventory, network, and model-profile work outside the Tk event loop.
- Backend database for memory, history, settings, projects, connectors, and browser profiles.
- API dashboard that can be disabled with `SARTHI_SERVE_UI=0`.
- Backend and Desktop Agent bind to `127.0.0.1` by default.
- Focused tests for local routing, client behavior, and architecture boundaries.

## Partial

- The Brain parses and executes some compound requests. The Planner is a pass-through. General model-based planning, recovery, and cross-device plans are not implemented.
- The desktop app can open a known app while the backend is offline. Other requests need the backend.
- The desktop inventory and backend application records are separate. They do not sync.
- The backend can run without the dashboard. Deployment and data recovery procedures need more work.
- Desktop Agent IPC works, but it has no pairing, authentication, or encrypted transport. Do not expose it to a network.

## Not implemented

- Android, mobile, and TV clients.
- Secure remote device enrollment and pairing.
- Network authentication and authorization for the API and Desktop Agent.
- A clean-machine release check for the packaged client.
- Backup, restore, migration, and uninstall procedures for all persistent data.

## Known release risks

- A database or inventory failure can prevent the related feature from working. Verify recovery before release.
- The backend API test run stalled during initialization in the last recorded check. Run it again and find the cause.
- The full test suite and clean-account packaged-app checks remain open.
- LAN or cloud deployment is not safe. The API and Desktop Agent have no remote security controls.

See the root [release checklist](../../to-do.md) for current work.
