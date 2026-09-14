# Agents (observed)

"Agent" here means a component that runs a model-driven loop until a goal is
met. **Three** exist — and only one of them is a Hermes reasoning loop.

> **2026-09-14:** the former `HermesOrchestrator + ToolPlanner` loop was
> removed (DM-012/D-01). `HermesAgent` is the single Hermes reasoning loop;
> `HermesOrchestrator` survives only as provider wiring + the plain-chat path.
> See [ARCHITECTURAL_DECISIONS.md](ARCHITECTURAL_DECISIONS.md) AD-02/AD-03.

## 1. HermesAgent (the production complex-task agent)

| Property | Value |
| --- | --- |
| Location | `hermes/agent.py` |
| Trigger | api.py complexity fallback → `hermes.service.run_task` |
| Loop | fast path (deterministic) → retrieval → N model turns (parse tool call → validate → execute → feed back) |
| Bounds | `HERMES_AGENT_MAX_ITERATIONS` (default 5), `HERMES_AGENT_TIMEOUT` (default 300 s) |
| Tools | the 10 registered tools (TOOLS.md) |
| Outputs | result dict + sandbox persistence (`agent_*` task ids) |
| Lifecycle | constructed per task from config (`get_agent`); engine singleton for fast path |
| Tests | test_hermes_agent, test_hermes_pipeline_integration |

## 2. HermesOrchestrator (provider wiring + plain chat — NOT a loop)

| Property | Value |
| --- | --- |
| Location | `hermes/orchestrator.py` |
| Trigger | `hermes.service.chat` (conversation mode + NLP fallback), `POST /hermes/chat`, `hermes/main.py` |
| `process(task)` | Delegates to `HermesAgent` (the one loop) with the fast path disabled, then maps the result to a `ProviderResponse` |
| `chat(task)` | Plain conversational call: no tool planning, no tool fetching, no loop; still sandbox-recorded |
| Responsibilities | provider manager + primary/local fallback (shared by both paths) |
| Tests | test_fallback, test_fallback_integration, test_hermes_api, test_sandbox_query_index |

## 3. BrainAssistant (automation engine)

| Property | Value |
| --- | --- |
| Location | `skills/automation_engine/assistants/brain_assistant/` |
| Trigger | `AutomationSkill._handle_generate` ("generate assistant for <skill>") |
| Responsibilities | Read-only skill analysis → generates `assistant.json` from manifest.json |
| Tools | none (filesystem read/write of assistant.json only) |
| Outputs | assistant.json path |
| Status | the generator works (smoke test). The non-functional `analyze` command was removed in the 2026-09-14 pass; `assistants/brain_assistant/analyzer.py` is unreachable and listed as a removal candidate |
| Tests | test_brain_assistant |

## 4. Browser Awareness manager loop

| Property | Value |
| --- | --- |
| Location | `skills/browser_awareness/manager.py` |
| Trigger | `browse` intent (executor) or browser_ask tool |
| Loop | open isolated Chrome → DOM snapshot → Hermes inspector observes → recommendation → schema validation → executor acts → re-inspect; until done/blocked/step limit |
| Tools | none (its own executor + inspector interfaces) |
| Outputs | InspectionResult; spoken progress via utils.voice |
| Tests | test_browser_awareness |

## Not an agent (for clarity)

- `BrainEngine` — deterministic pipeline, no model, no loop.
- `hermes/providers/*` — stateless adapters.
- `speech/` — recording/STT utilities.
