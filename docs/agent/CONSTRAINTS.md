# Constraints

Hard rules for any CLI coding agent working on Sarthi. Each constraint is
backed by the repository's architecture and, in most cases, by tests that
will fail if you violate it.

## Architecture

1. **Sarthi Brain remains deterministic.** `brain/` never calls a model.
   The Brain must never import `hermes/` — the single sanctioned brain-side
   path into the LLM layer is the NLP fallback skill's
   `hermes.service.chat` import. (Locked by `tests/test_architecture_boundaries.py`.)
2. **Hermes handles complex/model-driven orchestration — as escalation only.**
   Do not make Hermes the default executor, do not wake it for simple
   commands, and never let it become a physical executor.
3. **One Hermes reasoning loop.** `hermes/agent.py::HermesAgent` is the only
   model-driven tool loop. Do not create a second loop, planner-loop, or
   parallel orchestration engine. The duplicate ToolPlanner loop was already
   removed (AD-02) — do not reintroduce the pattern.
4. **The validator is the only tool-call gate.** Model output must be parsed
   (`hermes/tool_planner.py::parse_tool_call`) and pass
   `hermes/validator.py` before dispatch through
   `hermes/tool_registry.py`. No shell, eval, exec, or arbitrary subprocess
   execution anywhere in Hermes or the tools.
5. **All OS interaction goes through the Hand.** Use
   `hands.local.get_desktop_hand()`; Windows-only imports stay exclusively
   inside `hands/desktop/`; `hands/` imports nothing from
   `brain`/`hermes`/`knowledge`/`skills` (locked by
   `tests/test_brain_hand_boundary.py`).
6. **Do not introduce LLM dependencies into deterministic Brain logic.**
   Deterministic-first is the core principle: if a known, validated
   capability path exists, it is used; Hermes escalates only.
7. **The Desktop client communicates with the backend only through the
   established HTTP boundary** (`Desktop/client/sarthi_client/backend.py`).
   No backend imports in the client (test-locked).

## Reuse

8. **Reuse existing skills/tools rather than creating parallel execution
   systems.** New Hermes tools delegate to existing skills/executor.
   New OS-level behaviour belongs in `hands/desktop/` backends, not ad-hoc
   pyautogui/psutil calls elsewhere. (Historical precedent: the ai_chain
   control-layer duplication is deferred debt, AD-12 — do not add more.)
9. **Do not add a second sandbox root, second conversation store, or second
   capability registry.** Sandbox paths resolve via
   `hermes.sandbox.resolve_sandbox_root` (AD-01); the two conversation
   tables are intentionally distinct (AD-09).

## Honesty & scope

10. **Do not represent planned functionality as implemented.** Label work
    IMPLEMENTED / PARTIAL / PLANNED. If a feature needs new infrastructure
    (auth, discovery, remote hands), say so instead of faking it.
11. **Preserve existing behaviour unless the active task explicitly changes
    it.** Behaviour-preserving refactors stay behaviour-preserving; do not
    bundle unrelated changes. Do not modify unrelated subsystems.
12. **Do not casually "fix" deferred items.** These are decided debts with
    recorded reasons (see `docs/dev/PROJECT_STATE.md`): ai_chain control
    layer (AD-12), `handled` vs `success` skill semantics (D-07),
    sandbox→knowledge promotion (AD-13), automation lifecycle (AD-14),
    unified observation contract (AD-15). Changing them needs an explicit
    task, not drive-by cleanup.
13. **Removal candidates stay in place** (`ai_chain/browser_automation.py`,
    `assistants/brain_assistant/analyzer.py`) — they carry unique test
    coverage / contract consumers (AD-06, AD-11).

## Process

14. **Run relevant tests after modifications.** The boundary suites
    (`test_architecture_boundaries.py`, `test_brain_hand_boundary.py`,
    `test_consolidation_routing.py`, `test_desktop_agent_ipc.py`) must pass
    after any structural change; run the full suite before finishing.
15. **Update documentation in the same change** when behaviour or
    architecture changes: the matching section in
    `docs/dev/ARCHITECTURE.md`, the state entry in
    `docs/dev/PROJECT_STATE.md`. Never leave stale architecture documented.
16. **The code is the source of truth.** If documentation and code disagree,
    verify against the code, then fix the documentation.
17. **Never commit**: `Backend/database/sarthi.db`, `.env`, `sandbox/`,
    `results/`, `ai_chain/calibration.json`, `Desktop/dist/`.
