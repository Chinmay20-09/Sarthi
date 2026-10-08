# SARTHI — DIVERGENCE MATRIX

**Purpose:** Compare the intended Sarthi architecture with the architecture observed in the repository.

**Authority order:**

1. User-defined intended behavior / architecture
2. Repository implementation evidence
3. Existing documentation
4. Architectural inference

A divergence does not automatically mean that something should be deleted. It means the implementation and intended architecture require investigation.

---

## 1. Core Architecture

| ID     | Concept             | Intended Architecture                                                                                 | Current Repository Reality                                                                    | Divergence                                                                                | Severity | Decision    |
| ------ | ------------------- | ----------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------- | -------- | ----------- |
| DM-001 | Sarthi Core         | Sarthi is the final authority over tasks, execution, state, permissions, and hands.                   | Repository contains BrainEngine/Core routing, execution, sandbox, skills and related systems. | Ownership boundaries need to be verified across runtime paths.                            | HIGH     | Investigate |
| DM-002 | Deterministic Core  | Simple tasks should remain inside Sarthi without waking Hermes.                                       | Deterministic pipeline exists through interpreter/planner/resolver/executor.                  | Current routing must be checked to ensure simple tasks cannot unnecessarily enter Hermes. | HIGH     | Investigate |
| DM-003 | Complexity Routing  | Sarthi decides whether a request is simple or complex.                                                | Complexity Router exists and Hermes is used for complex requests.                             | Need to verify that routing occurs before unnecessary model invocation.                   | HIGH     | Verify      |
| DM-004 | Task Ownership      | Sarthi owns a task from creation through execution, retry, completion and history.                    | Hermes currently participates in planning/status while Sarthi owns execution-related state.   | Ownership is distributed across components.                                               | HIGH     | Clarify     |
| DM-005 | Execution Authority | Sarthi controls actual execution; Hermes requests actions but does not directly control the computer. | Hermes uses tools which delegate into Sarthi capabilities. Hands exist separately.            | Appears aligned, but all execution paths must be checked.                                 | HIGH     | Verify      |
| DM-006 | Final Authority     | Sarthi should have final authority over actions and continuation.                                     | Validator, tools, executor and Hermes all participate in execution decisions.                 | Need explicit authority boundary.                                                         | HIGH     | Investigate |

---

## 2. Hermes

| ID     | Concept                   | Intended Architecture                                                                                    | Current Repository Reality                                                      | Divergence                                                               | Severity | Decision    |
| ------ | ------------------------- | -------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------- | ------------------------------------------------------------------------ | -------- | ----------- |
| DM-007 | Hermes Role               | Hermes is the reasoning/planning component used when Sarthi encounters complex work.                     | HermesAgent and Hermes-related orchestration systems exist.                     | Role appears to be implemented through more than one orchestration path. | CRITICAL | Investigate |
| DM-008 | Hermes Control            | Hermes must never directly possess system control.                                                       | Hermes accesses capabilities through tools.                                     | Appears aligned, but all tool paths need verification.                   | HIGH     | Verify      |
| DM-009 | Hermes Tools              | Hermes should interact with Sarthi through controlled tools rather than loading the entire skill system. | Tool registry exposes capabilities to Hermes.                                   | Appears aligned.                                                         | LOW      | Preserve    |
| DM-010 | Hermes Persistence        | Hermes should not continuously run or consume expensive resources when unnecessary.                      | Hermes is invoked through complex-path routing.                                 | Need to verify lifecycle and shutdown behavior.                          | HIGH     | Verify      |
| DM-011 | Hermes Model Independence | Hermes is an architectural role, not permanently tied to one specific model/provider.                    | Current implementation includes an Ollama-based Hermes model path.              | Current model implementation may be more tightly coupled than intended.  | MEDIUM   | Investigate |
| DM-012 | Hermes Orchestration      | There should conceptually be one Hermes reasoning/orchestration role.                                    | Repository contains HermesAgent and HermesOrchestrator/ToolPlanner-style paths. | Multiple model-driven orchestration loops appear to overlap.             | CRITICAL | Resolve     |

