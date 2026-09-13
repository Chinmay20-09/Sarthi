# Sarthi Documentation

Documentation for Sarthi, a local-first AI desktop assistant. Every document
in this tree describes **observed** behaviour — derived from the code in this
repository, not from plans or claims.

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
| [TESTING.md](TESTING.md) | Test suite reality check |
| [DIVERGENCE.md](DIVERGENCE.md) | Architectural inconsistencies (evidence-based) |
| [DUPLICATION.md](DUPLICATION.md) | Overlapping responsibilities |
| [DEAD_CODE.md](DEAD_CODE.md) | Suspected dead/orphaned systems |
| [PROJECT_STATE.md](PROJECT_STATE.md) | Current implementation state |
| [DOCUMENTATION_RULES.md](DOCUMENTATION_RULES.md) | Rules this documentation follows |
| [FORENSIC_SUMMARY.md](FORENSIC_SUMMARY.md) | Counts, findings, top risks |

Historical documents (pre-reset) are preserved in `docs/archive/`.
