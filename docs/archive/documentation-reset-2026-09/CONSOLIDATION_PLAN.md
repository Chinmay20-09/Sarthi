# Consolidation plan

Status: **VALIDATED AND IMPLEMENTED** (2026-09-14). Results:
[CONSOLIDATION_REPORT.md](CONSOLIDATION_REPORT.md); per-change reasoning:
[ARCHITECTURAL_DECISIONS.md](ARCHITECTURAL_DECISIONS.md). The stop-condition
decisions (D1–D5) were answered by the maintainer and are recorded below; the
plan text (observations, verdicts, phases) is preserved unchanged as the audit
trail.

**Decisions taken before implementation:**

| # | Decision | Answer |
| - | -------- | ------ |
| D1 | Canonical sandbox root | `Backend/sandbox`, resolved against `config.PROJECT_ROOT` (now `hermes.sandbox.resolve_sandbox_root`) |
| D1b | Stray root `sandbox/` data | Left untouched (gitignored); it simply stops receiving records |
| D2 | Complex-task escalation | Fix narrowly: pre-execution gate for task-shaped instructions, with tests proving open/search/play/close are unaffected |
| D3 | Chain default AIs | Keep `chatgpt → gemini` for explicit `/chain` requests |
| D4 | Retry bound | Adopt the architectural bound of 3 automatic iterations |
| D5 | Deletions | Approved and executed (automation scaffolding, `analyze` stub, `pystray`) after the §19 checklist |

---

## Original plan (unchanged)

**Status at the time: PROPOSED. No code had been changed.**
Produced after Phase A (Observe) + Phase B evidence gathering, per the
consolidation brief (steps 1–15). Every claim below is backed by a source
path or a live probe run against the working tree.

Authority order used: source code + runtime behaviour > documentation.
Several documentation claims were found stale (see §3 "Documentation debt").

---

## 1. Method used

- Read `docs/` (PROJECT_STATE, ARCHITECTURE, DIVERGENCE, DEAD_CODE&Duplicate,
  RUNTIME_FLOW, AGENTS, CHAINING, TESTING, DEPENDENCIES, DATA_FLOW, MEMORY,
  KNOWLEDGE, MODULE_MAP, Divergance-matrix).
- Traced every orchestration path in source (callers, triggers, caps,
  validation, persistence).
- Ran live probes (read-only): interpreter output, router verdicts, sandbox
  path resolution from two working directories, sandbox index census,
  `pytest --collect-only`.
- Baseline: **1021 tests collected, 53 test files** (`pytest --collect-only`).

---

## 2. Verified findings (evidence)