---

## 3. Planning & Task Lifecycle

| ID     | Concept         | Intended Architecture                                                            | Current Repository Reality                                                                | Divergence                                                                        | Severity | Decision    |
| ------ | --------------- | -------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------- | -------- | ----------- |
| DM-013 | Planning        | Hermes determines the next steps for complex tasks.                              | Planner exists in the deterministic path while Hermes also generates/controls next steps. | "Planner" responsibilities may be split between deterministic planner and Hermes. | HIGH     | Clarify     |
| DM-014 | Current Step    | Sarthi owns the current executing step.                                          | Runtime state is distributed across orchestration/execution components.                   | Need explicit task-state ownership.                                               | HIGH     | Investigate |
| DM-015 | Previous Step   | Completed/previous execution state lives in Sandbox.                             | Sandbox stores task-related artifacts/history.                                            | Appears directionally aligned.                                                    | MEDIUM   | Verify      |
| DM-016 | Next Step       | Hermes proposes/owns the next intended step.                                     | Hermes/tool-planning systems produce tool calls/next actions.                             | Appears aligned but overlaps with task orchestration.                             | HIGH     | Verify      |
| DM-017 | Retry           | Sarthi controls retry mechanics, with bounded retries and confidence considered. | Retry/validation behavior exists in Hermes-related systems.                               | Retry responsibility may be split between Sarthi and Hermes.                      | HIGH     | Investigate |
| DM-018 | Retry Authority | User has final authority when retry/continuation is risky or ambiguous.          | Validator/agent mechanisms exist.                                                         | Explicit user authority boundary needs verification.                              | HIGH     | Verify      |
| DM-019 | Completion      | Sarthi owns final task completion.                                               | Hermes participates in task status and completion reasoning.                              | Task completion authority may be distributed.                                     | HIGH     | Clarify     |

---

## 4. Skills & Tools

| ID     | Concept             | Intended Architecture                                                                                              | Current Repository Reality                                                   | Divergence                                                                               | Severity | Decision    |
| ------ | ------------------- | ------------------------------------------------------------------------------------------------------------------ | ---------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------- | -------- | ----------- |
| DM-020 | Skill               | A skill is a portable capability that can potentially be copied into another compatible system.                    | Skills are registered and exposed through the existing skill system.         | Portability requirements are not necessarily enforced by current architecture.           | MEDIUM   | Investigate |
| DM-021 | Tool                | A tool is a Hermes-facing controlled interface into capabilities.                                                  | Hermes ToolRegistry exposes tools which delegate into existing capabilities. | Appears strongly aligned.                                                                | LOW      | Preserve    |
| DM-022 | Skill/Tool Boundary | Hermes should use tools rather than directly owning/understanding the entire skill ecosystem.                      | Tool bridge exists between Hermes and capabilities.                          | Appears aligned.                                                                         | LOW      | Preserve    |
| DM-023 | Skill Registration  | New skills should become part of the skill system.                                                                 | Registry/skill infrastructure exists.                                        | Relationship between registration, knowledge and skill installation needs clarification. | MEDIUM   | Investigate |
| DM-024 | Skill Knowledge     | Knowledge should describe available operational capabilities rather than become the registration mechanism itself. | Knowledge and skill systems both exist.                                      | Exact ownership relationship is unclear.                                                 | MEDIUM   | Investigate |

---

## 5. AI Chaining

