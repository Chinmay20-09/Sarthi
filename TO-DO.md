TO-DO

STATUS (2026-09-16): BOTH ITEMS DONE.

> ACTIVE SPRINT (2026-09-16): the current task list lives in
> docs/agent/TASK.md — (1) IPC token auth, (2) terminal capability
> (cd / echo / create / write).

> NOTE (2026-09-16 documentation restructure): docs/ paths mentioned in the
> historical record below (e.g. docs/ARCHITECTURE.md) were consolidated into
> docs/dev/ and the originals archived under
> docs/archive/documentation-reset-2026-09/.

1. ✅ DONE (2026-09-16) — add voice feedback to all test(at last for example:"test_ai_chain.py passed" at end of each file)
   Implemented via `tests/conftest.py` (session-wide pytest hook, no per-file
   edits): announces "test_<file>.py passed" aloud at the end of every
   pytest file — or "test_<file>.py failed. N tests failed." — using the
   existing `utils/voice.announce()` (Windows SAPI → PowerShell TTS → log
   line). One announcement per file; `SARTHI_TEST_VOICE=0` silences it; CI
   is silent by default. Verified: full suite 1127 passed, 49 collected
   files, hook active.
2. ✅ DONE (2026-09-16) — implement documentation prompt:
   Documentation aligned with the canonical architecture below. Anchor:
   "Canonical terminology map" section added to docs/ARCHITECTURE.md
   (canonical role → code → CURRENT/PLANNED label → evidence, plus the
   deterministic-first principle and CURRENT-vs-TARGET topology).
   Aligned: README, PROJECT_STATE, RUNTIME_FLOW, DATA_FLOW, AGENTS, TOOLS,
   SKILLS, CAPABILITIES, KNOWLEDGE, MEMORY, DATABASE, TESTING, MODULE_MAP.
   No production code modified; no implementations invented; remote
   Hands/IPC/discovery documented as PLANNED. Contradiction audit clean
   (historical reports kept per DOCUMENTATION_RULES.md rule 10). Tests:
   architecture/boundary suites pass. Changed files: the 14 docs above.
   Remaining gaps documented as PLANNED: Brain↔Hand protocol, remote
   Hands, provider/capability discovery registry, unified capability
   registry, SHELL/WINDOW_CONTROL capabilities, real multi-step planner.

The original prompt text is preserved below unchanged as the reference.

------------------------------------------------------------------------

1.add voice feedback to all test(at last for example:"test_ai_chain.py passed" at end of each file)
2.implement documentation prompt:
Update and align the entire Sarthi documentation with the following
canonical architecture.

IMPORTANT:
The repository code is the source of truth.

Do NOT invent implementations.
Do NOT mark planned functionality as implemented.
Do NOT modify production code unless absolutely required by documentation
tooling/tests.
First inspect the existing code and documentation, then update the docs.

============================================================

1. CANONICAL SARTHI ARCHITECTURE
============================================================

Sarthi is a deterministic orchestrator.

Hermes is a complex/model-driven orchestrator.

These are NOT interchangeable.

Sarthi should use deterministic routing and registered capabilities
whenever a known solution exists.

Hermes should be invoked only when deterministic orchestration is
insufficient, such as when a task is complex, ambiguous, requires
planning/reasoning, or has no suitable deterministic route.

Conceptual flow:

    User
      ↓
    Sarthi Brain
      │
      ├── deterministic solution exists
      │        ↓
      │     Skill / Tool
      │
      └── deterministic solution unavailable
               ↓
             Hermes
               ↓
          reasoning/planning
               ↓
          Skill / Tool
               ↓
          Capability request
               ↓
              Hand

The model is a component used by Hermes.
Hermes itself is the complex orchestrator.

Neither Sarthi nor Hermes should directly perform physical machine
execution.

Hands are execution layers.

============================================================
2. SARTHI SERVER
============================================================

The target architecture is a server-oriented Sarthi runtime.