| # | Finding | Evidence | Divergence IDs |
| - | ------- | -------- | -------------- |
| V1 | Sandbox root is cwd-relative; **two live stores exist** | `hermes/config/settings.py:13 sandbox_path: str = "sandbox"`; probe: root → `C:\Sarthi\sandbox`, cwd `Backend/` → `C:\Sarthi\Backend\sandbox`. Census: `Backend/sandbox/index.json` = **34 queries**, `sandbox/index.json` = **4 queries**. `sarthi.bat` does `cd /d "%~dp0"` → production writes `Backend/sandbox`. `scripts/clean_sandbox.py` also targets `Backend/sandbox`. `sandbox/` is gitignored. | DM-046, D-06, DEAD#8 |
| V2 | Two model-driven tool loops | `hermes/agent.py` (HermesAgent): fast path + retriever + `hermes/validator.py` gate + sandbox. `hermes/orchestrator.py:59 → tool_planner.ToolPlanner.run` (no validator, no retrieval, cap `MAX_TOOL_CALLS_PER_TASK=5`). `/command` fallback uses the agent (`api.py:388`); `POST /hermes/chat` uses the planner (`hermes/routes.py:275`); `hermes/main.py` uses the planner. Pure helpers are **already shared** (`agent.py` imports `build_decision_instructions`, `build_followup_instructions`, `parse_tool_call` from `tool_planner`). | DM-012, D-01, D-09 |
| V3 | Chain-intent collision is **not reproducible** in the documented case | Live probe: `"search for OpenAI"` → `search`; `"Open Google, search for "OpenAI", copy the URL"` → `open` + `search` (not chain); `"Use ChatGPT to write a script"` → `unknown`. `_parse_chain_intent` requires trigger word + `from <AI> to <AI>` with both names in `_CHAIN_AI_NAMES`; `_parse_open_chain` requires both AI names. Residual: `parse_chain_command` still defaults `chatgpt→gemini` when a chain intent carries no AIs (`/chain <query>`). Router reason strings can mislead (`"open chatgpt … to gemini"` → `hermes`/`simple_action_word` although the chain skill owns it). | DM-029, D-03, D-04 |
| V4 | Complexity routing is consulted **only after** a failed deterministic run, so a mis-parsed complex request never reaches Hermes | `api.py:376-388`: `if not result.get("success") or routing == "hermes"` → router → agent. Probe: `"Find all assignment PDFs and rename them according to subject"` → interpreter returns `search` (target `all assignment PDFs and rename them acco…`) and router score 0 (`fast`). Result: a complex file task is executed as a literal web search; Hermes is never woken. `"please open chrome"` → router `hermes` score 2, but handled deterministically before the router (harmless, confirms D-02). | DM-002, DM-003, DM-056, D-02 |
| V5 | Hermes has no direct system control and no shell/CLI path | 10 tools in `hermes/tools/` all delegate to existing skills/executor (`open_app.py → AppLauncherSkill`, `close_app.py → BrainExecutor`, `github.py → GitHubProjectSkill._ensure_github`). Repo-wide grep for `subprocess|os.system|shell=True|os.popen` under `Backend/hermes/` → **1 match, in a docstring**. | DM-008, DM-049, DM-058 |
| V6 | AI chain is invoked only through Sarthi's skill walk, but owns its **own** system-control stack | `brain/interpreter` → `chain` intent → executor → `AutomationSkill._handle_chain` (`skill.py:76`) → `run_ai_chain`; test-mode aware (`get_test_mode`), abort hotkey + failsafe. Control primitives live in `ai_chain/control.py` (pyautogui/keyboard/pyperclip) **in addition to** `hands/desktop/input.py`. A third controller lives in the production-dead `ai_chain/browser_automation.py`. | DM-028, DM-027, §15 (hands) |
| V7 | Browser automation is already semantic-first; blind coordinate clicking is **opt-in** | `ai_chain/registry.py:86-98` `COORDINATE_SCAN_ENV = "AI_CHAIN_COORDINATE_SCAN"`, grid disabled unless `=1`; DOM matchers (`aria-label="Copy"` etc.) primary, site-registered Copy button preferred, `Ctrl+A/Ctrl+C` page copy only as fallback. `skills/browser_awareness/` = Selenium/Playwright page + bs4 + inspector loop for arbitrary sites. | DM-031, DM-032, DM-033, §8 |
| V8 | Conversation persistence is four **different** semantic states, not four copies | `knowledge_memory` (user facts, injected via `build_memory_prompt`), `conversation_messages` (role/content model turns, `hermes/conversation.py`), `chat_messages` (rendered UI payload JSON, `api.py:732`), `command_history` (every `/command`, feeds retriever). `DELETE /chat` clears both conversation tables by design. | DM-035, DM-039, D-05 |
| V9 | Memory physically lives inside the knowledge package | `knowledge/memory.py` (`knowledge_memory` + `command_history`) vs `knowledge/manager.py` (apps/websites JSON). Boundary is conceptually right, placement is not. | DM-043 |
| V10 | Desktop hand is a validated executor with partial production reach | `hands/desktop/hand.py` (allow-listed actions, arg specs, no shell, scoped filesystem). Production callers: `brain/executor.py:287-300` (close), `skills/app_launcher/main.py:185` (launch), `desktop_agent.py` CLI (no IPC server). | DM-048, DM-051 |
| V11 | Automation-engine scaffolding is unreachable | `AutomationEngine.run(event)`, `skills/automation_engine/{events,context,preview}.py`, `contracts.AutomationEvent` — no callers, no test imports (grep). `skill.py` only calls `register_assistant(BrainAssistant())`; `analyze` returns a fixed stub (`skill.py:171-180`). | DM-052, DM-053, DM-054, DEAD#3/#4 |
| V12 | v1.7 DOM chain engine is production-dead but test-alive | `ai_chain/browser_automation.py` (1178 lines) exported in `ai_chain/__init__.__all__`, exercised by `tests/test_browser_automation.py`, no production caller (`run_browser_chain` never referenced outside its module/tests). | DEAD#1 |
| V13 | `pystray` declared, never imported | `pyproject.toml:15`; zero imports repo-wide. | DEAD#2 |
| V14 | `/browser/*` endpoints are placeholders | `skills/browser/routes.py` → `service.execute_action` returns `{"status": "pending"}`; no in-repo consumer found. | DEAD#5 |