| ID     | Concept                | Intended Architecture                                                                                        | Current Repository Reality                                                    | Divergence                                                               | Severity | Decision    |
| ------ | ---------------------- | ------------------------------------------------------------------------------------------------------------ | ----------------------------------------------------------------------------- | ------------------------------------------------------------------------ | -------- | ----------- |
| DM-025 | AI Chain Purpose       | AI chaining is an automation mechanism allowing AI ↔ execution loops, e.g. ChatGPT → CLI → result → ChatGPT. | ai_chain subsystem exists with AI-provider and browser-related functionality. | Current subsystem may act as a separate orchestration system.            | HIGH     | Investigate |
| DM-026 | AI Chain Ownership     | Hermes should invoke/use chaining when it is the appropriate automation mechanism.                           | AI chaining exists as a distinct subsystem.                                   | May be positioned as a peer orchestrator instead of a Hermes capability. | HIGH     | Investigate |
| DM-027 | Chain vs Hermes        | Hermes reasons/plans; chaining executes a specific AI-to-AI/external-environment loop.                       | Hermes and chaining both contain orchestration-like behavior.                 | Responsibility overlap likely.                                           | HIGH     | Resolve     |
| DM-028 | Chain Safety           | Sarthi remains responsible for execution boundaries even during a chain.                                     | Chain contains browser/automation execution mechanisms.                       | Need to verify whether chains bypass Sarthi's execution authority.       | CRITICAL | Investigate |
| DM-029 | Chain Intent Detection | AI-chain detection should not accidentally classify ordinary user requests as AI-chain requests.             | Existing forensic documentation identified possible intent collision.         | Known routing ambiguity.                                                 | HIGH     | Resolve     |

---

## 6. Browser Automation

| ID     | Concept              | Intended Architecture                                                                                 | Current Repository Reality                                                                    | Divergence                                                 | Severity | Decision                 |
| ------ | -------------------- | ----------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------- | ---------------------------------------------------------- | -------- | ------------------------ |
| DM-030 | Browser Role         | Browser automation gives Sarthi controlled access to the internet.                                    | Multiple browser-related systems exist.                                                       | Capability is distributed across multiple implementations. | HIGH     | Investigate              |
| DM-031 | Browser Architecture | DOM/HTML understanding is preferred; screenshots/visual interaction are fallback mechanisms.          | Repository contains browser awareness, Selenium/BeautifulSoup and automation mechanisms.      | Multiple approaches coexist.                               | HIGH     | Consolidate conceptually |
| DM-032 | Browser Interaction  | Sarthi should target semantic elements such as Copy rather than blindly clicking coordinates.         | Repository includes browser/automation implementations with differing interaction mechanisms. | Need a single semantic browser-action boundary.            | HIGH     | Resolve                  |
| DM-033 | Browser Fallback     | Dynamic sites should be handled with visual/screenshot fallback where DOM inspection is insufficient. | Screenshot/visual capabilities exist in parts of the system.                                  | Integration boundary needs verification.                   | MEDIUM   | Verify                   |
| DM-034 | Browser as Core      | Browser automation should become core if form filling and similar internet workflows are supported.   | Browser automation is distributed across skills/automation/chain systems.                     | Current ownership is unclear.                              | HIGH     | Resolve                  |

---

## 7. Memory

| ID     | Concept            | Intended Architecture                                                                                      | Current Repository Reality                                            | Divergence                                       | Severity | Decision        |
| ------ | ------------------ | ---------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------- | ------------------------------------------------ | -------- | --------------- |
| DM-035 | Memory Definition  | Memory stores user facts, preferences, relationships and useful past interactions.                         | Multiple persistent stores contain conversational/task information.   | Memory responsibilities appear distributed.      | HIGH     | Investigate     |
| DM-036 | Memory Relevance   | Sarthi should remember useful user-provided information rather than irrelevant command telemetry.          | Command/history/task data is also retained.                           | Need explicit memory promotion/filtering rules.  | MEDIUM   | Clarify         |
| DM-037 | Memory Conflict    | Conflicting user preferences should be surfaced to the user for resolution.                                | Memory infrastructure exists.                                         | Conflict-resolution behavior needs verification. | MEDIUM   | Implement later |
| DM-038 | Memory Promotion   | Repeated temporary information can be promoted from Sandbox into longer-lived knowledge where appropriate. | Sandbox and knowledge systems exist.                                  | Promotion lifecycle is not clearly established.  | HIGH     | Investigate     |
| DM-039 | Conversation State | Conversation context should not be unnecessarily duplicated across stores.                                 | Documentation identifies multiple conversation-related storage paths. | Potential duplication.                           | HIGH     | Investigate     |