Conceptually:

    Sarthi Server
    │
    ├── Model
    ├── Brain
    ├── Hermes
    ├── Memory
    ├── Knowledge
    ├── Database
    ├── Skills
    └── Tools

Hands are external execution surfaces:

    Sarthi Server
       │
       ├── Desktop Hand
       ├── Android Hand
       ├── Browser Hand
       ├── future IoT Hand
       └── other execution Hands

IMPORTANT:

This is TARGET architecture unless the repository already implements
all corresponding functionality.

If remote Hands / Brain↔Hand IPC are not implemented, document them as
PLANNED rather than IMPLEMENTED.

Do not claim that Sarthi is already a fully distributed server merely
because this is the intended architecture.

============================================================
3. MEMORY
============================================================

Memory represents private/user-specific context.

Memory answers:

    "What relevant information do I know about this user,
     their previous conversations, preferences, context, or state?"

Memory is NOT the capability registry.

Memory must not be described as the place where Sarthi stores everything
it can do.

Where the implementation supports it, describe Memory as a private/local
conversation and context layer.

If actual network isolation/private-network guarantees are not implemented,
do NOT claim security guarantees that the code does not provide.

Use precise terminology such as:

    private memory
    user context
    conversation context
    persistent context

only where supported by implementation.

============================================================
4. KNOWLEDGE
============================================================

Knowledge represents what Sarthi knows about its available capabilities.

Knowledge answers:

    "What can Sarthi do, and through which Skills, Tools,
     Capabilities, Providers, and Hands can it do it?"

Knowledge should conceptually contain/describe:

    Skills
    Tools
    Capabilities
    Providers
    Hands
    supported entities
    relationships between them

Do NOT define Knowledge merely as:

    "all possible skills Sarthi can do"

Instead describe it as a registry/knowledge layer that allows the
orchestrator to determine what capabilities and execution paths are known.

IMPORTANT:

Separate:
    what Sarthi knows is possible
from:
    what is currently available on a connected Hand.

A capability may be known by Knowledge while no currently connected Hand
provides it.

============================================================
5. SKILLS
============================================================

A Skill is a capability-oriented subsystem that groups related behaviour.

Examples may include:

    automation
    browser
    project tracking
    scanner
    speech
    etc.

Only document Skills that actually exist in the repository as
IMPLEMENTED.

Do not invent Skills merely because the architecture could support them.

============================================================
6. TOOLS
============================================================

A Tool is a specific structured operation exposed to the orchestrator.

Tools are NOT arbitrary code execution.

Tools should have:

    name
    purpose
    parameters
    required capability
    execution/action semantics

Example conceptual definition:

    Tool:
        download

    Parameters:
        package: string

    Required capability:
        terminal

    Template/operation:
        pip install {package}

For:

    "download numpy"

the tool receives:

    package = "numpy"

and produces a structured action/capability request.

Do NOT document this as the model directly executing:

    pip install numpy

The orchestrator remains responsible for validation and routing.

============================================================
7. CAPABILITIES
============================================================

A Capability represents an abstract ability required to perform an action.

Examples:

    terminal
    browser
    clipboard
    filesystem

Capability is different from its concrete implementation.

For example:

    terminal
       ↓
    provider: CMD
       ↓
    Desktop Hand

or:

    terminal
       ↓
    provider: bash
       ↓
    Linux Hand

or:

    terminal
       ↓
    provider: Termux
       ↓
    Android Hand

Do NOT hardcode:

    terminal = CMD

as a universal architectural rule.

============================================================
8. PROVIDERS
============================================================

A Provider is the concrete implementation of a capability.

Examples:

    terminal → CMD
    terminal → PowerShell
    terminal → bash
    terminal → Termux
    browser → Chrome
    browser → Firefox

Document Providers separately from abstract Capabilities.

Only document provider discovery as IMPLEMENTED if the code actually
discovers and registers providers.

Otherwise mark capability/provider discovery as PLANNED.

============================================================
9. HANDS
============================================================

A Hand is an execution layer.

A Hand:

    receives validated structured requests
    resolves the requested capability/provider
    performs the physical/system operation
    returns a structured result

