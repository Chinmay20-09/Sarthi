# Task

> **STATUS: ACTIVE** — sprint started 2026-09-16. Two tasks this sprint.
> Context: read [CURRENT_CONTEXT.md](CURRENT_CONTEXT.md) first; obey
> [CONSTRAINTS.md](CONSTRAINTS.md). Permanent truth: `docs/dev/`.

---

# Task 1 — IPC hardening (authentication for the Desktop Agent boundary)

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
   "agent unreachable" (a dedicated error code such as
   `transport_unauthorized`) so the Brain can tell "refused" from "no one
   listening".
2. **Fail closed on non-loopback binds.** When no token is configured, the
   agent must refuse to bind to any non-loopback host (clear error message),
   so today's dev experience on `127.0.0.1` keeps working unchanged while a
   LAN bind without a secret becomes impossible.
3. **Zero new dependencies on the agent side.** The server deliberately uses
   the stdlib `http.server`; auth must not add a framework or third-party
   dependency there (stdlib hashing/`secrets`/`hmac` are fine;
   constant-time comparison required).
4. **Secret hygiene.** Token comes from config/env
   (`SARTHI_DESKTOP_AGENT_TOKEN`, following the existing
   `SARTHI_DESKTOP_AGENT_*` pattern in `Backend/config.py` +
   `Backend/.env.example`); never logged, never echoed in error messages or
   sandbox records.
5. **Pairing = minimum viable.** On first start with a generated token, the
   agent prints/writes the token for the user to copy to the Brain's `.env`.
   No PKI, no mTLS, no heavy handshake — document that this is a
   LAN/local-trust boundary improvement, not internet-grade security.
6. **Health/capabilities endpoints.** `GET /health` and `GET /capabilities`
   must not disclose configuration details to unauthenticated callers;
   either require the token or reduce the unauthenticated payload to a
   minimal liveness ack (implementer's choice, document it).
7. **Behaviour preservation.** `local` mode and the in-process `DesktopHand`
   path are byte-for-byte unchanged. The `Hand` interface (`hands/base.py`)
   gains no new members. The wire-format change is limited to the auth
   credential; existing request/response payloads are unchanged.
8. **Documentation in the same change:** the IPC section of
   `docs/dev/ARCHITECTURE.md`, the OPEN row in `docs/dev/PROJECT_STATE.md`,
   `docs/client/INSTALLATION.md` + `docs/client/FAQ.md` (LAN warning → token
   setup), `Backend/.env.example`, and the server's docstring security note.
9. **Stay cross-platform:** `hands/transport.py` and `hands/remote.py` remain
   importable on Linux/Android (no Windows-only imports, no heavy imports).

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
  Android/remote Hands) — do not touch them.

---

# Task 2 — Terminal capability: `cd`, `echo`, `create`, `write`

## Objective

Give Sarthi terminal-style file commands — `cd`, `echo`, `create`, `write` —
so the deterministic pipeline (and Hermes, for task-shaped instructions) can
actually manipulate files instead of only reasoning about them. This closes
part of the recorded gap: "Sarthi has no filesystem/file tool yet, so Hermes
can reason about such a task but not execute it" (`docs/dev/PROJECT_STATE.md`,
AD-04 follow-up).

**Design decision (fixed):** these four commands are implemented as
**structured, allow-listed `DesktopHand` actions** (pathlib/os only) — NOT by
spawning `cmd.exe`/a shell. `subprocess` must not be introduced. The declared
`SHELL` capability in `PLANNED_CAPABILITIES` (arbitrary allow-listed shell
commands) **stays planned** — this task does not promote it.

## Requirements

1. **New `TERMINAL` capability** in `Backend/hands/desktop/capabilities.py`
   with exactly these actions (strict argument specs, same format as the
   existing capabilities):
   - `cd` — `{path: (required, str)}`: resolve the path against the
     filesystem backend's current working directory, verify it is under an
     allowed root (existing `resolve_scoped`), and set it as the cwd. The
     result returns the resolved absolute path (serves as `pwd`).
   - `echo` — `{text: (required, str), path: (optional, None)}`: return the
     text as the result payload; when `path` is given, write the text
     (+ newline) to that file instead (scoped, size-capped like
     `write_file`).
   - `create` — `{path: (required, str), type: (choices, ["file", "directory"])}`:
     create an empty file or a directory (one level, scoped; error when it
     already exists — a structured result, not a raise).
   - `write` — file writing already exists as the `write_file` action
     (`FILESYSTEM_WRITE`). Do NOT duplicate it on the hand; the terminal
     skill/tool layer maps `write <content> to <path>` onto the existing
     `write_file` action, resolving relative paths against the tracked cwd.
2. **cwd state lives in `FilesystemBackend`** (`Backend/hands/desktop/filesystem.py`):
   starts at the first allowed root (default: user home), `cd` updates it,
   relative paths in `create`/`echo`/`write_file` resolve against it. Every
   path still passes `resolve_scoped` — traversal via `..` stays impossible.
   No new env vars (allowed roots default unchanged).
