# Architectural decisions

Decision log for the 2026-09-14 architectural consolidation pass. Every entry
records the problem, the evidence from source (the final authority), what was
chosen, what was rejected, the migration, the risk and the tests that lock it.

Status values: **ACCEPTED** (implemented) · **DEFERRED** (documented only).

| ID | Decision | Status |
| -- | -------- | ------ |
| AD-01 | One canonical sandbox root (`Backend/sandbox`), cwd-independent | ACCEPTED |
| AD-02 | One Hermes reasoning loop (HermesAgent); the ToolPlanner loop is removed | ACCEPTED |
| AD-03 | `POST /hermes/chat` runs the canonical loop, fast path disabled | ACCEPTED |
| AD-04 | Task-shaped instructions escalate to Hermes *before* execution | ACCEPTED |
| AD-05 | Retry bound = 3 automatic iterations | ACCEPTED |
| AD-06 | Unreachable automation scaffolding + `pystray` removed | ACCEPTED |
| AD-07 | AI-chain intent collision: not reproducible, locked by tests | ACCEPTED |
| AD-08 | `/chain` keeps the chatgpt → gemini default AIs | ACCEPTED |
| AD-09 | Two conversation tables stay — different semantic states | ACCEPTED |
| AD-10 | Memory vs Knowledge boundary documented (placement unchanged) | ACCEPTED |
| AD-11 | Browser stacks stay separate; coordinate guessing stays opt-in | ACCEPTED |
| AD-12 | AI chain keeps its own control layer instead of delegating to Hands | DEFERRED |
| AD-13 | Sandbox → Knowledge promotion lifecycle | DEFERRED |
| AD-14 | AutomationEngine as a trigger-based, Sarthi-owned automation lifecycle | DEFERRED |
| AD-15 | Unified execution-observation contract (DM-050) | DEFERRED |
| AD-16 | Brain/Hand boundary: `Hand` interface, `DesktopHand` is the local implementation | ACCEPTED |

---

## AD-01 — One canonical sandbox root

**Problem** (DM-046, DIVERGENCE D-06): the same task could be written to two
different sandbox roots depending on the launch directory, so task history,
index lookups and `retrieval` differed by how the server was started.

**Evidence**

- `hermes/config/settings.py`: `sandbox_path: str = "sandbox"` (relative).
- `TaskSandbox.__init__` did `Path(root)` — resolved against the cwd at
  write time.
- Probe: from the repo root → `C:\Sarthi\sandbox`; with cwd `Backend/` →
  `C:\Sarthi\Backend\sandbox`. **Both stores exist**: `Backend/sandbox/index.json`
  (34 queries) and `sandbox/index.json` (4 queries).
- `Backend/sarthi.bat` does `cd /d "%~dp0"` → production writes
  `Backend/sandbox`; `Backend/scripts/clean_sandbox.py` also targets
  `Backend/sandbox`.

**Chosen**: one resolver, `hermes.sandbox.resolve_sandbox_root()`:
`None`/empty → `Backend/sandbox`; relative → resolved against the backend
root (`Path(__file__).resolve().parents[1]`, i.e. `Backend/`); absolute → used
as given. `TaskSandbox()` defaults to it, and `ConfigLoader` resolves
`HERMES_SANDBOX_PATH` through it, so every existing caller
(`service.get_sandbox`, `executor._handle_clean`, `ai_chain/chain.py`,
`hermes/main.py`) became canonical without a call-site change.

**Rejected**: (a) making the repo root canonical — it would have required
moving production history and changing `sarthi.bat`/`clean_sandbox.py`;
(b) resolving inside each caller — the divergence existed precisely because
resolution was implicit.

**Migration**: none required. The stray root `sandbox/` is gitignored
(`.gitignore:149`) and was left untouched by explicit user decision; it simply
stops receiving new records. `tests/test_fallback_integration.py` used a
relative `"sandbox_test"` path and now uses an absolute `tmp_path`, so tests no
longer create cwd-relative stores.

**Risk**: low. Behaviour for absolute paths (tests, custom deployments) is
unchanged; only relative resolution moved.

**Tests**: `tests/test_consolidation_routing.py::TestSandboxCanonicalRoot`
(default root, relative-vs-absolute, identical resolution from both launch
directories, config-loader resolution, `TaskSandbox` defaults).

---

## AD-02 — One Hermes reasoning loop

**Problem** (DM-012, DIVERGENCE D-01/D-09): two model-driven tool loops ran
over the same `ToolRegistry` with different validation, caps and persistence.

**Evidence**