A Hand does NOT:

    perform model reasoning
    replace the Brain
    replace Hermes
    decide the overall task plan

The Desktop Hand is the physical Windows execution layer.

The Android Hand, Browser Hand, IoT Hand, etc. should be treated as
future/other execution surfaces unless they already exist in code.

============================================================
10. CAPABILITY DISCOVERY
============================================================

The target architecture should support capability discovery.

A Hand can report what it can currently provide.

Conceptually:

    Desktop Hand
        terminal → available
        browser → available
        clipboard → available

    Android Hand
        terminal → available
        browser → available

The system can then associate:

    capability
        ↓
    provider
        ↓
    Hand

For example:

    terminal
       ↓
    CMD
       ↓
    Desktop Hand

IMPORTANT:

If this discovery/registration mechanism is not yet implemented,
document it as PLANNED.

Do not describe conceptual examples as current runtime behaviour.

============================================================
11. EXAMPLE: "DOWNLOAD NUMPY"
============================================================

Use the following example to explain the architecture where useful.

User:

    "download numpy"

Conceptual flow:

    User
      ↓
    Sarthi Brain
      ↓
    deterministic route identified
      ↓
    Automation Skill
      ↓
    download Tool
      ↓
    parameter:
        package = "numpy"
      ↓
    structured action
      ↓
    required capability:
        terminal
      ↓
    capability/provider resolution
      ↓
    Desktop Hand
      ↓
    terminal provider
      ↓
    pip install numpy
      ↓
    structured result
      ↓
    Sarthi
      ↓
    User

IMPORTANT:

This is an ARCHITECTURAL EXAMPLE unless the entire flow is currently
implemented and tested.

Label it accordingly.

============================================================
12. HERMES ROLE
============================================================

Hermes is the complex orchestrator.

Hermes should be documented as responsible for tasks such as:

    reasoning
    planning
    multi-step problem solving
    selecting existing tools
    determining required capabilities
    handling cases without a deterministic Sarthi route
    bounded skill/tool generation where implemented
    validation where implemented

Hermes should NOT be documented as:

    the physical executor
    the Desktop Hand
    arbitrary shell execution
    the entire Sarthi Brain
    a replacement for deterministic routing

The relationship is:

    Sarthi
       ↓
    deterministic path?

    YES → execute known path

    NO
       ↓
    Hermes
       ↓
    complex orchestration
       ↓
    structured tool/action request
       ↓
    Hand

============================================================
13. DETERMINISTIC-FIRST PRINCIPLE
============================================================

Make this principle explicit throughout the documentation:

    Sarthi should prefer deterministic orchestration whenever
    a known, validated capability path exists.

    Hermes is an escalation path for complexity, not the default
    execution mechanism for every request.

This principle should be reflected consistently in:

    ARCHITECTURE.md
    RUNTIME_FLOW.md
    DATA_FLOW.md
    AGENTS.md
    CAPABILITIES.md
    PROJECT_STATE.md
    README.md

Do not allow contradictory descriptions such as:

    "every command is sent to the LLM"

or:

    "Hermes executes commands"

unless such behaviour actually exists and is intentionally documented.

============================================================
14. DOCUMENT CURRENT VS TARGET ARCHITECTURE
============================================================

Every major document must distinguish:

    CURRENT / IMPLEMENTED

from:

    PLANNED / TARGET

Use explicit labels.

Example:

CURRENT:

    BrainEngine performs deterministic interpretation/routing.
    Hermes provides the current complex orchestration path.
    DesktopHand provides Windows execution.

PLANNED:

    Sarthi Server operates independently of physical Hands.
    Hands register/discover capabilities.
    Brain communicates with remote Hands.
    Capability/provider registry routes actions to the appropriate Hand.

Do not merge these two states.

============================================================
15. DOCUMENTATION FILES TO REVIEW
============================================================