---

## 8. Knowledge

| ID     | Concept              | Intended Architecture                                                                              | Current Repository Reality                                         | Divergence                                            | Severity | Decision |
| ------ | -------------------- | -------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------ | ----------------------------------------------------- | -------- | -------- |
| DM-040 | Knowledge Definition | Knowledge represents operational information about Sarthi's environment/capabilities.              | Knowledge contains environment/application/capability information. | Appears broadly aligned.                              | LOW      | Preserve |
| DM-041 | Knowledge Ownership  | Sarthi owns the knowledge system, ultimately under user control.                                   | KnowledgeManager/loader/knowledge sources exist.                   | Ownership is distributed across managers and storage. | MEDIUM   | Verify   |
| DM-042 | Knowledge Updates    | Knowledge should update when the environment changes, e.g. a new application appears.              | Scanner/discovery infrastructure exists.                           | Need to verify update lifecycle.                      | MEDIUM   | Verify   |
| DM-043 | Memory vs Knowledge  | User facts/preferences belong to Memory; operational environment information belongs to Knowledge. | Boundaries are not always explicit.                                | Conceptual overlap.                                   | HIGH     | Clarify  |

---

## 9. Sandbox

| ID     | Concept           | Intended Architecture                                                     | Current Repository Reality                                                | Divergence                                                               | Severity | Decision    |
| ------ | ----------------- | ------------------------------------------------------------------------- | ------------------------------------------------------------------------- | ------------------------------------------------------------------------ | -------- | ----------- |
| DM-044 | Sandbox Purpose   | Sandbox stores temporary task state and artifacts.                        | Sandbox stores task-related artifacts/history.                            | Broadly aligned.                                                         | LOW      | Preserve    |
| DM-045 | Sandbox Promotion | Frequently useful information may be promoted into persistent knowledge.  | Promotion concept exists in intended architecture.                        | Actual automatic promotion is not established.                           | MEDIUM   | Planned     |
| DM-046 | Sandbox Path      | There should be one stable task workspace regardless of launch directory. | Repository documentation identified root/backend sandbox path divergence. | Same logical sandbox can resolve differently based on working directory. | CRITICAL | Resolve     |
| DM-047 | Sandbox Ownership | Sarthi owns task state and sandbox lifecycle.                             | Multiple components interact with sandbox.                                | Ownership should be centralized.                                         | HIGH     | Investigate |

---

## 10. Hands / Execution

| ID     | Concept         | Intended Architecture                                                                                            | Current Repository Reality                                         | Divergence                                       | Severity | Decision    |
| ------ | --------------- | ---------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------ | ------------------------------------------------ | -------- | ----------- |
| DM-048 | Hands           | Hands perform actual system interaction on behalf of Sarthi.                                                     | Desktop hand abstraction exists.                                   | Appears aligned conceptually.                    | LOW      | Preserve    |
| DM-049 | Hermes → Hands  | Hermes should not directly control hands; it should request actions through Sarthi/tool boundaries.              | Hermes accesses tools which delegate into capabilities.            | Needs complete runtime verification.             | CRITICAL | Verify      |
| DM-050 | Observation     | After an action, the execution layer should return enough observation/result for Hermes to reason about success. | Browser/desktop automation provides varying levels of observation. | Observation contract is not yet clearly unified. | HIGH     | Resolve     |
| DM-051 | Desktop Control | Desktop interaction should eventually use a consistent Hand abstraction.                                         | DesktopHand exists but current production integration is partial.  | Architecture and implementation are incomplete.  | HIGH     | Investigate |

---

## 11. Automation

