# Divergence (observed + status)

Architectural inconsistencies found during the forensic audit, with the status
after the 2026-09-14 consolidation pass. **No row was removed** — the audit
trail is preserved.

Status legend:

- **RESOLVED** — the implementation was changed and the behaviour is locked by tests.
- **INTENTIONAL** — two different things that were mistaken for duplication;
  the boundary is now documented.
- **DEFERRED** — real, understood, deliberately not changed in this pass
  (reason recorded in [ARCHITECTURAL_DECISIONS.md](ARCHITECTURAL_DECISIONS.md)).
- **NOT REPRODUCIBLE** — could not be reproduced in the current source; locked
  by tests in both directions so it cannot silently return.

| ID | Area | Component A | Component B | Conflict | Evidence | Severity | Status |
| -- | ---- | ----------- | ----------- | -------- | -------- | -------- | ------ |
| D-01 | Agent loops | HermesAgent (`hermes/agent.py`) — production complex-task loop | HermesOrchestrator + ToolPlanner (`orchestrator.py`, `tool_planner.py`) — separate decision loop | Two model-driven tool loops over the same ToolRegistry. The /command fallback path uses HermesAgent; `POST /hermes/chat` and `hermes/main.py` use the orchestrator loop. Different iteration caps (config vs MAX_TOOL_CALLS_PER_TASK=5), different prompt builders, different validation (validator gate vs ToolPlanner's own). | api.py:374-404 vs hermes/routes.py:275; both import tool_registry | HIGH | **RESOLVED** (AD-02/AD-03) |
| D-02 | Complexity decision | Router verdict (`hermes/router.py`) — "complex" | Actual execution — deterministic pipeline first | A "complex" verdict never skips the fast path: api.py only consults the router AFTER a failed deterministic run, and HermesAgent re-runs the fast path again. The router's verdict is a filter, not a decision; its reason strings can mislead (e.g. `simple_action_word` appears as reason for a hermes route). | api.py:374; agent.py:_try_fast_path; router.py:325-329 | MEDIUM | **RESOLVED** (AD-04: pre-execution gate for task-shaped instructions; reasons now report the specific signal) |
| D-03 | Chain defaults | `parse_chain_command` defaults (chatgpt→gemini) | User intent | Any chain-shaped command without "from X to Y" silently runs ChatGPT→Gemini. Sandbox evidence: "Open Google, search for \"OpenAI\", copy the URL..." executed as an ai_chain with default AIs (task_afec33) — a browser task misinterpreted as an AI chain. | ai_chain/parsing.py:36-77; sandbox/index.json key 'open google, search for \"openai\"...' | HIGH | **NOT REPRODUCIBLE** for the documented query (AD-07); the `/chain` default itself is **INTENTIONAL** (AD-08) |
| D-04 | Chain detection width | Interpreter chain regexes | Plain browser/app commands | `_OPEN_CHAIN_RE` fires on `open <AI-name> ... to <AI2>`; `_CHAIN_FROM_TO_RE` on any `from <AI> to <AI>`. Sentences merely *mentioning* an AI name can become chain intents, competing with the browse/open handlers. | interpreter.py:128-158, 340-391 | MEDIUM | **NOT REPRODUCIBLE** — both shapes require *two known* AI names plus a chain trigger; locked by tests (AD-07) |
| D-05 | Conversation history | `chat_messages` (UI transcript) | `conversation_messages` (Hermes sessions) | Two tables store overlapping conversation data with different writers; DELETE /chat clears both, /hermes/chat only writes the latter. | api.py:712-762; hermes/conversation.py | MEDIUM | **INTENTIONAL** (AD-09): rendered UI transcript vs model context; no merge (would break the /chat contract) |
| D-06 | Sandbox location | `HERMES_SANDBOX_PATH` relative ("sandbox") | CWD-dependent resolution | The same config yields `Backend/sandbox/` when the server runs from Backend/ and `sandbox/` at project root — two live index.json files exist with different task histories. | Backend/sandbox/index.json (34 queries) vs sandbox/index.json (4 queries); hermes/sandbox.py:40 | HIGH | **RESOLVED** (AD-01): one resolver, canonical root `Backend/sandbox` |
| D-07 | Skill execution contract | `success` gate | `handled` gate | A skill result with `success: false, handled: false` is skipped so the NEXT skill can try (including NLP chat); with `handled: true` the failure is final. Two competing semantics for "couldn't do it" coexist; not all skills set `handled` consistently (e.g. automation_engine's unknown_command does not). | brain/executor.py:154-171; skills/*/main.py | MEDIUM | **DEFERRED** — unchanged; needs a per-skill audit, not a consolidation change |
| D-08 | Browser targets | BrowserSkill (default browser) | Browser Awareness (isolated Chrome) | The open flow picks Chrome-isolated DOM automation only when the target is a non-deterministic bare domain; otherwise the OS default browser. Two different "open a website" behaviours with different session/login state. | interpreter.py:_extract_bare_domain + _DETERMINISTIC_DOMAINS; browser_awareness/driver.py profiles | MEDIUM | **INTENTIONAL** (AD-11): deterministic vs non-deterministic site routing, decided in the interpreter |
| D-09 | Tool-call validation | HermesAgent validator (Phase 3c) | ToolPlanner internal validation | ToolPlanner validates arguments itself and does NOT use hermes/validator.py's verdict/refusal-feedback flow; the two loops enforce different gates on the same registry. | tool_planner.py vs validator.py usage | MEDIUM | **RESOLVED** (AD-02): the validator is the only tool-call gate |
| D-10 | Config sync | `Backend/config.py` API_HOST/PORT | `sarthi.bat` hardcoded API_HOST/PORT | Two sources of the bind address that must be kept in sync manually (the bat file itself documents this). | config.py:28-30; sarthi.bat set lines | LOW | **DEFERRED** — cosmetic launcher change, no behavioural divergence observed |
| D-11 | Test-mode authority | `brain/modes.get_test_mode()` global | Per-call `execute=False/None` (ai_chain) | ai_chain allows an explicit execute override while every other skill only checks the global; the test runner sets the global, so an explicit True would bypass dry-run. | chain.py:76-79 vs skills honouring get_test_mode only | LOW | **DEFERRED** — no production caller passes an explicit override; the skill passes `None` unless test mode is global |
| D-12 | Voice announcements | ABSOLUTE.md contract (automation-only voice) | Spoken replies (all responses) | The archived doc mandated voice for hands-off automation; spoken_replies now speaks every reply. Behaviour outgrew the documented contract (contract archived, code moved on). | docs/archive/ABSOLUTE.md; utils/spoken_replies.py | LOW | **INTENTIONAL** — the contract is archived; current behaviour is documented in CAPABILITIES/CONFIGURATION |

## Resolution evidence

| Row | Change | Tests |
| --- | ------ | ----- |
| D-01 / D-09 | `HermesOrchestrator.process` delegates to `HermesAgent`; `ToolPlanner` class deleted; `/hermes/chat` uses the one loop (fast path disabled) | `test_consolidation_routing.py::TestSingleHermesLoop`, `test_tool_bridge.py`, `test_hermes_api.py`, `test_provider_abstraction.py` |
| D-02 | Pre-execution gate for task-shaped instructions; router reports its most specific signal as the reason | `test_consolidation_routing.py::TestTaskShapedEscalation` |
| D-03 / D-04 | No regex change; AI mentions verified to stay ordinary commands and two-AI shapes to stay chains | `test_consolidation_routing.py::TestChainIntentCollision` |
| D-06 | `resolve_sandbox_root` + `ConfigLoader` resolution; `TaskSandbox()` defaults to the canonical root | `test_consolidation_routing.py::TestSandboxCanonicalRoot` |
| D-05 / D-08 / D-12 | Documentation only (boundaries recorded in this file, MEMORY.md and ARCHITECTURAL_DECISIONS.md) | — |
