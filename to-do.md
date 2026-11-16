# Desktop and backend release checklist

Scope: Windows desktop app, Desktop Hand, and backend. Android and TV work is deferred. See [product documents](docs/product/) for requirements and decisions.

## Desktop app and hand

- [ ] Keep local routes direct and deterministic.
- [ ] Handle unreadable folders, long paths, duplicate names, missing apps, and empty inventories.
- [ ] Add a user control to refresh the app inventory. Show its status.
- [ ] Define rules for shortcuts, packaged apps, aliases, and app categories.
- [ ] Launch only entries from the device inventory. Reject other file types and stale paths.
- [x] Run inventory scans, network calls, and model-profile calls outside the Tk event loop. Update the window on the main thread.
- [ ] Keep local app launch available when the backend is offline. Show a clear error for other offline requests.
- [ ] Confirm that the packaged app includes all required modules and stores data in the per-user folder.

## Backend and service boundary

- [ ] Define request fields, response fields, errors, time limits, and cancel behavior.
- [ ] Keep the API, model logic, data store, dashboard, and device actions as clear components.
- [ ] Document a headless setup that does not start the dashboard.
- [ ] Prevent a server from using a local Desktop Hand unless an operator enables it.
- [ ] Add authentication, authorization, and encrypted transport before any network access.
- [ ] Keep Desktop Agent actions allow-listed, validated, logged, and size-limited.
- [ ] Document data ownership, backup, retention, migration, and recovery.
- [x] Bind the backend and Desktop Agent to loopback by default. Do not advertise LAN access.

## Release checks

- [x] Add tests for local routing, ambiguous app names, stale entries, backend fallback, and client boundaries.
- [ ] Run the full test suite and fix all failures.
- [x] Build the desktop app with PyInstaller in an isolated output folder.
- [ ] Run the packaged app on a clean Windows account without the development environment.
- [ ] Check backend start, stop, headless mode, missing model, bad configuration, and database recovery.
- [ ] Test remote access only after security controls are complete.
- [ ] Document installation, update, configuration, support, data paths, and uninstall cleanup.
- [ ] Update [architecture](docs/dev/ARCHITECTURE.md), [project state](docs/dev/PROJECT_STATE.md), and [testing](docs/dev/TESTING.md) after verified changes.

## Current implementation

- [x] Route an explicit single-app launch from the local inventory.
- [x] Store the Windows user's inventory in SQLite.
- [x] Keep app lookup separate from app launch. Launch only stored `.lnk` and `.exe` paths.
- [x] Send unknown, ambiguous, and compound requests to the backend.
- [x] Allow headless API use with `SARTHI_SERVE_UI=0`.
- [x] Add focused tests and build the desktop executable.

## Release is ready when

- [ ] The packaged app opens a supported app without the backend and never runs an unlisted path.
- [ ] The backend gives a bounded, structured result for every request.
- [ ] Network access is authenticated and encrypted before an operator enables it.
- [ ] Data survives upgrades and has documented backup and recovery steps.
- [ ] Full tests and clean-machine release checks pass.