| ID     | Concept               | Intended Architecture                                                                        | Current Repository Reality                                          | Divergence                                   | Severity | Decision    |
| ------ | --------------------- | -------------------------------------------------------------------------------------------- | ------------------------------------------------------------------- | -------------------------------------------- | -------- | ----------- |
| DM-052 | Automation Definition | Automation means trigger-based execution of a predefined workflow.                           | AutomationEngine infrastructure exists but execution is incomplete. | Intended capability exceeds implementation.  | MEDIUM   | Planned     |
| DM-053 | Automation Creation   | CLI creates automation pipelines guided by AI rather than Hermes directly owning automation. | Automation/assistant generation infrastructure exists.              | Current creation flow requires verification. | HIGH     | Investigate |
| DM-054 | Automation Ownership  | Created automation should persist as a Sarthi-owned workflow.                                | Persistence/execution model is incomplete.                          | Ownership lifecycle unclear.                 | MEDIUM   | Clarify     |

---

## 12. AI / External Intelligence

| ID     | Concept       | Intended Architecture                                                                       | Current Repository Reality                                                    | Divergence                                           | Severity | Decision    |
| ------ | ------------- | ------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------- | ---------------------------------------------------- | -------- | ----------- |
| DM-055 | AI Dependency | Sarthi's basic operation must not depend on external AI.                                    | Deterministic execution path exists.                                          | Appears aligned.                                     | LOW      | Preserve    |
| DM-056 | AI Invocation | AI should be invoked when complexity/semantic reasoning makes it valuable.                  | Hermes complex path exists.                                                   | Need to verify unnecessary model calls cannot occur. | HIGH     | Verify      |
| DM-057 | AI Provider   | ChatGPT/Claude/Gemini can provide intelligence through controlled automation.               | AI-provider integrations exist in chaining/Hermes-related systems.            | Provider boundaries need unification.                | MEDIUM   | Investigate |
| DM-058 | Cost Control  | Hermes must not directly initiate expensive resources such as unrestricted CLI/model usage. | Tool/agent boundaries exist but multiple automation paths complicate control. | Potential bypass paths.                              | CRITICAL | Investigate |

---

# 13. Overall Divergence Summary

| Category                  | Current Assessment                                          |
| ------------------------- | ----------------------------------------------------------- |
| Core Sarthi identity      | 🟡 Mostly aligned                                           |
| Deterministic execution   | 🟢 Strong                                                   |
| Hermes concept            | 🟠 Multiple overlapping implementations                     |
| Hermes authority boundary | 🟡 Conceptually clear, implementation requires verification |
| Skills                    | 🟢 Strong foundation                                        |
| Tools                     | 🟢 Strong boundary                                          |
| AI chaining               | 🟠 Likely misplaced/overlapping orchestration               |
| Browser automation        | 🟠 Multiple generations/implementations                     |
| Memory                    | 🟠 Fragmented                                               |
| Knowledge                 | 🟢 Conceptually sound                                       |
| Sandbox                   | 🔴 Path/ownership problem                                   |
| Hands                     | 🟡 Good abstraction, incomplete integration                 |
| Automation                | 🟡 Partial/scaffolded                                       |
| Task ownership            | 🟠 Needs explicit centralization                            |

---

# 14. Highest-Priority Divergences

These are the items that should be investigated before adding significant new functionality.

### CRITICAL

1. **DM-012 — Multiple Hermes orchestration loops**
2. **DM-028 — AI Chain potentially bypassing Sarthi execution authority**
3. **DM-046 — Sandbox path divergence**
4. **DM-049 — Hermes/Hands execution boundary**
5. **DM-058 — Expensive-resource/automation boundary**

### HIGH

1. **DM-029 — AI-chain intent collision**
2. **DM-027 — Hermes vs AI Chain responsibility overlap**
3. **DM-031 — Multiple browser automation mechanisms**
4. **DM-039 — Multiple conversation-state stores**
5. **DM-043 — Memory vs Knowledge boundary**
6. **DM-047 — Sandbox/task ownership**
7. **DM-050 — Unified execution observation**
8. **DM-051 — Desktop Hand integration**
9. **DM-017 — Retry ownership**
10. **DM-019 — Completion ownership**

