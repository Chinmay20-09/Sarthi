# Product and architecture decisions

Record each decision here. State the decision, reason, and effect.

## 2026-11-16: Route one app launch on the desktop

**Decision:** The desktop app handles an explicit, single app launch when one inventory entry matches. It sends other requests to the backend.

**Reason:** Direct actions should use a deterministic route. The client must not guess the meaning of a complex request.

**Effect:** The local route supports app launch only. It does not use a model.

## 2026-11-16: Store app inventory on the Windows device

**Decision:** Store the current user's app inventory in `%LOCALAPPDATA%/Sarthi/device.db`. Find apps from Start Menu shortcuts and executable files on `PATH`.

**Reason:** The device that runs an app must own the inventory for that app.

**Effect:** The inventory is Windows-specific. The scanner does not search the full disk or run a path from user input.

## 2026-11-16: Separate app lookup from app launch

**Decision:** The router finds one inventory entry. The local hand launches only its stored absolute `.lnk` or `.exe` path.

**Reason:** User text must not become a command or file path.

**Effect:** A direct launch does not use backend favourite categories. An explicit launch request permits the app to open when one entry matches.

## 2026-11-16: Make the dashboard optional

**Decision:** Keep the dashboard enabled by default. Set `SARTHI_SERVE_UI=0` to disable it.

**Reason:** The backend API must run without a graphical interface.

**Effect:** This setting does not add remote authentication or device pairing.

## 2026-11-16: Bind the backend to this computer

**Decision:** Bind the backend and Desktop Agent to loopback by default.

**Reason:** They do not authenticate remote requests or encrypt remote traffic.

**Effect:** LAN and remote control are unsupported until security controls exist.

## 2026-11-16: Defer mobile and TV control

**Decision:** Do not provide mobile or TV control of a PC until device pairing, identity, authorization, and protected transport exist.

**Reason:** The current remote agent does not provide those controls.

**Effect:** Keep mobile and TV work out of the desktop release scope.
