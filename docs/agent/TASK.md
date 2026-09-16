# Task

> **STATUS: ACTIVE** — sprint started 2026-09-16.
> Context: read [CURRENT_CONTEXT.md](CURRENT_CONTEXT.md) first; obey
> [CONSTRAINTS.md](CONSTRAINTS.md). Permanent truth: `docs/dev/`.

## Objective

Close the OPEN security item on the Brain ↔ Desktop Agent IPC boundary
(`docs/dev/PROJECT_STATE.md` → "Current architectural issues"): the Desktop
Agent server (`Backend/desktop_agent.py --server`) currently accepts
unauthenticated `POST /execute` requests from anyone who can reach the port,
which executes real OS actions on the agent's machine. Add authentication
(and the minimum pairing story that makes it usable) without breaking the
local mode or the existing `Hand` contract.

## Requirements

1. **Authenticated actions.** Every action-bearing request (`POST /execute`)
   must require a shared secret. Client (`hands/transport.py`) sends it;
   server (`desktop_agent.py`) rejects requests without a valid token with a
   **structured failure** (never a crash, never a raise) — following the
   existing pattern where transport problems are shaped into
   `DesktopResult`-shaped dicts. The rejection must be distinguishable from
   "agent unreachable" (e.g. a dedicated error code such as
   `transport_unauthorized`) so the Brain can tell "refused" from "no one
   listening".
2. **Fail closed on non-loopback binds.** When no token is configured, the
   agent must refuse to bind to any non-loopback host (clear error message),
   so today's dev experience on `127.0.0.1` keeps working unchanged while a
   LAN bind without a secret becomes impossible.
3. **Zero new dependencies on the agent side.** The server deliberately uses
   the stdlib `http.server` so it runs on a bare Windows Python; auth must
   not add a framework or third-party dependency there (stdlib hashing/
   `secrets`/`hmac` are fine; constant-time comparison required).
4. **Secret hygiene.** Token comes from config/env
   (`SARTHI_DESKTOP_AGENT_TOKEN`, following the existing `SARTHI_DESKTOP_AGENT_*`
   pattern in `Backend/config.py` + `Backend/.env.example`); never logged,
   never echoed in error messages or sandbox records.
5. **Pairing = minimum viable.** On first start with a generated token, the
   agent prints/writes the token for the user to copy to the Brain's `.env`.
   No PKI, no mTLS, no heavy handshake — document that this is a
   LAN/local-trust boundary improvement, not internet-grade security.
6. **Health/capabilities endpoints.** `GET /health` and `GET /capabilities`
   must not disclose configuration details (host/port/token) to
   unauthenticated callers; either require the token or reduce the unauthenticated
   payload to a minimal liveness ack (implementer's choice, document it).
7. **Behaviour preservation.** `local` mode and the in-process `DesktopHand`
   path are byte-for-byte unchanged. The `Hand` interface
   (`hands/base.py`) gains no new members. The wire format change is limited
   to the auth credential; existing request/response payloads are unchanged.
8. **Documentation in the same change:** the IPC section of
   `docs/dev/ARCHITECTURE.md`, the OPEN row in `docs/dev/PROJECT_STATE.md`,
   `docs/client/INSTALLATION.md` + `docs/client/FAQ.md` (LAN warning → token
   setup), `Backend/.env.example`, and the server's own docstring security
   note.
9. **Stay cross-platform:** `hands/transport.py` and `hands/remote.py` remain
   importable on Linux/Android (no Windows-only imports, no new heavy imports).

## Acceptance Criteria

- [ ] Unauthorized `POST /execute` (missing/wrong token) returns a structured
      failure with the dedicated error code; nothing executes on the agent.
- [ ] Agent with no token refuses to bind non-loopback; loopback works as today.
- [ ] `local` mode tests pass unmodified — `tests/test_desktop_agent_ipc.py`,
      `tests/test_brain_hand_boundary.py` green without behavioural edits
      (new tests are additive).
- [ ] New tests cover: valid token accepted; missing token rejected; wrong
      token rejected; unauthorized error distinct from `transport_unavailable`;
      non-loopback bind without token fails closed; token never appears in
      logs/results.
- [ ] Full pytest suite passes (baseline: **1127 passed**, 2026-09-16).
- [ ] `ruff check Backend tests` clean; no new runtime dependencies in
      `pyproject.toml`.
- [ ] Docs updated per Requirement 8; `docs/dev/PROJECT_STATE.md` no longer
      lists the IPC boundary as OPEN (or narrows it to what remains, e.g.
      transport encryption).
- [ ] Manual validation documented for a real two-machine run (Brain with
      token → agent on LAN host): rejected without token, accepted with
      token — see `docs/dev/TESTING.md` manual-validation section.

## Relevant Files

| Area | Files |
| --- | --- |
| Server (auth check + fail-closed bind + token bootstrap) | `Backend/desktop_agent.py` |
| Client transport (send credential, shape unauthorized failures) | `Backend/hands/transport.py` |
| Remote hand (unchanged or thin pass-through) | `Backend/hands/remote.py` |
| Config constants + env plumbing | `Backend/config.py`, `Backend/.env.example` |
| Tests (additive) | `tests/test_desktop_agent_ipc.py` |
| Docs | `docs/dev/ARCHITECTURE.md` (IPC section), `docs/dev/PROJECT_STATE.md`, `docs/dev/TESTING.md`, `docs/client/INSTALLATION.md`, `docs/client/FAQ.md`, `Backend/.env.example` |

## Non-Goals

- Authentication for the main FastAPI server (`Backend/api.py`, 0.0.0.0:8000)
  — a separate concern, not this boundary.
- TLS/mTLS, certificates, device-registration protocol, or internet-grade
  security — the boundary stays LAN-trust; token auth is the scope.
- Changing the `DesktopHand` allow-list, `Hand` interface members, or the
  request/response payload schema.
- Any change to `local` mode or in-process execution.
- The deferred items (AD-12 control-layer merge, capability discovery,
  Android/remote Hands) — see `docs/dev/PROJECT_STATE.md`; do not touch them.
