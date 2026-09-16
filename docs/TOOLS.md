# Tools (observed)

The **Sarthi Tool Bridge**: tools the Hermes agent may request. Only tools
registered in `hermes/tool_registry.py` can execute; `register_default_tools`
(`hermes/tools/__init__.py`) registers exactly these 10. Every tool delegates
to an existing Sarthi capability — none expose shell/code execution. Arguments
are validated (`tool_registry.validate_arguments`) and every call passes the
`hermes/validator.py` gate before dispatch.

> **Canonical definition.** A Tool is a specific structured operation exposed
> to the orchestrator — name, purpose, parameters, required capability,
> execution semantics. Tools are NOT arbitrary code execution. Example
> (conceptual shape, matching the real open_app tool): the model requests
> `open_app` with `{"app": "chrome"}`; the validator gates the call, the
> registry dispatches, and the tool delegates to the AppLauncherSkill —
> the orchestrator (Brain/Hermes) remains responsible for validation and
> routing, and the model never runs anything itself.

| # | Tool | Location | Delegates to | Purpose | Side effects | Tests |
| - | ---- | -------- | ------------ | ------- | ------------ | ---- |
| 1 | open_app | hermes/tools/open_app.py | AppLauncherSkill | Launch an application | launches app | test_hermes_tools |
| 2 | open_website | hermes/tools/open_website.py | BrowserSkill (+webbrowser fallback for raw URLs) | Open a website | opens browser tab | test_hermes_tools |
| 3 | close_app | hermes/tools/close_app.py | executor close path / DesktopHand | Terminate an application | kills process | test_hermes_tools |
| 4 | search_web | hermes/tools/search_web.py | BrowserSkill search | Web search in browser | opens browser tab | test_hermes_tools |
| 5 | browser_ask | hermes/tools/browser_ask.py | BrowserAwarenessSkill | High-level objective on a website, DOM-aware | drives isolated Chrome | test_hermes_tools |
| 6 | history_search | hermes/tools/history_search.py | command_history table | Search past commands | none | test_hermes_tools |
| 7 | memory_search | hermes/tools/memory_search.py | knowledge_memory (/remember facts) | Recall user memories | none | test_hermes_tools |
| 8 | project_get | hermes/tools/project_get.py | projects/github_projects tables | Fetch user project context | none | test_hermes_tools |
| 9 | github | hermes/tools/github.py | project_tracker github client | GitHub data for configured username | network read | test_hermes_tools |
| 10 | personal_context | hermes/tools/personal_context.py | personal_context skill | Personal context fields | none | test_hermes_tools |

## Mechanics

- The LLM sees `name`/`description`/`parameters` (JSON-schema subset) via
  `build_decision_instructions` (`hermes/tool_planner.py`).
- Model output is parsed by `parse_tool_call`; a `tool_call` object triggers
  validation (`hermes/validator.py`, the only gate) → execution → follow-up
  prompt; plain text ends the task.
- Hard caps: **3 iterations** (default `HERMES_AGENT_MAX_ITERATIONS`) and
  300 s wall clock. A refused tool call is fed back to the model exactly once.

## One loop, one protocol

`hermes/agent.py` (HermesAgent) is the **only** model-driven tool loop;
`POST /hermes/chat` and the `/command` complex fallback both run it
(`HermesOrchestrator.process` delegates). `hermes/tool_planner.py` is the
shared tool-call *protocol* — the decision/follow-up prompts and
`parse_tool_call` — with no loop of its own. The former parallel ToolPlanner
loop was removed; see [ARCHITECTURAL_DECISIONS.md](ARCHITECTURAL_DECISIONS.md)
AD-02/AD-03.