---

# 15. Preliminary Target Architecture

This is NOT a refactoring specification yet.

It is the architectural hypothesis produced by comparing the intended behavior against the repository evidence.

```text
                              USER
                                │
                                ▼
                            ┌───────┐
                            │Sarthi │
                            │ Core  │
                            └───┬───┘
                                │
                       Interpret / Route
                                │
                    ┌───────────┴───────────┐
                    │                       │
                 SIMPLE                  COMPLEX
                    │                       │
                    ▼                       ▼
             Deterministic              Hermes
               pipeline                  │
                    │                     │
                    │                 Plan / Reason
                    │                     │
                    │                   Tools
                    │                     │
                    └──────────┬──────────┘
                               ▼
                           Sarthi Task
                               │
                     ┌─────────┼─────────┐
                     ▼         ▼         ▼
                   Skills    Hands     Memory/
                              │       Knowledge
                              │
                              ▼
                           System
                              │
                              ▼
                           Result
                              │
                              ▼
                           Hermes
                              │
                    continue / finish / ask
                              │
                              ▼
                           Sarthi
                              │
                              ▼
                             User
```

### Conceptual ownership

```text
Sarthi
├── Task lifecycle
├── Execution authority
├── Hands
├── Skills
├── Memory
├── Knowledge
├── Sandbox
└── Hermes
     └── Tools
```

Where:

```text
Hermes = intelligence / planning

Tools = Hermes-facing interfaces

Skills = portable capabilities

Hands = actual system interaction

Memory = user/past-interaction information

Knowledge = operational/environment information

Sandbox = temporary task state/artifacts

AI Chain = automation capability used when appropriate,
           not a second competing Sarthi brain
```

This last point is a **hypothesis**, not yet a confirmed implementation requirement.

---

# 16. Decision Rule

For every divergence, ask:

> "Is this component violating Sarthi's intended ownership boundary, or is it simply implementing the boundary differently?"

Only the first case should trigger architectural removal/refactoring.

Do not delete a component merely because another component looks similar.

First prove that:

1. They perform the same responsibility.
2. They are both active.
3. They have no intentional boundary.
4. One can safely replace the other.
5. Removing one does not eliminate a required capability.

---

# 17. Current Conclusion

Sarthi does NOT currently require a rewrite.

The strongest evidence points toward **architectural consolidation**, particularly around:

* Hermes orchestration
* AI chaining
* browser automation
* task ownership
* sandbox ownership
* memory/conversation state
* execution/observation boundaries

The deterministic core, skill system, tool boundary, and general local-first philosophy appear substantially aligned with the intended Sarthi architecture.

The next step is to validate each high-severity divergence against the actual source code before making any deletion/refactoring decision.

---

# 18. Status after the 2026-09-14 consolidation pass

Every original row is preserved above. This table assigns each divergence its
outcome: **RESOLVED** (changed + test-locked), **INTENTIONAL** (boundary
documented), **DEFERRED** (understood, deliberately unchanged) or
**NOT REPRODUCIBLE** (could not be reproduced in the current source, now
locked by tests). AD references point at
[ARCHITECTURAL_DECISIONS.md](ARCHITECTURAL_DECISIONS.md).