- `hermes/agent.py` (HermesAgent): fast path → retrieval → model/tool loop →
  `hermes/validator.py` gate → sandbox persistence → iteration + wall-clock
  bounds. Used by the `/command` complexity fallback (`api.py`).
- `hermes/orchestrator.py:process` → `hermes/tool_planner.py::ToolPlanner`:
  same registry, **no** validator, **no** retrieval, cap
  `MAX_TOOL_CALLS_PER_TASK = 5`, its own prompt builders. Reached by
  `POST /hermes/chat` (`hermes/routes.py`) and `hermes/main.py`.
- Both already shared the pure protocol helpers (`agent.py` imported
  `build_decision_instructions`, `build_followup_instructions`,
  `parse_tool_call` from `tool_planner`).

**Chosen**: `HermesAgent` is the single reasoning loop.
`HermesOrchestrator` keeps only its genuine responsibilities — provider wiring
with primary/local fallback, `chat()` (plain conversational call, no tools) and
`process()` (delegates to the agent). The `ToolPlanner` **class** is deleted;
its three pure functions remain in `hermes/tool_planner.py`, which is now
explicitly the tool-call **protocol** module.

**Rejected**: keeping the ToolPlanner loop with a documented boundary — the
two loops performed the same job (a model answer or one validated tool call),
which is duplication, not two responsibilities.

**Migration**: `hermes/routes.py` and `hermes/main.py` need no change (they call
`orchestrator.process`). Tests that constructed `ToolPlanner` directly now
drive `HermesAgent` with the same fakes and assert the same behaviours.

**Risk**: medium-low. `/hermes/chat` now gains retrieval and validator
refusals (behaviour *improves*), and the sandbox trace records the agent's
richer steps (`retrieval`, `model`, `validation`, `tool_result`) instead of a
single `decision` step. The dashboard renders trace steps generically
(`Backend/UI/chat.html`), so no client change is needed.

