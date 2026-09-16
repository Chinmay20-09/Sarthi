# Current context

> Temporary sprint context — replaced after each sprint. Permanent truth:
> [`docs/dev/ARCHITECTURE.md`](../dev/ARCHITECTURE.md) and
> [`docs/dev/PROJECT_STATE.md`](../dev/PROJECT_STATE.md).
>
> **Active sprint (2026-09-16): two tasks** — see [TASK.md](TASK.md):
> (1) IPC hardening (token auth for the Desktop Agent boundary),
> (2) Terminal capability (`cd`, `echo`, `create`, `write` as structured
> hand actions — no subprocess).

## Architecture in one screen

- **Brain** (`Backend/brain/`) — deterministic orchestrator:
  interpreter → pass-through planner → fuzzy resolver → executor over
  registered skills. Never imports Hermes.
- **Hermes** (`Backend/hermes/`) — complex/model-driven orchestrator: ONE
  bounded loop (`agent.py`, default 3 iterations), ONE tool-call gate
  (`validator.py`), 11 whitelisted tools that delegate to existing skills.
  Escalation only — reached via the complexity router (after a failed
  deterministic run) or the task-shaped gate (before execution when the only
  reading is a web search).
- **Hands** (`Backend/hands/`) — the only OS execution layer. `Hand` interface
  (`base.py`); local `DesktopHand` (Windows) selected by
  `hands/local.py::get_desktop_hand()`; `RemoteDesktopHand` over the IPC
  transport (`remote.py` + `transport.py`) when
  `SARTHI_DESKTOP_AGENT_MODE=remote`. Import lock: `hands/` never imports
  brain/hermes/knowledge/skills.
- **Skills** (`Backend/skills/`) — 11 manifest-discovered skills (terminal
  added 2026-09-16); plain-dict
  results; fallback NLP skill registered LAST.
- **Knowledge** (`Backend/knowledge/`) — apps/websites entity store + fuzzy
  resolver. **Memory** — `/remember` facts, two conversation tables (UI
  transcript vs model context — intentionally separate), Hermes sandbox
  (canonical root `Backend/sandbox`, cwd-independent).
- **API** (`Backend/api.py`) — 46 routes; the Desktop client talks HTTP only
  (test-locked boundary).

## Implementation state relevant to now

- As of 2026-09-16 the full suite is **1172 tests / 50 collected files, all
  passing** (~10 min). 56 `test_*.py` files total; 6 are manual smoke
  scripts with no collected tests. The terminal capability suite
  (`tests/test_terminal_capability.py`, 45 tests) is the newest file.
- The **Brain ↔ Desktop Agent IPC** landed in commit `0108235` (2026-09-16):
  `hands/local.py`, `hands/remote.py`, `hands/transport.py`,
  `desktop_agent.py --server`, tests in `tests/test_desktop_agent_ipc.py`.
  Mode default is `local` — in-process behaviour is unchanged.
- `Backend/hermes/config/loader.py` has an **uncommitted** working-tree fix:
  the `hermes.sandbox` import is deferred into `load()` to break an import
  cycle (sandbox → providers → config → sandbox) that crashed processes
  importing `hermes.sandbox` first (e.g. `scripts/clean_sandbox.py`).
- Every pytest file announces its result aloud via `tests/conftest.py`
  (`SARTHI_TEST_VOICE=0` silences it).

## Relevant files (quick map)

| Area | Files |
| --- | --- |
| Routing/escalation | `Backend/brain/engine.py`, `Backend/api.py`, `Backend/hermes/router.py`, `Backend/hermes/agent.py` |
| Tool bridge | `Backend/hermes/tool_registry.py`, `Backend/hermes/validator.py`, `Backend/hermes/tools/` |
| Hands / IPC | `Backend/hands/base.py`, `Backend/hands/local.py`, `Backend/hands/remote.py`, `Backend/hands/transport.py`, `Backend/desktop_agent.py` |
| Skills | `Backend/skills/registry.py`, `Backend/skills/<id>/{manifest.json,main.py}` |
| Knowledge/memory | `Backend/knowledge/manager.py`, `Backend/knowledge/entity_resolver.py`, `Backend/knowledge/memory.py` |
| Database | `Backend/database/manager.py`, `Backend/database/models.py` |
| Boundary locks (tests) | `tests/test_architecture_boundaries.py`, `tests/test_brain_hand_boundary.py`, `tests/test_consolidation_routing.py`, `tests/test_desktop_agent_ipc.py` |

## Current known blockers / open issues

- File capability in the brain pipeline: task-shaped instructions can now
  execute terminal file steps — Task 2 landed cd/echo/create/write as the
  TERMINAL capability + terminal skill + Hermes tool (validated: 45-test
  suite + full run 1172 passed). Broader file ops (move/copy/delete/search)
  remain open (AD-04 residue).
- IPC boundary has no authentication/pairing/transport security — documented
  as LAN-local only — **being addressed this sprint** (Task 1: token auth);
  transport encryption remains open after it.
- Deferred (do not "fix" casually): ai_chain's private control layer (AD-12),
  skill `handled` vs `success` semantics (D-07), `sarthi.bat`/`config.py`
  port duplication (D-10), sandbox→knowledge promotion (AD-13), automation
  lifecycle (AD-14), unified observation contract (AD-15).
- Removal candidates (kept deliberately): `ai_chain/browser_automation.py`
  (v1.7, test-only), `skills/automation_engine/assistants/brain_assistant/analyzer.py`.