3. **New `terminal` skill** (`Backend/skills/terminal/{manifest.json,main.py}`,
   manifest-discovered — skill count goes 10 → 11) so the deterministic
   pipeline routes commands like:
   - `cd documents` / `cd <path>`
   - `echo hello` (and `echo hello to notes.txt`)
   - `create file notes.txt` / `create directory projects`
   - `write hello world to notes.txt` / `create file notes.txt with content …`
   Follow the standard skill contract: `execute(intent) -> dict` plain
   result, `handled: True` semantics, honour `get_test_mode()` (dry-run
   returns the plan, touches nothing).
4. **One Hermes tool** (`terminal`) registered in
   `register_default_tools` (`hermes/tools/__init__.py`), delegating to the
   terminal skill — the tool bridge pattern. It exposes ONLY the four
   structured operations; constraint #4 (no shell/eval/subprocess in Hermes
   or tools) applies unchanged. This is what lets task-shaped instructions
   ("find … and rename …"-class work) finally execute file steps.
5. **Security invariants (all test-locked):**
   - every op scoped to `allowed_roots`; outside-root paths → structured
     failure (`FilesystemScopeError` handled, never raised past the hand);
   - no `subprocess`/`os.system`/`eval` anywhere in the new code;
   - unknown actions/arguments rejected by the existing spec validation;
   - results are `DesktopResult`-shaped dicts; failures are observations.
6. **IPC comes free.** Actions flow through the hand's registry, so remote
   mode (`SARTHI_DESKTOP_AGENT_MODE=remote`) and `desktop_agent.py
   --capabilities` pick them up with no extra work — verify the capability
   report lists TERMINAL.
7. **Docs in the same change:** `docs/dev/ARCHITECTURE.md` (capability
   description, skills table 10 → 11, tools table, `PLANNED_CAPABILITIES`
   note that SHELL remains planned), `docs/dev/PROJECT_STATE.md` (file
   capability gap narrowed: state exactly what IS now possible — cd/echo/
   create/write — and that broader file ops remain open), `docs/client/USAGE.md`
   (new user commands + examples), `docs/dev/TESTING.md` (what the new tests
   cover).

## Acceptance Criteria

- [ ] End-to-end via `/command`: `cd documents` → `create file notes.txt` →
      `write hello world to notes.txt` → `echo done` all succeed in order,
      with the cwd carried between steps; the file exists with the content.
- [ ] `cd` outside allowed roots, `create`/`echo`/`write` outside roots, and
      unknown/extra arguments all return structured failures; nothing
      executes outside the scope.
- [ ] No `subprocess`/`os.system`/`eval` added anywhere (repo-wide grep
      clean in the touched packages).
- [ ] `python Backend/desktop_agent.py --capabilities` lists TERMINAL with
      its four actions; remote mode can execute them (fake-transport test).
- [ ] Hermes tool `terminal` passes the validator gate and delegates to the
      skill (fake-provider test, same pattern as `test_hermes_tools.py`).
- [ ] Test-mode (dry-run) returns plans without touching the filesystem.
- [ ] Skill count is 11 and every doc that says "10 skills" is updated;
      `docs/dev/PROJECT_STATE.md` no longer claims "no filesystem/file tool"
      without qualification.
- [ ] Full pytest suite passes with new tests additive
      (baseline: **1127 passed** + new).
- [ ] `ruff check Backend tests` clean; no new runtime dependencies.

## Relevant Files

| Area | Files |
| --- | --- |
| Capability registration | `Backend/hands/desktop/capabilities.py` (add TERMINAL; SHELL stays in PLANNED_CAPABILITIES) |
| Backend ops + cwd tracking | `Backend/hands/desktop/filesystem.py`, `Backend/hands/desktop/hand.py` (dispatch entry if needed) |
| New skill | `Backend/skills/terminal/manifest.json`, `Backend/skills/terminal/main.py` |
| New Hermes tool | `Backend/hermes/tools/terminal.py`, `Backend/hermes/tools/__init__.py` |
| Interpreter (command shapes) | `Backend/brain/interpreter.py` (only if a new intent/action form is needed — prefer reusing existing shapes) |
| Tests | `tests/test_desktop_hand.py`, `tests/test_terminal_skill.py` (new), `tests/test_hermes_tools.py` |
| Docs | `docs/dev/ARCHITECTURE.md`, `docs/dev/PROJECT_STATE.md`, `docs/client/USAGE.md`, `docs/dev/TESTING.md` |

## Non-Goals

- Arbitrary shell command execution — `SHELL` stays in `PLANNED_CAPABILITIES`.
- Additional commands (rm/mv/cp/ls/dir/cat/run/pip/…) — only cd, echo,
  create, write this sprint; extend the allow-list later, one review each.
- Multi-session or per-user cwd persistence (cwd is process-lifetime state).
- Changes to the `Hand` interface members or the wire payload schema.
- Any change to `local`/`remote` mode selection, the IPC transport, or the
  deferred items (AD-12/13/14/15).
