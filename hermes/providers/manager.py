from hermes.models import Task

from .base import AIProvider, ProviderResponse
from .exceptions import ProviderUnavailable


class ProviderManager:
    """Initializes a provider and delegates generate() calls to it."""

    def __init__(self):
        self._provider: AIProvider | None = None
        self._fallback_provider: AIProvider | None = None

    def initialize(self, provider: AIProvider) -> None:
        """Set the active provider instance."""
        self._provider = provider

    def set_fallback(self, provider: AIProvider) -> None:
        """Set the fallback provider for when primary fails."""
        self._fallback_provider = provider

    def generate(self, task: Task) -> ProviderResponse:
        """Delegate response generation to the current provider."""
        if self._provider is None:
            raise ProviderUnavailable("No provider has been initialized.")
        return self._provider.generate(task)

    def generate_fallback(self, task: Task) -> ProviderResponse:
        """Generate using fallback provider."""
        if self._fallback_provider is None:
            raise ProviderUnavailable("No fallback provider has been initialized.")
        return self._fallback_provider.generate(task)
