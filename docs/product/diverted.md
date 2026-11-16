# Sarthi PRD Alignment: Current State and Gaps

Assessment against [prd-by-me.md](prd-by-me.md). This is a repository inspection, not a code change. The project state document is dated 2026-09-16, so entries below were checked against the current source tree where possible.

## Summary

Sarthi has substantial pieces of the proposed architecture, but its current runtime is still primarily a backend-centered desktop product. The Desktop Hand and deterministic command pipeline exist, the backend already serves structured APIs and model context, and a remote Desktop Agent can execute validated actions over HTTP. Since this assessment, the desktop client gained a narrow local route for explicit single-app launches with a per-user inventory, and the API dashboard became optional for headless use. Android/mobile and TV clients remain absent; device inventory synchronization, general multi-step planning, and secure device pairing remain open.

## Requirement-by-requirement status

| PRD area | Status | What exists | What is missing or differs from the PRD |
| --- | --- | --- | --- |
| Layer 1: desktop application | **Partial** | A Windows tkinter client exists in `Desktop/client/sarthi_client/`. It handles explicit single-app launch requests locally and sends other requests over HTTP. | Local routing covers only explicit, uniquely resolved app launches. Other local deterministic actions and shared app-category policy are not yet in the client layer. |
| Desktop Hand | **Implemented, backend-owned in the default setup** | `Backend/hands/desktop/hand.py` exposes a fixed set of structured actions and validates arguments. It performs explicit operations and does not reason. | The hand is normally instantiated and called by the backend on the backend host. It is not packaged as part of a self-contained desktop application layer. The HTTP Desktop Agent can place execution on another Windows process/machine, but it is a separate opt-in mode. |
| Deterministic application-name routing | **Implemented in backend path** | The backend knowledge/entity resolver and app launcher resolve known applications/aliases; the Desktop Hand launches by explicit path. Unknown apps can use scan/browser fallback. | Resolution and inventory are not local to the desktop application or hand. The hand itself intentionally expects an already-resolved path, so the PRD's local ownership boundary is not met. |
| Mobile application | **Not implemented** | The API request schema anticipates future clients. `flutter/README.md` describes a future Flutter client. | There is no mobile client source or mobile-specific experience in the repository. |
| Android APK | **Not implemented** | `apk/README.md` reserves the directory for future distribution. | No APK project, build configuration, or application exists. |
| TV APK/application | **Not implemented** | No TV application or TV-specific source/build setup was found. | TV interface, device capabilities, packaging, and supported actions remain undefined in code. |
| Layer 2: backend orchestration and model | **Implemented** | FastAPI, Brain, Hermes, model providers, structured tools, and retrieval are present under `Backend/`. The backend coordinates deterministic handling and model-assisted handling. | Current service combines API, orchestration, knowledge, persistence, dashboard serving, and (in local mode) desktop execution in one backend deployment. The PRD's clearer separation between client/device and backend responsibilities has not been completed. |
| Headless backend | **Largely supported, not deployment-separated as a product** | The FastAPI service is not dependent on opening its dashboard; its API can run as a service. A separate Desktop Agent process is also available. | The backend still serves the web UI from the same process, and local execution mode couples it to the machine running it. A deployment that runs only model/orchestration on a headless host and securely coordinates remote hands is not fully productized. |
| Cross-platform request flow | **Partial foundation** | `RemoteDesktopHand`, `DesktopAgentClient`, and `Backend/desktop_agent.py` support forwarding structured, validated desktop actions to a separate Windows agent. | No mobile client initiates this flow; no device pairing or device registry binds a request to a selected PC; there is no authentication or transport security on the agent boundary. The flow is configured by backend mode/environment rather than managed as a user-facing device relationship. |
| Compound / multi-action requests | **Partial** | The interpreter supports parsing some compound command forms. Hermes desktop-query flow can split a compound request into deterministic allow-listed subcommands for supported cases. | The general Brain Planner is explicitly a pass-through (`Backend/brain/planner.py`). There is no general-purpose multi-step plan, sequencing, recovery, or broad cross-hand coordination. Existing compound behavior is limited to recognized/parser-supported or specific Hermes-supported patterns. |
| Device/application inventory | **Partial; split ownership** | The Windows client stores Start Menu shortcuts and PATH executables in a per-user SQLite inventory (`%LOCALAPPDATA%/Sarthi/device.db`). Backend API/Brain flows still use the separate `Backend/knowledge/applications.json` store. | The stores are not synchronized; backend requests targeting a remote PC do not fetch that PC's inventory or capabilities. |
| Backend memory and model context | **Implemented** | SQLite persistence and Hermes retrieval cover remembered facts, settings, command/session history, knowledge entities, and prior task context. See `Backend/database/` and `Backend/hermes/retriever.py`. | Multi-client/device ownership, account-level identity, and shared context policies are not established as part of the mobile/paired-device architecture. |
| Separate local and backend databases | **Partial** | Device-local SQLite now stores the desktop launch inventory; backend SQLite/JSON stores model context and existing Brain knowledge. | The ownership split has no sync/versioning, stale-data policy, or user/account scoping contract yet. |
| Validated execution boundary | **Implemented for desktop actions** | Desktop actions pass through an allow-listed action registry and argument validation; remote IPC also reaches the same Desktop Hand gate. | The remote service is documented as local/LAN development use and lacks pairing/authentication. Authorization to a particular user's device is not implemented. |
| Local operation during backend outage | **Partial** | The desktop client can open a uniquely matched app from its local inventory without contacting the backend. | Only the explicit single-app launch route is available offline; other deterministic local actions still depend on backend connectivity. |

