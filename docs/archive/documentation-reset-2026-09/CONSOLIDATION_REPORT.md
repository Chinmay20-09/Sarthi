# Consolidation report — 2026-09-14

Final report of the architectural consolidation pass. Method, evidence and
per-decision reasoning live in [CONSOLIDATION_PLAN.md](CONSOLIDATION_PLAN.md)
(observations) and [ARCHITECTURAL_DECISIONS.md](ARCHITECTURAL_DECISIONS.md)
(decisions). This document records what changed and what is left.

## Executive summary

Sarthi was not rewritten. The pass made four structural changes and closed the
audit findings that were real, while explicitly deferring the ones that needed
a product decision:

1. **One canonical sandbox root.** A relative `HERMES_SANDBOX_PATH` now
   resolves against the backend root instead of the current working
   directory, so the two live task stores (`Backend/sandbox` with 34 queries
   and `sandbox/` with 4) can no longer both be "the" sandbox.
2. **One Hermes reasoning loop.** The duplicate model/tool loop
   (`ToolPlanner`) was deleted; `HermesOrchestrator.process` now delegates to
   `HermesAgent`, so `/command`'s complex fallback and `POST /hermes/chat`
   share retrieval, tool validation, retry bounds and sandbox persistence.
3. **Complex work reaches Hermes before it is executed literally.** A
   task-shaped sentence whose only deterministic reading is a web search
   (`"Find all assignment PDFs and rename them according to subject"`) is
   handed to Hermes before anything runs, instead of opening a browser for the
   sentence's own words.
4. **Unreachable code removed.** The automation engine's second orchestration
   pipeline, the non-functional `analyze` command and the unused `pystray`
   dependency are gone.

Everything the brief called out as working and conceptually aligned — the
deterministic pipeline, the skill system, the tool bridge, the provider
abstraction, memory/knowledge, hands, the API, the clients — was preserved
untouched. Several audit findings turned out to be already fixed or not
reproducible in the current source; those were closed with tests rather than
changed.

## Before

```text
/command ──► interpreter → planner(pass-through) → resolver → executor → skills
             │
             └─ on failure: router(heuristics) → HermesAgent (retrieval +
                validator + sandbox + fast path)
/UI chat ──► /command, then (client-side fallback) POST /hermes/chat
             └─ HermesOrchestrator.process → ToolPlanner  ← SECOND loop,
                no validator, no retrieval, own cap of 5
sandbox root = relative "sandbox" → Backend/sandbox OR ./sandbox per cwd
```

- 4 "agent" components, 2 of them model-driven tool loops.
- 1021 tests collected in 53 files.
- Documented divergences: 12 (DIVERGENCE.md), 8 duplications, 9 dead items,
  58 divergence-matrix rows.

## After

```text
/command ──► task-shaped instruction? ──yes──► HermesAgent (no fast path)
             │no
             └─► interpreter → planner → resolver → executor → skills
                 │
                 └─ on failure / hermes routing: router → HermesAgent
/UI chat ──► /command, then POST /hermes/chat → HermesOrchestrator.process
             └─ HermesAgent   ← the ONE model/tool loop
sandbox root = Backend/sandbox (absolute, cwd-independent)
```

- Hermes = one bounded loop (`hermes/agent.py`); `hermes/tool_planner.py` is
  now only the tool-call protocol (prompt builders + parser).
- 3 "agent" components: the Hermes loop, BrainAssistant (assistant
  generation), the browser-awareness manager loop.
- 1059 tests collected in 54 files, all passing.
- Hermes may request; only Sarthi executes. AI chain remains a capability
  reached through the skill walk, not a peer brain.

## Components removed

| Path | Reason | Replacement | Evidence |
| ---- | ------ | ----------- | -------- |
| `hermes/tool_planner.py::ToolPlanner` (+ `MAX_TOOL_CALLS_PER_TASK`) | Second model/tool loop over the same registry, without validator or retrieval | `hermes/agent.py::HermesAgent` (single loop) | Only callers were `orchestrator.process` and 3 test files; both production endpoints now share one loop |
| `skills/automation_engine/events.py` | `AutomationEvent` / `SkillTestPassedEvent` scaffolding | none (no capability) | No callers, no test imports, no config, no dynamic loading |
| `skills/automation_engine/context.py` | `ProjectScanner` only built the unreachable `AutomationContext` | none | Same |
| `skills/automation_engine/preview.py` | `PreviewGenerator.show()` printed a placeholder | none | Same |
| `contracts.py::AutomationEvent`, `contracts.py::AutomationContext` | Only produced/consumed by the removed pipeline | none | Repo-wide grep: zero remaining references |
| `AutomationEngine.run/_run_assistants/_request_approval/_apply_requests/_validate` | Unreachable event pipeline (approval loop + placeholders) | `register_assistant` / `run_assistant` registry | `skill.py` never called `run` |
| `AutomationSkill._handle_analyze` + the `analyze` branch | Returned a fixed empty `capabilities` list | none | Not a capability; nothing consumed it |
| `pystray` (dependency) | Declared, never imported | none | Zero imports under `Backend/`, `Desktop/`, `tests/` |

