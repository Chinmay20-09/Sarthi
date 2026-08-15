from abc import ABC, abstractmethod
from dataclasses import dataclass

from hermes.models import Task


@dataclass
class ProviderResponse:
    success: bool
    provider: str
    model: str
    text: str
    error: str = ""
    # Name of the Sarthi tool that was executed to produce this response
    # (set by the Tool Planner when Hermes requested a registered tool).
    tool_used: str | None = None


class AIProvider(ABC):
    """Abstract base class for all AI providers."""

    name: str = ""

    @abstractmethod
    def generate(self, task: Task) -> ProviderResponse:
        """Generate a response for the given task."""
        ...
