# Desktop and Backend Readiness — Work Report

**Date:** 2026-11-16

## Completed in this pass

- Focused scope on Windows desktop and backend; Android and TV work is deferred.
- Moved the PRD, architecture gap analysis, decisions, prior report, and divergence matrix into `docs/product/`, leaving `to-do.md` as the root task document.
- Added exact local routing for single-app launch requests, device-owned SQLite inventory, duplicate-name rejection, and a separate local launch hand.
- Made the dashboard optional and changed both backend and Desktop Agent defaults to loopback. Updated the launcher and setup docs so they no longer advertise unauthenticated LAN access.
- Moved inventory, API, and model-profile work off the Tk event loop; worker results are applied on the main thread and failures restore UI controls.
- Added isolated desktop route and inventory tests, and updated architecture/project-state/setup documentation.

## Validation

- Passed: `tests/test_desktop_local_router.py`, `tests/test_desktop_client.py`, and `tests/test_architecture_boundaries.py` in the project virtual environment (56 tests).
- Passed: Ruff checks for the changed Python files.
- Passed: PyInstaller desktop build in a temporary, isolated output directory; the existing executable was not overwritten and the temporary artifacts were removed afterward.
- Not completed: backend API tests stalled after application initialization; interrupted the run. API startup/headless behavior therefore remains unverified.
- The full test suite was not run; Android/mobile is outside this scope.

## Remaining production gates

- Add a visible inventory refresh/status control and validate scanner behavior on clean Windows profiles.
- Decide and implement local app launch policy for favourites/ignored entries, aliases, and app categories.
- Add authenticated and encrypted remote access before allowing LAN or cross-device operation; current API and Desktop Agent remain local-only.
- Smoke-launch the generated package and validate local launch on a clean Windows profile.
- Diagnose the API test stall, run the full suite, and verify the headless API option using the project's supported runtime.
- Document backup/migration/uninstall behavior for both the device inventory and backend database.

The active checklist is [to-do.md](../../to-do.md); architectural rationale is in [decisions.md](decisions.md).