## What is already aligned

- Physical desktop execution is isolated behind a Hand contract and uses explicit, validated actions (`Backend/hands/base.py`, `Backend/hands/desktop/hand.py`).
- The Desktop Hand does not make model decisions; it receives concrete action names and arguments.
- The project follows a deterministic-first pattern for recognized actions, with Hermes used for model-driven interpretation and tool planning (`Backend/brain/`, `Backend/hermes/`).
- The backend has persistent context suitable for model retrieval (`Backend/database/`, `Backend/hermes/retriever.py`).
- The HTTP API and Desktop Agent establish early service boundaries, and remote desktop execution is possible in configured mode (`Backend/hands/remote.py`, `Backend/desktop_agent.py`).
- Android and Flutter client directories are explicitly marked as future work rather than represented as completed features.

## Main architecture divergences to resolve later

1. **Expand simple local routing beyond app launch.** A narrow exact-match route now handles single app launches; other supported local actions remain backend-owned.
2. **Define ownership and synchronization for inventory.** Backend knowledge still includes discovered Windows applications. The target requires the executing device to be authoritative and to provide inventory/capabilities to backend orchestration when needed.
3. **Build the client/device layer.** Mobile, Android APK, and TV application are not implemented; no paired-device lifecycle exists.
4. **Turn remote execution into a managed cross-platform path.** IPC can forward a desktop action, but device identity, pairing, authentication, authorization, and a client-facing selection/request flow are missing.
5. **Implement general compound planning.** Some syntax and specific Hermes splitting exist, but Brain Planner does not yet produce a multi-step plan for arbitrary supported requests.
6. **Separate headless orchestration from local execution operationally.** The dashboard can be disabled with `SARTHI_SERVE_UI=0`, but local hand mode assumes a suitable execution host and remote mode lacks the secure device-management layer needed for a server coordinating user devices.

## Evidence and limits

- Current runtime and implementation status: [Architecture](../dev/ARCHITECTURE.md), [Project State](../dev/PROJECT_STATE.md).
- Desktop client boundary: [Desktop/README.md](Desktop/README.md), `Desktop/client/sarthi_client/backend.py`.
- Android/Flutter placeholders: [apk/README.md](apk/README.md), [flutter/README.md](flutter/README.md).
- Hand and IPC boundary: `Backend/hands/desktop/hand.py`, `Backend/hands/remote.py`, `Backend/desktop_agent.py`.
- Planning and model split: `Backend/brain/planner.py`, `Backend/brain/engine.py`, `Backend/hermes/desktop_query.py`.
- Inventory and persistence: `Backend/knowledge/manager.py`, `Backend/database/manager.py`, `Backend/hermes/retriever.py`.

This assessment records repository evidence and stated project status; it does not claim runtime verification or change implementation.

## Limitations to achieving the PRD target

These are the main constraints the project must resolve before the target architecture can be considered complete:

1. **Client platforms are absent.** Android/mobile and TV clients have no implementation, so their interfaces, permissions, lifecycle, connectivity behavior, and action capabilities are not yet known.
2. **Offline desktop coverage is narrow.** Explicit single-app launches work locally; all other requests still depend on the backend.
3. **Device inventory is duplicated without synchronization.** The desktop client now owns a local launch inventory, but Brain/API flows continue to use backend knowledge files. A separately hosted backend cannot reliably discover or refresh each remote device's inventory until the device reports it through a defined contract.
4. **The cross-device path has no device identity or trust model.** Remote Desktop Agent IPC has no pairing, authentication, authorization, or transport security. The backend cannot securely know which PC a request targets or whether the requester may control it.
5. **Desktop execution depends on a suitable host.** In local mode, the backend and desktop actions share a process/host. In remote mode, a Windows agent must be running and reachable. A headless backend alone cannot execute physical desktop actions.
6. **General multi-step planning is missing.** Compound parsing and a narrow Hermes split path cover selected cases, but the Brain Planner is pass-through. Ordering, partial failure handling, confirmation points, and recovery for broader plans are not defined.
7. **The service boundary is not yet a full multi-client contract.** The API has request endpoints, but target-device selection, device capability discovery, action status/progress, reconnect behavior, and version compatibility between clients, backend, and hands need definition.
8. **Application-local storage and synchronization are undefined.** The PRD calls for local device data and backend model memory, but there is no client-side inventory store or synchronization contract. Conflict handling, stale inventory, privacy, retention, and deletion behavior need decisions.
9. **Backend separation is incomplete.** The dashboard can be disabled, but the backend can still execute local desktop operations in local mode. Deployment profiles and explicit boundaries between orchestration, persistence, and device agents have not been established.
10. **Operational resilience and access control are insufficient for remote use.** The current project documents unauthenticated LAN boundaries. Remote deployment needs secure credentials, authorization checks, connection lifecycle handling, and clear failure reporting before it can safely coordinate user devices.
11. **The TV product requirements are underspecified.** The PRD names a TV APK, but supported TV platforms, interaction model, input methods, and expected local/remote actions are not yet specified. These affect the implementation and packaging approach.
12. **Target behavior lacks end-to-end validation.** Existing tests cover current backend routes and desktop IPC, but there can be no end-to-end coverage for absent mobile/TV clients, paired-device routing, local routing during backend outage, or general multi-step workflows yet.
