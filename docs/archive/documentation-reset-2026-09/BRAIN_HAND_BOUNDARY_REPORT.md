# Brain/Hand boundary report — 2026-09-15

Companion to [ARCHITECTURE.md](ARCHITECTURE.md) ("Backend = Brain, Desktop = Hand")
and [ARCHITECTURAL_DECISIONS.md](ARCHITECTURAL_DECISIONS.md) (AD-16). This
report records what was inspected, what changed, and what is deliberately
left for the future.

## 1. Current architecture (observed, before this change)

```
                        SARTHI
                          │
          ┌───────────────┴───────────────┐
    BACKEND / BRAIN                  DESKTOP / HAND
    Hermes, memory, knowledge,       input, processes, filesystem,
    retrieval, routing, planning     windows, browser backends
          │                                 │
          └──────── in-process calls ───────┘
```

The boundary already existed in substance after the 2026-09-14
consolidation (AD-01–AD-11): the Brain never touched the OS directly, and
`hands/desktop/` held the only input/process/filesystem backends. What was
missing was a *named contract* and an *enforced import lock*.

## 2. Target architecture

```
USER/CLIENT → NETWORK → BACKEND/BRAIN → Sarthi Core → Interpreter
  → Complexity Router → Deterministic OR Hermes → validated action request
  → NETWORK → DESKTOP/HAND → Execute → Observe
  → NETWORK → BACKEND/BRAIN → next decision / final result
```

The Backend is the authority; the Desktop is an execution/observation
endpoint. Current local mode (same machine, in-process calls) and future
network mode (protocol to a remote device) must both fit the same Brain
code.

## 3. Existing execution path discovered

Traced end-to-end (see [RUNTIME_FLOW.md](RUNTIME_FLOW.md)):

1. `POST /command` (`api.py`) — mode/conversation checks, task-shaped gate (AD-04).
2. `BrainEngine.process` → interpreter → planner (pass-through) → resolver →
   `BrainExecutor` → built-in handlers / skills.
3. On failure or hermes routing → complexity router (heuristics, no model) →
   `HermesAgent` (the single bounded loop) → validator → `ToolRegistry` → tools.
4. OS-touching tools and skills delegate to `hands/desktop/`:
   - `app_launcher` → `hands.desktop.processes` (`launch_process`/`startfile`)
   - executor `close` handler → `get_desktop_hand().execute("close_application", pid=...)`
   - `hermes/tools/open_app.py` → `AppLauncherSkill`; `close_app.py` → `BrainExecutor`
5. `desktop_agent.py` is the standalone hand seam (capabilities/self-test/exec CLI; no IPC).

Verified by grep during inspection: zero `subprocess`/`os.system` under
`hermes/`; pyautogui/keyboard/win32 imports exist **only** under
`hands/desktop/` (plus the ai_chain control layer, adjudicated as AD-12).
`Backend/actions/` and `Backend/tools/` do not exist — the tool bridge is
`hermes/tools/`.

## 4. Boundary introduced

- **`Backend/hands/base.py`** — `Hand`, a `runtime_checkable` structural
  Protocol with exactly the members `DesktopHand` already had:
  `execute(action, target, **kwargs) -> dict`, `capabilities()`,
  `find_application_process(exe_name)`. Docstring states the responsibility
  split: the Brain issues validated actions; the hand performs and observes,
  never reasons.
- **`Backend/hands/desktop/__init__.py`** — re-exports `Hand` and asserts
  `DesktopHand` conforms at import.
- **`Backend/brain/executor.py`** — the close handler now programs against
  the interface (`hand: Hand = get_desktop_hand()`); typing-only, behaviour
  unchanged.
- **Import lock** (test-enforced): `hands/` must not import `brain`,
  `hermes`, `knowledge`, `skills` or `api`.

`LocalHand` in the brief's diagram is `DesktopHand` (kept — one abstraction,
no rename). `RemoteDesktopHand` is *not* implemented; it would satisfy the
same contract over a network protocol.

## 5. Files changed

