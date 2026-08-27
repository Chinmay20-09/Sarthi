"""
Hermes service layer — shared wiring for the orchestrator and sandbox.

Both the HTTP routes (hermes/routes.py) and the Natural Language Processor
skill build their orchestrator here, so provider configuration lives in
exactly one place.

Public helpers:
    get_orchestrator() — singleton HermesOrchestrator (OpenRouter primary,
                         local Ollama fallback, or explicit local-only).
    get_sandbox()      — the shared TaskSandbox every task is saved to.
    chat(message)      — plain conversational reply. NO tool planning, NO
                         tool fetching — the model is asked directly.
"""

from hermes.config.loader import ConfigLoader
from hermes.conversation import DEFAULT_SESSION, get_conversation_store
from hermes.models import Task
from hermes.orchestrator import HermesOrchestrator
from hermes.providers.base import ProviderResponse
from hermes.providers.local_provider import LocalHermesProvider
from hermes.providers.manager import ProviderManager
from hermes.providers.openrouter_provider import OpenRouterProvider
from hermes.sandbox import TaskSandbox
from knowledge.memory import build_memory_prompt

_orchestrator: HermesOrchestrator | None = None
_sandbox: TaskSandbox | None = None


def get_sandbox() -> TaskSandbox:
    """Get the shared TaskSandbox (single reference for every task)."""
    global _sandbox
    if _sandbox is None:
        _sandbox = TaskSandbox(ConfigLoader().load().sandbox_path)
    return _sandbox


def get_orchestrator() -> HermesOrchestrator:
    """Get the shared HermesOrchestrator, configured once and reused."""
    global _orchestrator
    if _orchestrator is None:
        config = ConfigLoader().load()
        manager = ProviderManager()

        provider_name = (config.provider or "openrouter/free").lower()
        explicit_local = provider_name in ("local", "local_hermes", "localhermes")

        if explicit_local:
            # Explicit local mode: local provider only, no fallback
            manager.initialize(LocalHermesProvider(config))
        else:
            # Default mode: OpenRouter primary with local fallback
            manager.initialize(OpenRouterProvider(config))
            manager.set_fallback(LocalHermesProvider(config))

        _orchestrator = HermesOrchestrator(manager, sandbox=get_sandbox())
    return _orchestrator


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