---

## 3. Documentation debt found (docs must be corrected, not trusted)

- `DEAD_CODE&Duplicate.md` Dup#8 ("two GitHub data paths") is **stale**:
  `hermes/tools/github.py` already delegates to the project_tracker skill
  (V5). → mark RESOLVED / NOT REPRODUCIBLE.
- `DEAD_CODE&Duplicate.md` Dup#5 and `PROJECT_STATE.md` "known limitations"
  claim polite prefixes route to Hermes "costs a retrieval" — probe shows the
  router is not consulted at all when the fast path succeeds (V4). The router
  verdict is advisory-after-failure, not a pre-router.
- `Divergance-matrix.md` DM-029/D-03 chain collision: no longer reproducible
  in the documented form (V3); needs a characterization test to lock it.
- `PROJECT_STATE.md` says 52 test files; actual is 53 (1021 tests).
- `DIVERGENCE.md` D-12 (voice announcements vs archived contract) is a
  documentation-only divergence; the archived contract is gone. → close as
  INTENTIONAL.

---

## 4. Component verdicts

Legend: **KEEP** (no change) · **MERGE** (consolidate responsibility) ·
**MIGRATE** (move callers) · **DELETE** (remove, all §20 boxes ticked) ·
**DEFER** (documented, not changed now) · **CANDIDATE** (mark for removal,
evidence recorded, not removed).

### 4.1 Core / routing

| Component | Verdict | Change |
| --------- | ------- | ------ |
| `brain/interpreter.py` | **KEEP** | No fuzzy rules added (§16). Add characterization tests only. |
| `brain/planner.py` (pass-through) | **KEEP** | Do not invent multi-step planning now (§22, DM-013 deferred). |
| `brain/executor.py` (handler → skill walk) | **KEEP** | Sarthi's execution authority; unchanged. |
| `hermes/router.py` | **MERGE (call-site)** | Keep heuristics; move the *consult point* so complexity is evaluated against a low-confidence deterministic interpretation, not only after outright failure. See Decision D2 — **blocked on user validation**. |
| `hermes/validator.py` | **KEEP** | Already the single tool-call gate (§20 replacement behaviour). |
| Hermes retry mechanics (§3 "max 3 retries") | **KEEP + CLARIFY** | Current bound is `HERMES_AGENT_MAX_ITERATIONS=5` model turns + 300 s budget + 1 refusal-feedback retry. Brief says "maximum automatic retry attempts = 3". Decision D4: adopt 3 as the default config value? |

### 4.2 Hermes

| Component | Verdict | Change |
| --------- | ------- | ------ |
| `hermes/agent.py` (HermesAgent) | **KEEP as canonical loop** | The single reasoning loop. No redesign. |
| `hermes/orchestrator.py` | **KEEP (reduced role)** | Becomes: provider wiring + `chat()` (plain chat, no tools) + `process()` delegating to the canonical loop. Not a second brain. |
| `hermes/tool_planner.py::ToolPlanner` (class) | **DELETE after migration** | Duplicate loop (V2). Its three pure helpers survive in the same module (they are the tool-call protocol). |
| `hermes/tool_planner.py` pure helpers | **KEEP** | Already shared by both loops. |
| `POST /hermes/chat` | **MIGRATE** | Route through the canonical loop with the deterministic fast path **disabled** (the dashboard already ran `/command` first — `UI/chat.html:1718` sends the message to `/command`, then calls `/hermes/chat` only for unhandled/open-ended input). Response schema unchanged (no public-API break). |
| `hermes/main.py` | **KEEP** | Dev CLI; follows `orchestrator.process`. |
| Providers / registry | **KEEP** | P6 already satisfied (config-selected, no concrete provider imported in `service.py`). |

### 4.3 AI chaining

| Component | Verdict | Change |
| --------- | ------- | ------ |
| `ai_chain/` chain runner, driver, DOM, sites | **KEEP** | Working, tested, invoked only through Sarthi's skill walk (V5/V6). |
| Chain intent detection | **KEEP + LOCK** | Add characterization tests for the collision cases (V3). No regex widening. |
| `parse_chain_command` default `chatgpt→gemini` | **DEFER** | Only reachable via explicit `/chain`; Decision D3. |
| `ai_chain/browser_automation.py` (v1.7) | **DEFER / CANDIDATE** | §20 fails ("an important test uniquely validates it") → not deleted now. |
| `ai_chain/control.py` | **MERGE (later)** | Should become a thin semantic layer over `hands/desktop/input.py` (one system-control boundary, P9). Deferred because real (non-dry-run) control is **untested** — high risk. |