## Components merged

| Original | Surviving component | Responsibility | Migration |
| -------- | ------------------- | -------------- | --------- |
| `HermesAgent` + `HermesOrchestrator.process`/`ToolPlanner` | `HermesAgent` | One bounded reasoning loop: retrieval → model → validated tool → sandbox | `orchestrator.process` delegates; `hermes/routes.py` and `hermes/main.py` unchanged; tests re-pointed at the canonical loop |
| cwd-relative sandbox resolution in 4 call sites | `hermes.sandbox.resolve_sandbox_root` (used by `TaskSandbox` and `ConfigLoader`) | One absolute sandbox root | Call sites unchanged (they pass the configured path); `test_fallback_integration` moved to an absolute `tmp_path` |
| Router verdict after failure only | Router consulted pre-execution for task-shaped instructions | Complexity decision owns the request before execution | New gate in `api._process_command_text` + `hermes.router.looks_like_task_instruction` |

## Components preserved (and why)

- **Deterministic pipeline** (`brain/`) — working, tested, conceptually
  aligned; the interpreter/planner/executor contract is Sarthi's execution
  authority. Only the API-level gate in front of it changed.
- **Tool bridge** (`hermes/tool_registry.py`, `hermes/tools/*`) — already
  exactly P8: Hermes-facing adapters that delegate to existing skills; no
  shell/code execution. Verified by grep: zero `subprocess`/`os.system` under
  `hermes/`.
- **Validator** (`hermes/validator.py`) — became the *only* tool-call gate once
  the duplicate loop went.
- **Provider abstraction** (`hermes/providers/*`) — P6 already satisfied:
  provider/model is config-selected, and `service.py` imports no concrete
  adapter.
- **Skills** (10) — manifest-registered capabilities; unchanged.
- **Browser stacks** — `skills/browser_awareness/` (arbitrary sites) and
  `ai_chain/dom.py` (AI sites) serve different consumers and are both tested;
  coordinate scanning is already opt-in (AD-11).
- **Hands** — `hands/desktop/` is the sanctioned validated execution boundary
  used by the close handler, the app launcher and the standalone agent CLI.
- **Memory / Knowledge / Sandbox storage** — no database or schema change was
  needed (AD-09, AD-10).
- **API, dashboard, desktop client, CLI, speech, connectors, events** —
  untouched; the only API-visible change is the routing of task-shaped
  requests to Hermes (same envelope, same schema).

## Hermes changes

- `hermes/agent.py`: `run()` accepts `history`, `memory`, `task_id`,
  `task_type` (so callers keep their identity and context; no capability
  loss). `fast_path=False` disables the deterministic short-circuit.
  `DEFAULT_MAX_ITERATIONS` is 3. The sandbox record uses the caller's task id
  when given.
- `hermes/orchestrator.py`: `process()` delegates to the agent and maps the
  result to `ProviderResponse`; `chat()` unchanged (plain chat, no tools,
  still sandbox-recorded); `_get_agent()` builds the agent once with
  `fast_path=False`.
- `hermes/tool_planner.py`: loop removed; protocol (decision/follow-up prompts
  + `parse_tool_call`) kept as the shared contract.
- `hermes/service.py`: `run_task(..., allow_fast_path=True)`; default
  iteration bound 3.
- `hermes/router.py`: new `looks_like_task_instruction` + `task_instruction`
  signal; verdict reasons no longer report the generic shape signal.

## AI Chain changes

None in behaviour. The chain remains a **capability** invoked only through the
brain's skill walk (`chain` intent → `AutomationSkill._handle_chain` →
`run_ai_chain`), test-mode aware, with the hands-off countdown and the
`Ctrl+Alt+X` abort. No bypass of Sarthi's authorization was found (no CLI or
shell execution path exists in the chain or in Hermes). The chain's private
control layer and the v1.7 `browser_automation.py` engine are recorded as
deferred (AD-12) and candidate-for-removal respectively.

## Browser changes

None in behaviour. Verified that the semantic-first requirement is already the
default: DOM affordance matching (`aria-label="Copy"`, per-site registered Copy
button) is primary, the multi-point coordinate scan is disabled unless
`AI_CHAIN_COORDINATE_SCAN=1`, and the `Ctrl+A`/`Ctrl+C` page copy is only the
fallback for unregistered sites. New tests lock all four properties without
starting a browser.

## Memory / Knowledge changes

None in storage. The boundary is now explicit: Memory = user facts and
preferences (`knowledge_memory`, `/remember`, personal-context/config
skills); Knowledge = environment/operational entities
(`applications.json`, `websites.json`, skills/tools capabilities); the UI
transcript (`chat_messages`) and the model's session context
(`conversation_messages`) are two states of one exchange, not duplicates.
No tables were merged and no migration was required.

## Sandbox changes

`hermes/sandbox.py` owns the one resolver (`resolve_sandbox_root`,
`BACKEND_ROOT`, `DEFAULT_SANDBOX_ROOT`); `TaskSandbox()` defaults to it and
`ConfigLoader` resolves `HERMES_SANDBOX_PATH` through it. Canonical root:
`Backend/sandbox` (where `sarthi.bat`, `clean_sandbox.py` and the 34-query
history already are). The stray repo-root `sandbox/` (gitignored) was left in
place by explicit user decision and simply stops receiving new records.

