"""
Hermes service layer — shared wiring for the orchestrator and sandbox.

Both the HTTP routes (hermes/routes.py) and the Natural Language Processor
skill build their orchestrator here, so provider configuration lives in
exactly one place. Provider selection is config-driven through
hermes/providers/registry.py — no concrete provider is imported here.

Public helpers:
    get_orchestrator()    — singleton HermesOrchestrator wired from config
                             (local-only, OpenRouter + local fallback, or
                             OpenAI-compatible + local fallback).
    get_sandbox()         — the shared TaskSandbox every task is saved to.
    chat(message)         — plain conversational reply. NO tool planning, NO
                             tool fetching — the model is asked directly.
    route_command(text)   — the fast/complex gate (Phase 3a router, with
                             config knobs applied).
    run_task(query)       — the complex path: bounded Hermes agent loop
                             (Phase 3d) with retrieval + validated tools.
    get_provider_status() — diagnostic snapshot of the active provider stack.
"""

from knowledge.memory import build_memory_prompt

from hermes.agent import HermesAgent
from hermes.config.loader import ConfigLoader
from hermes.conversation import DEFAULT_SESSION, get_conversation_store
from hermes.models import Task
from hermes.orchestrator import HermesOrchestrator
from hermes.providers.base import ProviderResponse
from hermes.providers.registry import build_provider_manager, provider_status
from hermes.sandbox import TaskSandbox

_orchestrator: HermesOrchestrator | None = None
_sandbox: TaskSandbox | None = None
_agent = None


def get_sandbox() -> TaskSandbox:
    """Get the shared TaskSandbox (single reference for every task)."""
    global _sandbox
    if _sandbox is None:
        _sandbox = TaskSandbox(ConfigLoader().load().sandbox_path)
    return _sandbox


def get_orchestrator() -> HermesOrchestrator:
    """Get the shared HermesOrchestrator, configured once and reused.

    The provider stack (primary + local fallback) is chosen entirely from
    ``HERMES_PROVIDER`` and friends — changing the model/provider is a
    configuration change, never a code change.
    """
    global _orchestrator
    if _orchestrator is None:
        config = ConfigLoader().load()
        manager = build_provider_manager(config)
        _orchestrator = HermesOrchestrator(manager, sandbox=get_sandbox())
    return _orchestrator


def get_provider_status() -> dict:
    """Diagnostic snapshot: configured provider/model and what is active."""
    config = ConfigLoader().load()
    return provider_status(config, manager=get_orchestrator().provider_manager)


def chat(message: str, session_id: str | None = None) -> ProviderResponse:
    """
    Plain conversational generation — no tool planning, no tool fetching.

    The model is asked directly for a reply (primary provider, local
    fallback), and the task is saved to the sandbox indexed by query.
    Prior turns from the session are attached as history so Hermes
    remembers the conversation; the new user + assistant turns are then
    recorded back into the session store.

    Args:
        message: The user's message.
        session_id: Optional conversation session. Defaults to a shared
            session so history works even without a client-supplied id.

    Returns:
        ProviderResponse from primary or fallback provider.
    """
    store = get_conversation_store()
    session_id = session_id or DEFAULT_SESSION
    history = store.get_history(session_id)

    # Inject /remember facts as a system message so the model remembers them.
    task = Task(
        prompt=message,
        task_type="chat",
        history=history,
        memory=build_memory_prompt(),
    )
    response = get_orchestrator().chat(task)

    store.add_turn(session_id, "user", message)
    if response.success and response.text:
        store.add_turn(session_id, "assistant", response.text)

    return response


# ----------------------------------------------------------------------
# Complex-task path (Phase 3g): router → agent
# ----------------------------------------------------------------------


def route_command(text: str):
    """Classify one command for the fast/complex gate (config-aware).

    Returns a hermes.router.Route with the config knobs applied.
    """
    from hermes.router import route_command as _route

    route = _route(text)

    # Router knobs (Phase 3f): mode override + minimum complexity score.
    config = ConfigLoader().load()
    mode = getattr(config, "router_mode", "auto")
    min_score = getattr(config, "router_min_score", 1)

    if mode == "always":
        route.route = "hermes"
        route.reason = "router_mode_always"
    elif mode == "off":
        route.route = "fast"
        route.reason = "router_mode_off"
    elif route.score < min_score:
        route.route = "fast"
        route.reason = "below_min_score"

    return route


def run_task(
    query: str,
    session_id: str | None = None,
    *,
    allow_fast_path: bool = True,
) -> dict:
    """Execute a complex task through the bounded Hermes agent loop.

    This is the complex-path entry point for callers that have already
    decided (or want the agent to decide) that Hermes should handle the
    request. The agent still tries the deterministic pipeline first, so a
    misrouted simple command costs nothing.

    Args:
        query: The user's request.
        session_id: Optional conversation session for history/memory.
        allow_fast_path: When False, the agent skips the deterministic
            shortcut entirely. Set by the /command gate for requests whose
            deterministic reading is known to be wrong (a task-shaped
            sentence the interpreter can only mis-read as a web search), so
            Hermes reasons about the request instead of re-running the same
            literal action.

    Returns:
        Agent result dict: {success, text, tool_used, iterations,
        duration_ms, timed_out, route, reason, provider, model, trace}.
    """
    config = ConfigLoader().load()
    agent = HermesAgent(
        sandbox=get_sandbox(),
        fast_path=None if allow_fast_path else False,
        max_iterations=getattr(config, "agent_max_iterations", 3),
        timeout_seconds=getattr(config, "agent_timeout", 300.0),
    )
    return agent.run(query, session_id=session_id)