### 4.4 Browser

| Component | Verdict | Change |
| --------- | ------- | ------ |
| `skills/browser/` (OS default browser) | **KEEP** | Deterministic open path. |
| `skills/browser_awareness/` (isolated Chrome + DOM loop) | **KEEP** | Non-deterministic site path; the "two open-a-website behaviours" split is intentional and decided in the interpreter (D-08 → INTENTIONAL). |
| `ai_chain/dom.py`, `selenium_dom.py` | **KEEP** | Semantic-first; coordinate scan is opt-in (V7 → §8 already honoured by default). |
| Shared DOM/affordance primitive across both stacks | **DEFER** | Real overlap (V7) but both are tested and working; §22/§26 forbid an abstraction pass without a demonstrated need. Recorded as the browser consolidation follow-up. |
| `/browser/*` endpoints | **DEFER** | Possibly consumed by an out-of-repo extension. |

### 4.5 Memory / Knowledge / Sandbox

| Component | Verdict | Change |
| --------- | ------- | ------ |
| `knowledge/manager.py` + JSON stores | **KEEP** | Knowledge = operational/environment facts. |
| `knowledge/memory.py` | **KEEP (placement documented)** | Memory = user facts; add a boundary note (does not move package now — moving it would churn imports for zero behaviour change). |
| `conversation_messages` / `chat_messages` | **KEEP BOTH — INTENTIONAL** | Different semantic states (V8). No DB merge (would break the UI contract; §32.5). Document the boundary in MEMORY.md. |
| `hermes/sandbox.py` (TaskSandbox) | **KEEP (single implementation)** | Only the *root resolution* changes. |
| Sandbox root resolution | **MERGE → one canonical root** | Resolve a relative `HERMES_SANDBOX_PATH` against `config.PROJECT_ROOT` (`Backend/`), so launch directory stops mattering. `Backend/sandbox` is the de-facto production store (34 queries, `sarthi.bat` cwd, `clean_sandbox.py`). Absolute env values stay as-is. See Decision D1. |
| Root `sandbox/` + stray `sandbox_test/` copies | **MIGRATE (local data only)** | Not in git (`.gitignore:149-150`). Choice: fold the 4-query root index into the canonical store, or leave the stray dirs untouched and ignore them. See Decision D1. |

### 4.6 Hands / automation / dead code

| Component | Verdict | Change |
| --------- | ------- | ------ |
| `hands/desktop/*` | **KEEP** | Already the sanctioned execution boundary; documented gaps remain (DM-050, DM-051 deferred). |
| `desktop_agent.py` | **KEEP / DEFER** | Standalone CLI; no IPC server (seam only). |
| `AutomationSkill` + `BrainAssistant` | **KEEP** | Live, tested ("generate assistant for <skill>"). |
| `AutomationEngine.run`, `events.py`, `context.py`, `preview.py`, `contracts.AutomationEvent` | **DELETE (proposed)** | Unreachable scaffolding (V11): no callers, no tests, no config, no dynamic loading. Must be confirmed by re-running §19 checks before removal. |
| `automation analyze` stub branch | **DELETE (proposed)** | Returns a fixed empty payload; not a capability. |
| `pystray` dependency | **DELETE (proposed)** | Declared, never imported (V13). |
| `main-test.py`, `hermes/main.py` | **KEEP** | Manual/dev tools by design. |

### 4.7 Explicitly NOT changing (per §22)

HermesAgent loop design, tool registry + validator, provider abstraction,
skill registry/manifests, deterministic open/close/search/play/browse
handlers, `/remember` memory + retriever, connectors, UI/dashboard,
Desktop client, event bus, speech stack, `hermes/main.py`, browser stacks.

---

## 5. Phased change set (after plan validation)

