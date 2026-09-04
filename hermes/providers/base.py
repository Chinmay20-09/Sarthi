from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from hermes.models import ModelRequest, Task


@dataclass
class ProviderResponse:
    """Normalized provider answer — the ONLY object Hermes receives back.

    Every provider adapter (Ollama, OpenRouter, any OpenAI-compatible
    endpoint, ...) maps its own wire response into this shape, so Hermes
    core never sees provider-specific payloads.

    Fields:
        success: True when the model call produced a usable answer.
        provider: Human-readable provider name (e.g. "Ollama").
        model: Model name that actually answered.
        text: The generated text (empty on failure).
        error: Failure reason (empty on success).
        tool_used: Name of the Sarthi tool executed for this reply (set by
            the Tool Planner when Hermes requested a registered tool).
        data: Parsed structured output, when the caller asked for it and
            the provider/model honored the request.
        usage: Token usage reported by the provider, when available.
        raw: Provider-specific payload, kept only for diagnostics.
    """

    success: bool
    provider: str
    model: str
    text: str
    error: str = ""
    # Name of the Sarthi tool that was executed to produce this response
    # (set by the Tool Planner when Hermes requested a registered tool).
    tool_used: str | None = None
    # Parsed structured output when structured output was requested.
    data: dict[str, Any] | None = None
    # Token usage reported by the provider, when available.
    usage: dict[str, Any] | None = None
    # Provider-specific payload for diagnostics; never parsed by Hermes.
    raw: dict[str, Any] | None = None


@dataclass
class ModelCapabilities:
    """What a configured provider adapter + model actually supports.

    Capabilities describe what the *adapter* honors over the wire, not
    what the upstream API could theoretically do. Hermes core uses this to
    degrade gracefully (e.g. never send images to a non-vision model,
    rely on prompt-based tool calls when native tool calling is off).

    Defaults are conservative: an adapter declares a capability only when
    it implements it.
    """

    tool_calling: bool = False
    structured_output: bool = False
    vision: bool = False
    streaming: bool = False
    context_window: int | None = None


class AIProvider(ABC):
    """Abstract base class for all model providers.

    A provider adapter maps a provider-neutral ``ModelRequest`` into the
    provider's own wire format and maps the provider's response back into
    a ``ProviderResponse``. Hermes core only ever talks to this interface
    — swapping models/providers is a configuration change, not a code
    change.

    Compatibility note: adapters accept ``Task`` as well as
    ``ModelRequest`` (``generate`` normalizes via ``as_request``) so
    legacy direct call sites — tests, browser-awareness inspectors — keep
    working unchanged.
    """

    name: str = ""

    @abstractmethod
    def generate(self, request: ModelRequest) -> ProviderResponse:
        """Generate a response for the provider-neutral request."""
        ...

    def capabilities(self) -> ModelCapabilities:
        """Capabilities of this adapter + configured model.

        Subclasses override to declare what they implement. The default
        declares nothing, which is the safe answer: Hermes then uses its
        built-in prompt-based tool protocol and parsing fallbacks.
        """
        return ModelCapabilities()

    @property
    def model(self) -> str:
        """Effective model name this provider is configured to call."""
        return getattr(self, "_model", "") or self.name

    @staticmethod
    def as_request(task_or_request: Task | ModelRequest) -> ModelRequest:
        """Normalize a Task or ModelRequest into a ModelRequest.

        Adapters call this at the top of ``generate`` so both the
        orchestration path (ModelRequest) and legacy direct call sites
        (Task) converge on one provider-neutral request.
        """
        if isinstance(task_or_request, ModelRequest):
            return task_or_request
        if isinstance(task_or_request, Task):
            return task_or_request.to_request()
        raise TypeError(f"Expected Task or ModelRequest, got {type(task_or_request).__name__}")
