# Sarthi Documentation

Documentation for Sarthi, a local-first AI desktop assistant. Every document
in this tree describes **observed** behaviour — derived from the code in this
repository, not from plans or claims.

## Canonical model (read this first)

Sarthi's canonical architecture — defined once in
[ARCHITECTURE.md](ARCHITECTURE.md#canonical-terminology-map) and used
consistently everywhere in this tree:

- **Sarthi Brain** — the deterministic orchestrator. Prefers known, validated
  capability paths (deterministic-first principle).
- **Hermes** — the complex/model-driven orchestrator. An escalation path for
  complexity and missing deterministic routes, never the default executor and
  never a physical executor. The model is a component Hermes uses.
- **Skills** group related capability-oriented behaviour; **Tools** are
  specific structured operations; **Capabilities** are abstract abilities;
  **Providers** are concrete implementations of a capability; **Hands** are
  the execution layers that receive validated structured requests and perform
  physical operations. Neither Sarthi nor Hermes executes anything directly.
- **Memory** is private/user context (conversations, preferences, state);
  **Knowledge** is what Sarthi knows about its available capabilities.
- CURRENT vs PLANNED: the Sarthi-Server runtime, remote Hands (Android,
  Browser, IoT), Brain↔Hand IPC and capability/provider discovery are
  **PLANNED** (see PROJECT_STATE.md); today's implementation is the local
  Desktop Hand behind the `Hand` interface.

## Document index

| Document | Contents |
| --- | --- |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Observed architecture: layers, packages, dependency rules |
| [RUNTIME_FLOW.md](RUNTIME_FLOW.md) | What happens from input to response, step by step |
| [MODULE_MAP.md](MODULE_MAP.md) | Every package, what lives there, who calls it |
| [DATA_FLOW.md](DATA_FLOW.md) | Data structures that cross component boundaries |
| [CAPABILITIES.md](CAPABILITIES.md) | What Sarthi can currently do (capability inventory) |
| [SKILLS.md](SKILLS.md) | The 10 registered skills |
| [TOOLS.md](TOOLS.md) | The 10 Hermes tools (Sarthi Tool Bridge) |
| [AGENTS.md](AGENTS.md) | Agent loops and assistants |
| [AUTOMATION.md](AUTOMATION.md) | The automation engine (assistant generation) |
| [CHAINING.md](CHAINING.md) | AI chaining (ChatGPT → Gemini laptop automation) |
| [BROWSER_AUTOMATION.md](BROWSER_AUTOMATION.md) | The two browser automation stacks |
| [KNOWLEDGE.md](KNOWLEDGE.md) | Applications/websites knowledge layer + entity resolution |
| [MEMORY.md](MEMORY.md) | Long-term memory, conversation history, retrieval |
| [DATABASE.md](DATABASE.md) | SQLite schema, sandbox storage, all persistent state |
| [API.md](API.md) | Every HTTP endpoint |
| [CLI.md](CLI.md) | Entry points and command-line interfaces |
| [CONFIGURATION.md](CONFIGURATION.md) | Config files, environment variables, settings table |
| [DEPENDENCIES.md](DEPENDENCIES.md) | Dependency audit |
| [TESTING.md](TESTING.md) | Test suite reality check (incl. per-file voice feedback) |
| [DIVERGENCE.md](DIVERGENCE.md) | Architectural inconsistencies + post-consolidation status (evidence-based) |
| [DEAD_CODE&Duplicate.md](DEAD_CODE&Duplicate.md) | Dead/orphaned systems + overlapping responsibilities |
| [PROJECT_STATE.md](PROJECT_STATE.md) | Current implementation state |
| [ARCHITECTURAL_DECISIONS.md](ARCHITECTURAL_DECISIONS.md) | Decision log (problem, evidence, choice, rejected alternatives, risk, tests) |
| [CONSOLIDATION_PLAN.md](CONSOLIDATION_PLAN.md) | Pre-change plan and observations for the consolidation pass |
| [CONSOLIDATION_REPORT.md](CONSOLIDATION_REPORT.md) | What the consolidation changed, before/after, remaining divergence |
| [DOCUMENTATION_RULES.md](DOCUMENTATION_RULES.md) | Rules this documentation follows |
| [FORENSIC_SUMMARY.md](FORENSIC_SUMMARY.md) | Counts, findings, top risks |

Historical documents (pre-reset) are preserved in `docs/archive/`.
