from .models import Task
from .providers.base import ProviderResponse
from .providers.manager import ProviderManager
from .tool_planner import ToolPlanner
from .tool_registry import ToolRegistry


class HermesOrchestrator:
    """
    Coordinates Hermes task execution.

    Responsibilities:
    - Accept a Task
    - Run the Tool Planner (Hermes decides text vs registered Sarthi tool)
    - Attempt primary provider, then fallback provider for each model call
    - Return the ProviderResponse

    Hermes is the reasoning layer only — tool execution is delegated to the
    Sarthi Tool Registry, never executed directly by Hermes.
    """

    def __init__(self, provider_manager: ProviderManager, tool_registry: ToolRegistry | None = None):
        self._provider_manager = provider_manager
        self._tool_registry = tool_registry

    def process(self, task: Task) -> ProviderResponse:
        """
        Process a Hermes task through the tool loop with provider fallback.

        Args:
            task: Task to execute.

        Returns:
            ProviderResponse from primary or fallback provider, with
            tool_used set when a registered Sarthi tool was executed.
        """
        if self._tool_registry is None:
            from .tool_registry import get_tool_registry

            self._tool_registry = get_tool_registry()

        planner = ToolPlanner(self._tool_registry, self._generate_with_fallback)
        return planner.run(task)

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
