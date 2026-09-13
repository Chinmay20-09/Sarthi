# Agents (observed)

"Agent" here means a component that runs a model-driven loop until a goal is
met. Four exist.

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

## 2. HermesOrchestrator + ToolPlanner (task processor)

| Property | Value |
| --- | --- |
| Location | `hermes/orchestrator.py`, `hermes/tool_planner.py` |
| Trigger | `POST /hermes/chat` (routes.py:275), Hermes `main.py`; also underlies NLP skill's provider calls |
| Loop | Task → ToolPlanner decision (final answer vs tool call) → ProviderManager (primary + local fallback) → sandbox save; bounded by MAX_TOOL_CALLS_PER_TASK=5 |
| Tools | same ToolRegistry |
| Outputs | ProviderResponse + sandbox task (`chat_*`/`task_*` ids) |
| Tests | test_fallback, test_provider_abstraction, test_hermes_api |

## 3. BrainAssistant (automation engine)

| Property | Value |
| --- | --- |
| Location | `skills/automation_engine/assistants/brain_assistant/` |
| Trigger | `AutomationSkill._handle_generate` ("generate assistant for <skill>") |
| Responsibilities | Read-only skill analysis → generates `assistant.json` from manifest.json |
| Tools | none (filesystem read/write of assistant.json only) |
| Outputs | assistant.json path |
| Status | analyzer works (smoke test); `analyze` command path is a stub returning empty capabilities (skill.py:171-180) |
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