| ID | Status | Note | AD |
| -- | ------ | ---- | -- |
| DM-001 | INTENTIONAL | Sarthi's authority is the `brain/` pipeline + executor + skills + hands; ownership boundaries verified along both runtime paths | — |
| DM-002 | RESOLVED | Simple commands never wake Hermes (locked); complex/task-shaped ones now reach Hermes before execution | AD-04 |
| DM-003 | RESOLVED | Routing happens before execution for task-shaped instructions, not only after failure | AD-04 |
| DM-004 | INTENTIONAL | Task lifecycle is API → brain → skill/hand; Hermes proposes, Sarthi owns state and completion | — |
| DM-005 | INTENTIONAL | Hermes has no system control: all 10 tools delegate to existing skills; zero `subprocess`/`os.system` in `hermes/` | AD-02 |
| DM-006 | INTENTIONAL | Authority chain: interpreter → executor → skill/hand; the validator gates every Hermes tool call and refusals are fed back once | — |
| DM-007 | RESOLVED | One Hermes role, one loop | AD-02 |
| DM-008 | INTENTIONAL | Verified: tools only request; Sarthi executes | — |
| DM-009 | INTENTIONAL | Tool registry is the Hermes-facing boundary; preserved | — |
| DM-010 | INTENTIONAL | Hermes runs only on demand (router/endpoint); no background loop or polling | — |
| DM-011 | INTENTIONAL | Provider/model is config-selected through `hermes/providers/registry.py`; no concrete adapter imported by `service.py` | — |
| DM-012 | RESOLVED | `ToolPlanner` loop deleted; `HermesAgent` is the only reasoning loop | AD-02, AD-03 |
| DM-013 | INTENTIONAL | `brain/planner.py` stays a pass-through (deterministic decomposition only); Hermes proposes next steps for complex work | AD-14 |
| DM-014 | INTENTIONAL | Current step ownership: the executor executes; the agent loop's step state is local and persisted per run | — |
| DM-015 | INTENTIONAL | Previous-step artifacts live in the sandbox (now one canonical root) | AD-01 |
| DM-016 | INTENTIONAL | Next step is produced by the model and validated by the validator before dispatch | AD-02 |
| DM-017 | RESOLVED | Retry bound fixed at 3 automatic iterations (+ wall clock + 1 refusal feedback) | AD-05 |
| DM-018 | DEFERRED | No explicit confirmation prompt for risky continuations; the validator blocks malformed/unregistered calls | AD-15 |
| DM-019 | INTENTIONAL | Sarthi owns the response and completion; the agent's answer is only text | — |
| DM-020 | DEFERRED | Skill portability is real but unenforced; a per-skill dependency classification is a follow-up audit | — |
| DM-021 | INTENTIONAL | Tool = Hermes-facing adapter; preserved | — |
| DM-022 | INTENTIONAL | Skill/tool boundary verified | — |
| DM-023 | INTENTIONAL | Registration is manifest-based in `skills/registry.py`; knowledge does not register skills | AD-10 |
| DM-024 | INTENTIONAL | Knowledge describes entities/capabilities; it is not a registry | AD-10 |
| DM-025 | INTENTIONAL | AI chain is an automation mechanism (site → site), invoked from the skill walk | — |
| DM-026 | INTENTIONAL | Chain is reached as a capability (chain intent → automation skill), never as a peer brain | — |
| DM-027 | RESOLVED | Boundary explicit: Hermes reasons; the chain executes one bounded AI→AI loop as a skill | AD-12 |
| DM-028 | INTENTIONAL | No bypass found: the chain runs inside Sarthi's skill walk, test-mode aware, with abort controls | AD-12 |
| DM-029 | NOT REPRODUCIBLE | The documented accidental chain misfire no longer occurs; locked by tests both ways | AD-07, AD-08 |
| DM-030 | INTENTIONAL | Two browser stacks, two distinct consumers (arbitrary sites vs AI sites) | AD-11 |
| DM-031 | DEFERRED | DOM-first in both stacks; unifying the two DOM readers is a follow-up | AD-11 |
| DM-032 | RESOLVED | Semantic targeting verified and locked: DOM affordance/`aria-label` primary, coordinate scan opt-in, no blind clicking | AD-11 |
| DM-033 | INTENTIONAL | Screenshot/visual work lives in ai_chain `screen.py`/`awareness.py`; the DOM-miss path falls back to it | AD-11 |
| DM-034 | DEFERRED | Browser has no core-level ownership yet (form filling etc.); left to the browser consolidation follow-up | AD-11 |
| DM-035 | INTENTIONAL | Memory stores user facts (`knowledge_memory`); command/task telemetry stays separate and feeds retrieval | AD-10 |
| DM-036 | DEFERRED | No promotion/filtering rule for what becomes memory; `/remember` remains explicit | AD-13 |
| DM-037 | DEFERRED | No conflict surfacing for contradictory remembered facts | AD-13 |
| DM-038 | DEFERRED | Sandbox → knowledge promotion lifecycle not implemented | AD-13 |
| DM-039 | INTENTIONAL | `chat_messages` (rendered transcript) vs `conversation_messages` (model context) are different states | AD-09 |
| DM-040 | INTENTIONAL | Knowledge holds environment/operational facts; preserved | — |
| DM-041 | INTENTIONAL | `KnowledgeManager` singleton owns app/site knowledge; memory is a separate store | AD-10 |
| DM-042 | INTENTIONAL | The scanner skill + `/applications/*` endpoints update knowledge when the environment changes | — |
| DM-043 | RESOLVED | Memory vs Knowledge boundary documented explicitly | AD-10 |
| DM-044 | INTENTIONAL | Sandbox holds temporary task state; preserved | — |
| DM-045 | DEFERRED | Promotion from sandbox to knowledge is a planned lifecycle | AD-13 |
| DM-046 | RESOLVED | One absolute, cwd-independent sandbox root | AD-01 |
| DM-047 | RESOLVED | Sandbox lifecycle centralized in `hermes/sandbox.py` (`TaskSandbox` + `resolve_sandbox_root`) | AD-01 |
| DM-048 | INTENTIONAL | Hands perform system interaction; they never reason | — |
| DM-049 | INTENTIONAL | Hermes → tool → skill/hand verified for all 10 tools; the chain's private control layer is the one deferred overlap | AD-12 |
| DM-050 | DEFERRED | Observation shapes still differ per layer; the Hermes-facing view is normalized by `ToolResult` | AD-15 |
| DM-051 | DEFERRED | Desktop hand is used by close/launch/CLI only; full desktop integration is a feature, not a consolidation | AD-12 |
| DM-052 | DEFERRED | Automation is intended to be trigger-based; the unreachable engine pipeline was removed instead of promoted | AD-06, AD-14 |
| DM-053 | DEFERRED | Automation creation flow (CLI + AI guidance) not implemented | AD-14 |
| DM-054 | DEFERRED | Automation persistence/ownership model not implemented | AD-14 |
| DM-055 | INTENTIONAL | Deterministic path needs no AI; preserved | — |
| DM-056 | RESOLVED | Complexity is consulted before execution for the mis-read class; simple commands still never invoke the model | AD-04 |
| DM-057 | INTENTIONAL | External AI (sites) reached through the chain capability; local models through the provider abstraction | — |
| DM-058 | INTENTIONAL | No unrestricted shell/CLI path exists in Hermes or the chain; tools are an allow-list of 10 delegating adapters | AD-02 |

## Updated summary

| Category | Assessment after consolidation |
| -------- | ------------------------------ |
| Core Sarthi identity | 🟢 Aligned (authority verified along both paths) |
| Deterministic execution | 🟢 Strong |
| Hermes concept | 🟢 One loop, validator-gated |
| Hermes authority boundary | 🟢 Verified (no system control, no shell) |
| Skills | 🟢 Strong foundation (portability audit deferred) |
| Tools | 🟢 Strong boundary |
| AI chaining | 🟢 Capability inside Sarthi (control-layer merge deferred) |
| Browser automation | 🟢 Semantic-first, singular boundary deferred |
| Memory | 🟡 Boundary documented; promotion deferred |
| Knowledge | 🟢 Conceptually sound |
| Sandbox | 🟢 One canonical root |
| Hands | 🟡 Good boundary, partial integration (deferred) |
| Automation | 🟡 Scaffolding removed; lifecycle deferred |
| Task ownership | 🟢 Sarthi owns lifecycle; Hermes proposes |