## Task ownership

```text
USER → SARTHI (/command: modes → interpreter → planner → resolver → executor)
                       │ simple/deterministic: execute, done
                       └ task-shaped or failed + router says complex:
                            HERMES (retrieve → model → one validated tool → repeat, ≤3)
                                │ requests a capability
                            SARTHI executes it (skill / hand) and records the run
                                └ result → HERMES decides: finish / retry (bounded) / answer
Sarthi owns: lifecycle, current step, retry mechanics, permissions, memory,
knowledge, sandbox, completion. Hermes proposes the next step; the user
remains the authority for risky or ambiguous actions (the validator refuses
malformed/unregistered calls, and refusals are fed back exactly once).
```

## Tests

| Metric | Before | After |
| ------ | ------ | ----- |
| Collected | 1021 | 1059 |
| Files | 53 | 54 |
| Failures | 0 | 0 |
| Skipped | 0 | 0 |
| New tests | 38 (`tests/test_consolidation_routing.py`) | |
| Deleted tests | 0 — every test that constructed the removed loop was migrated to `HermesAgent` with the same fakes and assertions | |
| Modified tests | `test_tool_bridge.py`, `test_provider_abstraction.py`, `test_conversation_history.py`, `test_sandbox_query_index.py`, `test_fallback_integration.py` | |

Verification run: `python -m pytest` → **1059 passed** in 283 s.
`ruff check` clean on every touched file (2 pre-existing import-order findings
remain in `Backend/brain/engine.py` and `Backend/brain/executor.py`, which
this pass did not touch). `mypy` could not run in this environment:
it aborts on `.venv/Lib/site-packages/numpy/__init__.pyi:737` ("Type statement
is only supported in Python 3.12 and greater") for *any* target, including
untouched modules — a pre-existing toolchain/python-target mismatch, reported
rather than hidden.

Behavioural characterization added for: routing (simple vs complex), chain
intent collision (both directions), the task-shaped escalation gate, the
single-loop invariants, sandbox resolution from both launch directories, and
browser semantic targeting. No test was weakened to make the refactor pass.

## Remaining divergence

Deliberately unresolved, with reasons in `ARCHITECTURAL_DECISIONS.md`:

| Item | Status | Why |
| ---- | ------ | --- |
| AI chain's own control layer duplicates `hands/desktop/input.py` (DM-049/P9) | DEFERRED | Real runs are untested (dry-run only); re-pointing them is a behaviour-risk change needing its own harness (AD-12) |
| Sandbox → Knowledge promotion (DM-038/DM-045) | DEFERRED | Needs a promotion rule and a user confirmation boundary (AD-13) |
| Automation as a trigger-based Sarthi-owned lifecycle (DM-052–DM-054) | DEFERRED | Requires task persistence + trigger ownership decisions (AD-14) |
| Unified execution-observation contract (DM-050) | DEFERRED | Cross-cutting change across hands + both browser stacks; the Hermes-facing view is already normalized (AD-15) |
| Two browser DOM readers (DM-031) | DEFERRED | Both working and tested; different consumers (AD-11) |
| `ai_chain/browser_automation.py` v1.7 engine | CANDIDATE | Production-dead but the only place its DOM resolver paths are tested |
| `assistants/brain_assistant/analyzer.py` (+ `ProjectState`/`ChangeRequest`/`AssistantResponse`) | CANDIDATE | Unreachable, but it is the only consumer of the assistant-response contract |
| Skill `handled` vs `success` semantics (D-07) | DEFER | Unchanged; inconsistent across skills, needs a per-skill audit |
| `sarthi.bat` vs `config.py` bind address (D-10) | DEFER | Two sources must stay in sync manually; a launcher change is cosmetic |
| File capability for P4's "deterministic discovery first" | DEFERRED (feature) | Sarthi has no filesystem/file tool; Hermes can reason about such tasks but not execute them (AD-04) |

## Risks

- **Router-gated escalation (AD-04)** is the only change that can override a
  successful deterministic result. It is narrow (single `search` intent +
  task-instruction shape) and covered by tests, but a *legitimate* long search
  query containing a task verb may now be answered by Hermes instead of a
  browser tab. Reverting is a one-line gate removal.
- **`/hermes/chat` behaviour change (AD-03)**: it now performs retrieval and
  enforces the validator, and a refusal costs one extra model turn. Responses
  are otherwise equivalent; the schema is unchanged.
- **Trace shape in the sandbox** for `/hermes/chat` records the agent's steps
  (`retrieval`/`model`/`validation`/`tool_result`) instead of `decision`. The
  dashboard renders steps generically; any external consumer keying on the old
  step name would need updating.
- **Sandbox on a fresh machine**: the canonical root is now always
  `Backend/sandbox`, so a deployment that previously relied on running from the
  repo root will look at a different directory (the old root store is not
  deleted, just no longer used).
- **`mypy` is unusable in this environment**, so static typing was not verified
  beyond ruff; this is pre-existing and unrelated to the changes.
