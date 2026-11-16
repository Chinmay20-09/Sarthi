# Sarthi Product Requirements: Layered Architecture

## Product direction

Sarthi is a cross-platform assistant built from user-facing applications, local execution hands, and a separately deployable backend. Routine actions should take a direct, deterministic route through the appropriate hand. The backend provides model-driven reasoning and shared coordination when a request crosses platforms or needs multiple actions to be planned together.

## Architecture overview

### Layer 1: Applications and hands

This layer receives user input, handles platform-local experience, and performs actions on the device.

- **Desktop application and Desktop Hand:** The application provides the desktop interface. The Desktop Hand performs supported operations on that computer.
- **Mobile application:** Provides a mobile interface and can request actions on the phone or on another paired device, such as controlling a PC.
- **TV application (APK):** Provides a TV-compatible application package and interface. Device capabilities determine which actions it can perform.

Each application or hand routes known local actions deterministically. For example, a request such as “open Calculator” is resolved against the desktop's known applications and launches the matching app without asking a model to choose the route. Hands execute validated actions; they do not perform open-ended model reasoning.

### Layer 2: Backend

The backend contains shared orchestration, model access, and model-facing context. It has no required user interface and must be able to run as a headless service.

The backend is engaged when an application submits a request that needs cross-platform coordination (for example, a mobile request to control a paired PC) or when a single request contains multiple actions or questions that need to be interpreted and coordinated together. The backend may use models to understand and plan such requests, then sends structured, validated actions to the appropriate hand. The hand remains responsible for carrying out the physical operation.

## Routing requirements

1. Prefer a deterministic local route when the request maps to a known action and target on the current device.
2. Resolve application names and aliases using the local system's application knowledge. A clear app-opening request should launch the resolved application directly.
3. Escalate to the backend for cross-platform requests and compound requests (more than one action or question in one request).
4. The backend may plan and coordinate; it must not directly operate a user's device. Device actions must pass through the relevant hand and its validation boundary.
5. If a target is ambiguous, unavailable, or unsupported, return a clear result instead of guessing or silently invoking an unrelated action.

## Data and memory

Data is held at both the application/device layer and backend, with distinct purposes:

- **Device/application database:** Records the current device's system and application inventory, such as installed applications and their resolvable names. The Desktop Hand uses this information to understand what is available on that computer and to route local actions deterministically.
- **Backend database:** Stores information needed for model context, such as relevant conversation history, user preferences, and remembered facts. It gives backend reasoning continuity across requests and clients.

The two stores serve different jobs. Device inventory is grounded in the device that will execute the action; backend memory supplies context for interpreting and coordinating requests. Cross-device actions must use the target device's available capabilities and inventory rather than assuming the requesting device has them.

## Example request flows

### Local, single action

User asks the desktop application to open an app → Desktop Hand resolves the app name against the desktop inventory → Desktop Hand launches the app → result is returned to the application.

### Cross-platform action

User asks the mobile application to control the PC → mobile application sends a structured request to the backend → backend identifies the target PC and coordinates the request → the PC's Desktop Hand validates and executes the action → result returns through the backend to mobile.

### Compound request

User submits multiple actions in one request → application sends the request to the backend → backend uses model context to interpret and sequence the work → each device action is sent to its responsible hand for validation and execution → the combined result is returned to the application.

## Deployment and interface requirements

- Applications provide the user-facing interfaces; the backend does not depend on a graphical interface.
- The backend can run locally or on a headless server, subject to network connectivity and configured model availability.
- Applications communicate with the backend through a defined service boundary. Hands communicate through validated, structured action requests and return structured results.
- Losing backend connectivity must not prevent supported local deterministic actions from working on the device.

## Scope boundary

This PRD describes the target product architecture. It does not claim that mobile or TV hands, cross-device pairing, or every routing path are already implemented. Current implementation status is documented in [Architecture](../dev/ARCHITECTURE.md) and [Project State](../dev/PROJECT_STATE.md).
