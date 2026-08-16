import time

from .models import Task
from .providers.base import ProviderResponse
from .providers.manager import ProviderManager
from .sandbox import TaskSandbox
from .tool_planner import ToolPlanner
from .tool_registry import ToolRegistry


class HermesOrchestrator:
    """
    Hermes is the orchestrator, not a complete handler.

    For every task it:
      1. Runs the Tool Planner (Hermes decides text vs registered Sarthi tool)
      2. Attempts the primary provider, falling back per model call
      3. Records the full execution trace (decision, tool calls, results)
      4. Saves the task to the sandbox, indexed by the user's query, so the
         sandbox is the durable reference for what was asked and how it ran.

    Tool execution is always delegated to the Sarthi Tool Registry — Hermes
    never executes tools itself.
    """

    def __init__(
        self,
        provider_manager: ProviderManager,
        tool_registry: ToolRegistry | None = None,
        sandbox: TaskSandbox | None = None,
    ):
        self._provider_manager = provider_manager
        self._tool_registry = tool_registry
        self._sandbox = sandbox

    def process(self, task: Task) -> ProviderResponse:
        """
        Process a Hermes task through the tool loop with provider fallback,
        then persist the task + execution trace to the sandbox.

        Args:
            task: Task to execute.

        Returns:
            ProviderResponse from primary or fallback provider, with
            tool_used set when a registered Sarthi tool was executed.
        """
        if self._tool_registry is None:
            from .tool_registry import get_tool_registry

            self._tool_registry = get_tool_registry()

        trace: list[dict] = []
        planner = ToolPlanner(self._tool_registry, self._generate_with_fallback, trace=trace)

        started = time.perf_counter()
        response = planner.run(task)
        duration_ms = (time.perf_counter() - started) * 1000

        if self._sandbox is not None:
            self._sandbox.save(task, response, duration_ms, trace=trace)

        return response

    def chat(self, task: Task) -> ProviderResponse:
        """
        Plain conversational generation — NO tool planning, NO tool fetching.

        This is the "natural language processor" path: the model is asked
        directly for a conversational reply, never given the tool registry.
        The task is still saved to the sandbox (indexed by query) like every
        other Hermes execution, so the sandbox stays the single reference.

        Args:
            task: Task whose prompt is the user's message.

        Returns:
            ProviderResponse from primary or fallback provider.
        """
        trace: list[dict] = []

        started = time.perf_counter()
        response = self._generate_with_fallback(task)
        duration_ms = (time.perf_counter() - started) * 1000

        # Record the single chat step so the sandbox trace shows how the
        # reply was produced (provider + model, no tools involved).
        trace.append(
            {
                "step": "chat",
                "provider": response.provider,
                "model": response.model,
                "success": response.success,
                "text": response.text,
                "error": response.error,
            }
        )

        if self._sandbox is not None:
            self._sandbox.save(task, response, duration_ms, trace=trace)

        return response

    def _generate_with_fallback(self, task: Task) -> ProviderResponse:
        """Call the primary provider, falling back to the fallback provider."""
        response = self._provider_manager.generate(task)

        # If primary succeeds, return immediately
        if response.success:
            return response

        # Primary failed, attempt fallback
        print(f"{response.provider} unavailable.")
        print("Preserving task...")
        print("Switching to fallback provider...")

        try:
            fallback_response = self._provider_manager.generate_fallback(task)
            return fallback_response
        except Exception:
            # Fallback failed completely (not initialized or errored)
            # Return a graceful combined failure response
            return ProviderResponse(
                success=False,
                provider="Hermes",
                model="",
                text="",
                error=f"{response.provider} failed ({response.error}) and fallback unavailable",
            )