| File | Change |
| --- | --- |
| `Backend/hands/base.py` | **added** — the `Hand` interface |
| `Backend/hands/desktop/__init__.py` | re-export `Hand` + conformance assert, docstring updated |
| `Backend/brain/executor.py` | close handler annotated against `Hand`; docstring wording |
| `tests/test_brain_hand_boundary.py` | **added** — 18 contract/boundary tests |
| `docs/ARCHITECTURE.md` | "Backend = Brain, Desktop = Hand" section, topology diagram, divergences noted |
| `docs/ARCHITECTURAL_DECISIONS.md` | AD-16 added (ACCEPTED) |
| `docs/BRAIN_HAND_BOUNDARY_REPORT.md` | **added** — this report |

## 6. Files intentionally untouched

`Backend/api.py` (no new endpoint), `hermes/` entirely (agent, validator,
tool bridge, registry), `skills/` (including `app_launcher`,
`browser`, `browser_awareness`, `automation_engine`), `hands/desktop/*`
backends (input/processes/filesystem/windows/browser), `sandbox/`,
`knowledge/`, `database/`, `Desktop/client/`, `desktop_agent.py`.
Browser automation was not rewritten; the AI chain control layer stays as
AD-12 deferred it.

## 7. Tests added

`tests/test_brain_hand_boundary.py` (18 tests) proves the brief's §13 list:

1–3. Protocol conformance; the executor issues actions through `Hand`; a
     recording hand proves the Brain sends only explicit authorized actions
     (explicit pid) and receives the observation back (`result["closed"]`).
4. AST lock: `hands/` imports none of `brain|hermes|knowledge|skills|api`;
   source lock: no LLM/server/tool-planner references under `hands/`.
5–6. "open chrome" runs the deterministic pipeline (Hermes never woken,
     monkeypatched); compound research commands score `hermes` on the
     router; task-shaped gate flags preserved.
7. Hermes tools contain no direct OS primitives (`subprocess`,
   `os.system`, `pyautogui`, `psutil`, `startfile`) — they delegate to
   skills/executor only.
8. Hand results are structured `DesktopResult`-shaped dicts; expected
   failures return instead of raising.
9. `class ToolPlanner` remains absent; exactly one `DesktopHand`
   implementation exists and none of the banned duplicate names
   (`desktop_executor.py`, `hand_manager.py`, `device_agent.py`, …) exist.
10. Full existing suite passes (below).

## 8. Test results

- New boundary tests: **18/18 pass**.
- Full suite: **1077 tests, all passing** (1059 before + 18 new).
- `ruff check Backend tests`: clean.
- No behavior change: all pre-existing tests pass unmodified.

## 9. Future RemoteDesktopHand requirements (not implemented)

The interface is the prepared ground only. A real network hand needs:
authenticated/authorized `request → validation → execution → result`
semantics (the Backend must remain the sole authority — no arbitrary
clients), device pairing/registration, transport security, operation
timeouts/retries, and an observation payload contract. None of this exists
today and none was added speculatively.

## 10. Remaining architectural work

- RemoteDesktopHand + protocol (§9) — future.
- AD-12: point `ai_chain/control.py` at `hands/desktop/input.py` (needs a
  characterization harness first).
- AD-15: unify execution-observation shapes (`ToolResult` vs `DesktopResult`
  vs `InspectionResult`/`StepOutcome`).
- Two `webbrowser.open` call sites outside the hand (`skills/browser/main.py`,
  `hermes/tools/open_website.py`) — validated capability surfaces, not a
  second hand; candidates to route through `open_url` later.

## 11. Divergences discovered during implementation

- The brief's assumed `Backend/actions/` and `Backend/tools/` directories do
  not exist; the tool bridge is `hermes/tools/` and execution dispatch is
  `brain/executor.py` + skills. No action needed — recorded here so the
  mapping is explicit.
- `desktop_agent.py` already provided the standalone-hand seam; the future
  IPC work should extend it rather than add a new agent process.
- The single pre-existing test failure during development was in the new
  test itself (wrong monkeypatch target + wrong result-shape assertion),
  not in production code.

**Final principle, now enforced:** Sarthi thinks through the Backend.
Sarthi acts through the Desktop Hand. Backend = Brain. Desktop = Hand.