Inspect and update all relevant canonical documents, including:

    ARCHITECTURE.md
    RUNTIME_FLOW.md
    DATA_FLOW.md
    MODULE_MAP.md
    AGENTS.md
    SKILLS.md
    TOOLS.md
    CAPABILITIES.md
    DATABASE.md
    MEMORY.md
    KNOWLEDGE.md
    API.md
    CONFIGURATION.md
    DEPENDENCIES.md
    TESTING.md
    PROJECT_STATE.md
    DIVERGENCE.md
    DEAD_CODE.md
    FORENSIC_SUMMARY.md
    README.md

Follow DOCUMENTATION_RULES.md exactly.

Do not create duplicate architectural definitions across documents.

If the same concept appears in multiple documents, make sure the wording
is consistent while preserving each document's intended scope.

============================================================
16. DATABASE / .DB MODEL
============================================================

Where supported by the actual implementation, document the database as
persistent system state.

Conceptually the database may contain:

    Memory state
    Knowledge state
    Skills
    Tools
    Capabilities
    Providers
    Hands
    configuration
    other persistent state

Do NOT assume all of these are already stored in the database.

Inspect the actual schema first.

Only document implemented database entities as implemented.

============================================================
17. SECURITY BOUNDARY
============================================================

Preserve a strict boundary:

    Model/Hermes
        ↓
    structured Tool request
        ↓
    Brain validation
        ↓
    Capability resolution
        ↓
    Hand validation
        ↓
    physical execution

Do not describe the architecture as allowing:

    arbitrary shell execution
    arbitrary Python execution
    eval
    unrestricted subprocess execution

unless such functionality explicitly exists and is intentionally documented
as a controlled capability.

============================================================
18. DOCUMENTATION AUDIT
============================================================

After making changes, search the entire documentation set for
architectural contradictions.

Search for terms such as:

    "LLM executes"
    "Hermes executes"
    "Brain executes Windows"
    "tool executes shell"
    "terminal = CMD"
    "Memory = capabilities"
    "Knowledge = conversation"
    "Hands reason"
    "Desktop Agent"
    "IPC"
    "remote Hand"
    "capability discovery"

Correct contradictions according to the canonical architecture above.

Do NOT remove historical information if it is legitimately historical.
Move historical/deprecated material to the appropriate historical section
if required by DOCUMENTATION_RULES.md.

============================================================
19. FINAL VALIDATION
============================================================

Before finishing:

1. Inspect actual implementation.
2. Update documentation.
3. Verify CURRENT/PLANNED status.
4. Verify terminology consistency.
5. Verify no invented implementation.
6. Verify no duplicate/conflicting architecture.
7. Run available documentation/architecture tests.
8. Check references and links.
9. Report every changed file.
10. Report remaining architectural gaps.
11. Report any places where the documentation intentionally describes
    target architecture rather than current implementation.

FINAL ARCHITECTURAL MODEL:

    ┌────────────────────────────────────────────┐
    │              SARTHI SERVER                 │
    │                                            │
    │  Model                                      │
    │    │                                       │
    │  Brain ───── deterministic orchestration  │
    │    │                                       │
    │    ├── Memory ── private/user context     │
    │    │                                       │
    │    ├── Knowledge ─ what Sarthi can do     │
    │    │       │                               │
    │    │       ├── Skills                     │
    │    │       ├── Tools                      │
    │    │       ├── Capabilities                │
    │    │       └── Providers/Hands             │
    │    │                                       │
    │    └── Hermes ─ complex orchestration     │
    │                                            │
    └───────────────────┬────────────────────────┘
                        │
                 structured request
                        │
          ┌─────────────┼─────────────┐
          ▼             ▼             ▼
      Desktop Hand   Android Hand   Other Hand
          │             │             │
       Provider       Provider       Provider
          │             │             │
          ▼             ▼             ▼
       Physical/System Execution

Core principle:

    Sarthi thinks deterministically.
    Hermes thinks complexly.
    Knowledge describes what is possible.
    Memory stores private context.
    Skills group capabilities.
    Tools define operations.
    Capabilities describe required abilities.
    Providers implement capabilities.
    Hands execute.

Do not blur these responsibilities.
