from hermes.models import ModelRequest, Task

from .base import AIProvider, ModelCapabilities, ProviderResponse
from .exceptions import ProviderUnavailable


class ProviderManager:
    """Initializes a provider and delegates generate() calls to it.

    The manager is the single boundary where Hermes orchestration (which
    works in ``Task``/``ModelRequest`` terms) meets provider adapters
    (which only ever receive a ``ModelRequest``). Whatever is handed in —
    a ``Task`` from the orchestrator or a ``ModelRequest`` built by the
    Tool Planner — is normalized before it reaches the adapter, so no
    provider sees orchestration metadata (task ids, context, ...).
    """

    def __init__(self):
        self._provider: AIProvider | None = None
        self._fallback_provider: AIProvider | None = None

    def initialize(self, provider: AIProvider) -> None:
        """Set the active provider instance."""
        self._provider = provider

    def set_fallback(self, provider: AIProvider) -> None:
        """Set the fallback provider for when primary fails."""
        self._fallback_provider = provider

    @property
    def primary(self) -> AIProvider | None:
        """The active provider instance."""
        return self._provider

    @property
    def fallback(self) -> AIProvider | None:
        """The fallback provider instance, if any."""
        return self._fallback_provider

    @staticmethod
    def _as_request(task_or_request: Task | ModelRequest) -> ModelRequest:
        """Normalize whatever the orchestrator handed in to a ModelRequest."""
        if isinstance(task_or_request, ModelRequest):
            return task_or_request
        if isinstance(task_or_request, Task):
            return task_or_request.to_request()
        raise TypeError(f"Expected Task or ModelRequest, got {type(task_or_request).__name__}")

    def capabilities(self) -> ModelCapabilities:
        """Capabilities of the active provider (empty when uninitialized)."""
        if self._provider is None:
            return ModelCapabilities()
        return self._provider.capabilities()

    def generate(self, task_or_request: Task | ModelRequest) -> ProviderResponse:
        """Delegate response generation to the current provider."""
        if self._provider is None:
            raise ProviderUnavailable("No provider has been initialized.")
        return self._provider.generate(self._as_request(task_or_request))

    def generate_fallback(self, task_or_request: Task | ModelRequest) -> ProviderResponse:
        """Generate using fallback provider."""
        if self._fallback_provider is None:
            raise ProviderUnavailable("No fallback provider has been initialized.")
        return self._fallback_provider.generate(self._as_request(task_or_request))