**Tests**: `tests/test_consolidation_routing.py::TestSingleHermesLoop` (the
class is gone; the protocol survives; `process()` delegates once with the
caller's history/memory/task identity; `fast_path=False`),
`tests/test_tool_bridge.py` (tool call, tool failure, unknown tool refused,
iteration cap, trace shape), `tests/test_sandbox_query_index.py`,
`tests/test_conversation_history.py`, `tests/test_provider_abstraction.py`.

---

## AD-03 — `/hermes/chat` runs the canonical loop

**Problem**: the dashboard's chat fallback (`UI/chat.html` → `POST
/hermes/chat`) used the weaker duplicate loop while `/command` used the
stronger one, so the same question got different guarantees depending on
which path answered it.

**Evidence**: `Backend/UI/chat.html:1609-1739` posts every message to
`/command` first and calls `/hermes/chat` only when `/command` produced no
handler (open-ended question). `hermes/routes.py` then ran
`orchestrator.process` (ToolPlanner).

**Chosen**: `/hermes/chat` keeps its request/response schema but its work is
done by the single loop, with the deterministic fast path **disabled**
(`fast_path=False`) — the caller already gave Sarthi's pipeline the first
chance, so re-running it inside Hermes would only repeat a literal action.

**Rejected**: (a) making `/hermes/chat` a plain chat endpoint (would remove the
tool capability the dashboard advertises today → user-facing capability loss);
(b) leaving it on the duplicate loop.

**Risk**: low. Same provider stack and fallback; stricter tool validation.

**Tests**: `tests/test_hermes_api.py`, `tests/test_tool_bridge.py`
(`/hermes/chat` reports `tool_used`), `tests/test_conversation_history.py`
(session turns still recorded), `TestSingleHermesLoop`.

---

## AD-04 — Task-shaped instructions escalate before execution

**Problem** (DM-002/DM-003/DM-056, D-02; project principles P3/P4/P17): the
complexity router was consulted only **after** a failed deterministic run, so a
complex request that the interpreter mis-read as a simple action was executed
literally and Hermes was never consulted.

**Evidence**

- `api.py`: `if not result.get("success") or routing == "hermes"` → router →
  agent.
- Probe: `"Find all assignment PDFs and rename them according to subject"` →
  interpreter returns a single `search` intent
  (`target="all assignment PDFs and rename them acco…"`), and the router scored
  0 (`fast`). `skills/browser/main.py` would have executed that as a real
  browser search for the sentence's own words.
- `"please open chrome"` → router `hermes` (score 2) yet handled
  deterministically before the router — confirming the verdict is advisory.

**Chosen**: a pre-execution gate. `hermes.router.looks_like_task_instruction()`
fires when a sentence names file/document work (two task verbs, or one task
verb in a ≥6-word sentence); `api._is_task_shaped_search()` combines that with
an interpreter reading of exactly one `search` intent, and such a request is  handed to Hermes (`allow_fast_path=False`) **before** anything executes. The
  router also reports its most specific signal as the verdict reason instead of
  the generic `simple_action_word` / `long_command` ones.

**Rejected**: scattering more fuzzy rules into the interpreter (§16), and
widening the router's verdict to gate all execution (would have stolen
genuinely deterministic commands).

**Risk**: medium — this is the one behaviour change that overrides a
successful deterministic result. It is deliberately narrow: open, close, play,
browse, chain and Sarthi's own compound shapes are untouched, and a single
short search query (≤5 words, one verb) still runs as a search.

**Known limitation (DEFERRED)**: Sarthi has no filesystem/file tool, so Hermes
can reason about such a task but cannot execute it. Fulfilling P4's
"deterministic discovery + Hermes escalation" needs a file capability — a
feature, not a consolidation, and out of scope here.

**Tests**: `tests/test_consolidation_routing.py::TestTaskShapedEscalation`
(router signal, narrow heuristic, gate, `/command` integration with
`allow_fast_path=False`, simple command untouched, Hermes-down safety).

---

## AD-05 — Retry bound = 3 automatic iterations

**Problem** (DM-017): the brief fixes the intended bound at three automatic
retry attempts; the code defaulted to 5 (`HERMES_AGENT_MAX_ITERATIONS`,
`HermesConfig.agent_max_iterations`, `HermesAgent.DEFAULT_MAX_ITERATIONS`) and
the duplicate loop had its own cap of 5 tool calls.

**Chosen**: 3 is the default in `HermesConfig`, `hermes.service.run_task` and
`DEFAULT_MAX_ITERATIONS`. It stays configurable per deployment, still bounded
by wall-clock time (`HERMES_AGENT_TIMEOUT`, default 300 s) and by the
validator's single refusal-feedback turn.

**Evidence**: `tests/test_tool_bridge.py::test_tool_call_limit_prevents_infinite_loop`
now asserts exactly 3 executions and `reason == "iteration_cap"` from a model
that keeps requesting tools.

**Risk**: low — a complex task may now stop earlier; the agent returns a
graceful message instead of looping.

---

## AD-06 — Unreachable automation scaffolding removed

**Problem** (DM-052–DM-054, dead-code items 3 and 4): the automation engine
carried a second, unused orchestration pipeline.

**Evidence** (§19 checklist run before deletion)

- `AutomationEngine.run(event)`, `skills/automation_engine/{events,context,preview}.py`
  and `contracts.AutomationEvent`: **no callers** (repo-wide grep), **no test
  imports**, no config keys, no dynamic loading, no skill dependency.
  `skill.py` only called `register_assistant(BrainAssistant())`.
- The `analyze` branch returned a fixed `{"capabilities": []}` stub.
- `pystray` was declared in `pyproject.toml` with zero imports repo-wide.

**Chosen**: delete `events.py`, `context.py`, `preview.py`; reduce
`AutomationEngine` to the assistant registry (`register_assistant`,
`run_assistant`) with a docstring stating why the event pipeline is gone;
remove `AutomationEvent` and `AutomationContext` from `contracts.py`; remove
the `analyze` branch and `_handle_analyze`; drop the `pystray` dependency.
`ProjectState` / `ChangeRequest` / `AssistantResponse` were **kept** because
`assistants/brain_assistant/analyzer.py` still imports them (that module is
itself unreachable and is now recorded as a candidate in `DEAD_CODE&Duplicate.md`).

**Rejected**: keeping the scaffolding "for later" — it was a competing
orchestrator shape with no owner, and the intended automation lifecycle
(AD-14) belongs behind Sarthi's task ownership, not beside it.

**Risk**: low; nothing referenced the removed symbols. Reverting is a
single-commit revert.

**Tests**: full suite (no test touched these), plus
`tests/test_brain_assistant.py` covering the surviving assistant path.

---

## AD-07 — AI-chain intent collision: not reproducible, locked

**Problem** (DM-029, DIVERGENCE D-03/D-04): the forensic docs recorded a
sandbox-proven misfire where `Open Google, search for "OpenAI", copy the URL…`
executed as a ChatGPT → Gemini chain.

**Evidence** (live probe, current source)

- `"search for OpenAI"` → `search`.
- `'Open Google, search for "OpenAI", copy the URL'` → `open` + `search`.
- `"Use ChatGPT to write a script"` → `unknown` (never `chain`).
- `_parse_chain_intent` requires a trigger word *and* a `from <AI> to <AI>`
  clause whose names are both in `_CHAIN_AI_NAMES`; `_parse_open_chain`
  requires both names too.

**Chosen**: no code change; the reported collision is not reproducible in the
current source, so the finding is closed as NOT REPRODUCIBLE and locked by
tests in both directions (AI mentions stay ordinary commands; explicit
two-AI shapes stay chains).

**Risk**: low. The remaining trigger surface is the explicit shapes plus the
`/chain` slash command (AD-08).

---

## AD-08 — `/chain` keeps its default AIs

**Problem**: a chain command that names no AIs silently runs
ChatGPT → Gemini (`parse_chain_command` defaults).

**Chosen**: keep the documented default. The default is only reachable through
an explicitly chain-shaped request (`/chain <query>`, `chain <query>`,
`automate <query>`, `run <query> from A to B`), because the interpreter only
emits a `chain` intent for those shapes — so the residual risk is a user typing
`/chain` without naming AIs, not an accidental misfire on an ordinary sentence.

**Rejected**: requiring named AIs (would break the documented `/chain <query>`
shortcut and any automation built on it).

**Tests**: `TestChainIntentCollision::test_slash_chain_keeps_the_documented_default_ais`.

---

## AD-09 — Two conversation tables stay separate

**Problem** (DM-039, DIVERGENCE D-05): `chat_messages` and
`conversation_messages` both hold conversation data.

**Evidence**: `chat_messages` is written by the UI through `POST /chat`
(`api.py`) and stores the **rendered** assistant payload as JSON (cards,
provider, tool_used); `conversation_messages` is written by
`hermes/conversation.py` and stores `{role, content}` turns that are replayed
to the model as history. `DELETE /chat` clears both for a session by design.

**Chosen**: treat them as two states of the same exchange — UI transcript vs
model context — and document the boundary. No merge: collapsing them would
change the `/chat` API contract (a public API break) without removing real
duplication, since neither store can represent the other's shape.

**Risk**: none (documentation only). The boundary is recorded in `MEMORY.md`.

---

## AD-10 — Memory vs Knowledge boundary

**Problem** (DM-043): both layers store "information", so the boundary was
implicit.

**Evidence**: `knowledge_memory` (`knowledge/memory.py`, `/remember`,
injected as a system prompt via `build_memory_prompt`) holds **user facts**;
`tools/personal_context` and `user_config` hold user profile/config values;
`knowledge/applications.json` + `websites.json` (`knowledge/manager.py`) hold
**environment/operational** entities consumed by the resolver and the skills.

**Chosen**: document the boundary (Memory = user facts/preferences/relations;
Knowledge = environment, applications, capabilities) and keep the physical
layout. `knowledge/memory.py` therefore stays a *user-fact store that happens
to live inside the knowledge package*; moving the module would churn ~30
imports for zero behaviour change (§22/§26).

**Risk**: none (documentation only).

---

## AD-11 — Browser stacks stay separate; coordinate guessing stays opt-in

**Problem** (DM-030–DM-034, project principle §8): several browser
mechanisms coexist, and the brief forbids blind coordinate clicking.

**Evidence**

- `skills/browser_awareness/` (Selenium primary / Playwright fallback, bs4
  parsing, inspector loop) serves **arbitrary** sites via the `browse` intent
  and the `browser_ask` tool.
- `skills/automation_engine/ai_chain/` (`dom.py`, `selenium_dom.py`) serves
  **AI sites** for chaining, DOM-first: it reads the page, matches the
  semantic affordance (`aria-label="Copy"`, site-registered Copy button) and
  only then converts the element box to a window-fraction click.
- `registry.coordinate_scan_enabled()` is **off** unless
  `AI_CHAIN_COORDINATE_SCAN=1`; the `Ctrl+A`/`Ctrl+C` page copy is the
  fallback for unregistered sites, not the primary path.

**Chosen**: keep both stacks (different consumers, both tested and working)
and keep coordinate scanning opt-in. The semantic-target requirement is
already met by default; unifying the two DOM readers into one shared
affordance layer is recorded as a follow-up (DEFERRED) because neither stack
is broken and §22/§26 forbid an abstraction pass without a demonstrated need.

**Tests**: `tests/test_consolidation_routing.py::TestBrowserSemanticTargeting`
(scan off by default / opt-in, semantic `Copy` affordance, DOM matcher finds
the Copy button by label, the newest matching element wins, no blind fallback
when the label is absent) — no real browser is started.

---

## AD-12 — AI chain keeps its own control layer (DEFERRED)

**Problem** (DM-027/DM-028, P9): `ai_chain/control.py` drives the machine with
its own PyAutoGUI/keyboard/pyperclip stack instead of going through
`hands/desktop/input.py`, so two system-control mechanisms exist.

**Evidence**: the chain is invoked only through Sarthi's skill walk
(`AutomationSkill._handle_chain`), is test-mode aware, announces a hands-off
countdown and registers a Ctrl+Alt+X abort — so it does **not** bypass
Sarthi's authorization. But it does duplicate the low-level input boundary,
and a third copy lives in the production-dead
`ai_chain/browser_automation.py`.

**Chosen**: DEFERRED. The chain's control layer carries abort checks between
every action and real runs are **untested** by the suite (dry-run only), so
re-pointing it at `hands/desktop/input.py` is a behaviour-risk change to a
working capability that needs its own characterization harness first.

**Follow-up**: make `ai_chain/control.py` a thin semantic layer over
`hands/desktop/input.py` (keep `copy_with_button`, `select_all_and_copy`,
paste verification), then retire the duplicate primitive.

---

## AD-13 — Sandbox → Knowledge promotion (DEFERRED)

**Problem** (DM-038/DM-045): repeated temporary information (a task artifact)
is never promoted into durable knowledge.

**Chosen**: no implementation. Promotion needs a rule for *what* counts as
reusable and a user-facing confirmation boundary (P10); inventing it during a
consolidation pass would add an unowned automatic writer to the knowledge
store.

---

## AD-14 — AutomationEngine as a Sarthi-owned lifecycle (DEFERRED)

**Problem** (DM-052–DM-054): automation is intended to be a trigger-based,
Sarthi-owned workflow; today only assistant generation exists.

**Chosen**: DEFERRED. Building it requires task persistence, triggers and
ownership decisions (who creates, what persists, how it runs, whether CLI or
Hermes participates) — §32.1/§32.10 territory. AD-06 removed the unreachable
event pipeline so the future implementation starts from Sarthi's task model
instead of a parallel engine.

---

## AD-15 — Unified execution-observation contract (DEFERRED)

**Problem** (DM-050): after an action, different execution layers return
different observation shapes (`DesktopResult`, browser-awareness
`InspectionResult`, ai_chain `StepOutcome`), so Hermes reasons over
inconsistent feedback.

**Chosen**: DEFERRED. A common observation shape would touch
`hermes/tools/base.ToolResult`, the hands result model and both browser
stacks at once; the tool boundary already normalizes the Hermes-facing view
(`ToolResult`), so the divergence is internal rather than user-visible.

---

## AD-16 — Brain/Hand boundary: the `Hand` interface

**Problem**: the architectural rule "Backend = Brain, Desktop = Hand" was
real in the code (the Brain never touches the OS; `hands/` holds the only
input/process/filesystem backends) but had no named contract and no import
lock. A future remote device hand would have had nothing concrete to
implement, and nothing prevented a reasoning dependency from creeping into
`hands/`.

**Evidence**

- `hands/desktop/hand.py` already exposes exactly the right surface:
  `execute()` (allow-listed, argument-validated, structured result),
  `capabilities()`, `find_application_process()` — called by the executor's
  close flow, the app launcher and the standalone `desktop_agent.py` seam.
- `grep` verified: zero `brain|hermes|knowledge|skills|api` imports under
  `Backend/hands/`; zero `subprocess`/`os.system` under `hermes/`.
- AI-chain's separate control layer is already adjudicated (AD-12).

**Chosen**: introduce `hands/base.py::Hand` — a `runtime_checkable`
structural Protocol with exactly the three members `DesktopHand` already
has (`execute`, `capabilities`, `find_application_process`). No inheritance,
no runtime indirection, no behaviour change: the executor's close handler
now annotates `hand: Hand = get_desktop_hand()`. `DesktopHand` conforms
(asserted at import and in tests). The local path stays in-process; a
`RemoteDesktopHand` would implement the same contract over a network
protocol — deliberately **not** built now.

**Rejected**: (a) a `hand_manager.py`/`desktop_executor.py`-style second
abstraction — the hand already exists and works; (b) exposing new Hand
methods (screenshots, arbitrary shell) — no capability exists behind them;
(c) an IPC/WebSocket server for the hand — speculative infrastructure the
brief forbids.

**Risk**: low. Typing-only change to the executor; everything else is a new
module plus tests/docs.

**Tests**: `tests/test_brain_hand_boundary.py` — protocol conformance,
Backend-issues-through-the-interface, authority flow (explicit authorized
action + explicit pid, observation returned), allow-list refusal,
structured-failure contract, the `hands/` import lock (no brain modules,
no LLM/server references), tool-bridge-only Hermes→OS path, single Hermes
loop, single hand implementation, deterministic-vs-Hermes routing intact.
