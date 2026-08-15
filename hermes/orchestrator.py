from .models import Task
from .providers.base import ProviderResponse
from .providers.manager import ProviderManager


class HermesOrchestrator:
    """
    Coordinates Hermes task execution.

    Responsibilities:
    - Accept a Task
    - Attempt primary provider
    - If primary fails, attempt fallback provider
    - Return the ProviderResponse

    Future responsibilities:
    - Offline queue
    - Retry logic
    - Validation
    - Notifications
    """

    def __init__(self, provider_manager: ProviderManager):
        self._provider_manager = provider_manager

    def process(self, task: Task) -> ProviderResponse:
        """
        Process a Hermes task with fallback support.

        Attempts primary provider first. If it fails (success=False),
        attempts fallback provider with the original task.

        Args:
            task: Task to execute.

        Returns:
            ProviderResponse from primary or fallback provider.
        """
        # Try primary provider
        response = self._provider_manager.generate(task)

        # If primary succeeds, return immediately
        if response.success:
            return response

        # Primary failed, attempt fallback
        print("Cloud provider unavailable.")
        print("Preserving task...")
        print("Switching to local fallback...")
        
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
                error=f"Cloud provider failed ({response.error}) and local fallback unavailable",
            )