- **Phase B (characterize, no behaviour change)**
  1. `tests/test_consolidation_routing.py` — interpreter + router verdicts for:
     `"Open Chrome"`, `"Open YouTube"`, `"please open chrome"`,
     `"search for OpenAI"`, `"Open Google, search for "OpenAI", copy the URL"`,
     `"Use ChatGPT to write a script"`, `"open chatgpt … to gemini"`, the
     assignment-renaming case. Locks V3/V4 in both directions.
  2. Sandbox tests: resolution identical from repo root and from `Backend/`
     (`monkeypatch.chdir`), plus a `TaskSandbox` round-trip.
  3. Hermes-loop parity tests: tool call / invalid tool / retry / cap /
     completion / failure / user-confirmation boundary, driven through the
     canonical loop with fake providers.
  4. Browser semantic-target tests with fakes (no real browser).
- **Phase C (consolidate Hermes)** — orchestrator.process → canonical loop;
  delete the `ToolPlanner` class; migrate the 3 test files that construct it
  (`test_tool_bridge.py`, `test_provider_abstraction.py`,
  `test_conversation_history.py`) to the canonical loop with **no** loss of
  assertions.
- **Phase D (sandbox canonicalization)** — one resolver; update
  `hermes/config/*`, `service.get_sandbox`, `executor._handle_clean`,
  `ai_chain/chain.py`, `clean_sandbox.py` to use it.
- **Phase E (delete confirmed unreachable code)** — only for the §4.6 rows
  marked DELETE, after re-running the §19 checklist; removal is its own
  commit-sized step so it can be reverted independently.
- **Phase F (verify)** — full `pytest` (expect ≥ baseline 1021),
  `ruff check`, `mypy` on touched modules, plus a runtime smoke check of
  `python -c` interpreter/router probes and a `/command` TestClient call.
- **Phase G (document)** — update `DIVERGENCE.md` (status column:
  RESOLVED / INTENTIONAL / DEFERRED / NOT REPRODUCIBLE — rows preserved),
  `Divergance-matrix.md` (DM statuses), `PROJECT_STATE.md`, `ARCHITECTURE.md`,
  `MEMORY.md`, `MODULE_MAP.md`, `AGENTS.md`, `DEAD_CODE&Duplicate.md`;
  create `docs/ARCHITECTURAL_DECISIONS.md`; create
  `docs/CONSOLIDATION_REPORT.md` (before/after, tests, remaining divergence).

---

## 6. Target ownership after consolidation

```text
SARTHI (authority: lifecycle, execution, permissions, memory, knowledge, sandbox)
│
├── brain/            interpreter → planner(pass-through) → resolver → executor
│     └── hands/      DesktopHand (validated system interaction)
├── hermes/           ONE reasoning loop (agent) + router + retriever + validator
│     └── tools/      10 Hermes-facing adapters → existing skills
├── skills/           portable capabilities (browser, awareness, chain, tracker…)
└── sandbox/          temporary task state (ONE canonical root)
```

Hermes may request; only Sarthi executes. AI chain stays a **capability**
invoked through the skill walk, never a peer brain.

---

## 7. Stop-condition decisions (need user validation before Phase C)

- **D1 — Sandbox canonical root.** Recommend `Backend/sandbox`
  (resolved against `config.PROJECT_ROOT`), because `sarthi.bat` cds to
  `Backend/`, `clean_sandbox.py` targets it, and it holds the real history
  (34 vs 4 queries). Also decide whether to fold/move the stray root
  `sandbox/` index (local, gitignored) or leave it untouched.
  *(§32.4 — filesystem migration)*
- **D2 — Complex-task escalation (P4/§29).** Fixing the "mis-parsed complex
  request is executed as a web search" gap (V4) changes behaviour of an
  existing capability. Options: (a) consult the router when a deterministic
  run produced a *low-confidence / search-from-a-task-verb* interpretation
  and escalate to Hermes; (b) leave as-is and only document. Recommend (a)
  narrowly scoped, with tests proving "open/search/play/close" are untouched.
  *(§32.2 — could remove a user-facing capability)*
- **D3 — Chain defaults.** Keep `chatgpt→gemini` defaults for explicit
  `/chain <query>`, or require named AIs? *(§32.10)*
- **D4 — Retry bound.** Adopt the brief's "maximum automatic retry
  attempts = 3" as the default `HERMES_AGENT_MAX_ITERATIONS`, or keep 5?
- **D5 — Deletions.** Approve removing the unreachable automation scaffolding
  + `pystray` + the `analyze` stub (Phase E), or mark them
  CANDIDATE FOR REMOVAL only?

Until these are answered, Phases B (tests) may proceed; Phases C–E will not.
