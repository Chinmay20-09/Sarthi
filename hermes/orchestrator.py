from .models import Task
from .providers.base import ProviderResponse
from .providers.manager import ProviderManager


class HermesOrchestrator:
    """
    Coordinates Hermes task execution.

    Responsibilities (V1):
    - Accept a Task
    - Forward it to the ProviderManager
    - Return the ProviderResponse

    Future responsibilities:
    - Cloud/Local routing
    - Offline queue
    - Retry logic
    - Validation
    - Notifications
    """

    def __init__(self, provider_manager: ProviderManager):
        self._provider_manager = provider_manager

    def process(self, task: Task) -> ProviderResponse:
        """
        Process a Hermes task.

        Args:
            task: Task to execute.

        Returns:
            ProviderResponse
        """

        return self._provider_manager.generate(task)
