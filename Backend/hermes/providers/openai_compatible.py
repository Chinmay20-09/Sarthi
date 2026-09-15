import httpx2

from hermes.config.settings import HermesConfig
from hermes.models import ModelRequest, Task

from .base import AIProvider, ModelCapabilities, ProviderResponse
from .local_provider import _build_messages


class OpenAICompatibleProvider(AIProvider):
    """Generic adapter for any OpenAI-compatible /chat/completions endpoint.

    Works against OpenAI itself and every compatible service (OpenRouter,
    Together, vLLM, LM Studio, llama.cpp server, ...) configured through
    ``openai_compatible_url`` / ``openai_compatible_api_key`` (env:
    ``OPENAI_COMPATIBLE_URL`` / ``OPENAI_COMPATIBLE_API_KEY``).

    Endpoints are NOT assumed to implement every feature — this adapter
    only sends what it is told to send and maps every failure back to a
    graceful ``ProviderResponse``.
    """

    name = "OpenAI-Compatible"
    default_base_url = "https://api.openai.com/v1"

    def __init__(self, config: HermesConfig):
        self._config = config
        # Persistent client for connection pooling — avoids a new TCP
        # handshake on every generate() call.
        self._client = httpx2.Client(timeout=config.timeout)
        self._endpoint = self._resolve_endpoint(config)
        self._api_key = self._resolve_api_key(config)

    # -- Hooks subclasses (e.g. OpenRouter) override -------------------
    def _resolve_endpoint(self, config: HermesConfig) -> str:
        """Full /chat/completions URL for this provider."""
        base = (config.openai_compatible_url or self.default_base_url or "").rstrip("/")
        return f"{base}/chat/completions" if base else ""

    def _resolve_api_key(self, config: HermesConfig) -> str:
        return config.openai_compatible_api_key or config.api_key

    def _requires_api_key(self) -> bool:
        """True when a missing key must fail fast instead of an auth-less call."""
        return False

    def _extra_headers(self) -> dict:
        return {}

    # -- Provider interface -------------------------------------------
    @property
    def model(self) -> str:
        return self._config.model

    def capabilities(self) -> ModelCapabilities:
        """response_format=json_object is honored when structured output is
        requested; native tool schemas are not translated (Hermes uses its
        prompt-based tool protocol), so tool_calling stays off."""
        return ModelCapabilities(
            tool_calling=False,
            structured_output=True,
            vision=False,
            streaming=False,
            context_window=None,
        )

    def generate(self, task_or_request: Task | ModelRequest) -> ProviderResponse:
        """Send one chat completion request. Never raises upward.

        Accepts a Task for legacy direct call sites and normalizes via
        ``as_request``; through the ProviderManager it always receives a
        ModelRequest.
        """
        request = self.as_request(task_or_request)
        if not self._endpoint:
            return ProviderResponse(
                success=False,
                provider=self.name,
                model=self.model,
                text="",
                error="No endpoint configured — set OPENAI_COMPATIBLE_URL",
            )
        if self._requires_api_key() and not self._api_key:
            return ProviderResponse(
                success=False,
                provider=self.name,
                model=self.model,
                text="",
                error="Missing API key",
            )

        try:
            response = self._post(request)
            response.raise_for_status()
            data = response.json()
            message = data["choices"][0]["message"]
            content = message.get("content")
            if content is None:
                # e.g. the model returned a refusal or an unexpected shape
                return ProviderResponse(
                    success=False,
                    provider=self.name,
                    model=self.model,
                    text="",
                    error="Invalid response",
                )
            return ProviderResponse(
                success=True,
                provider=self.name,
                model=self.model,
                text=content,
                usage=data.get("usage"),
            )
        except httpx2.TimeoutException:
            return ProviderResponse(
                success=False,
                provider=self.name,
                model=self.model,
                text="",
                error="Connection timeout",
            )
        except httpx2.HTTPStatusError as exc:
            reason = exc.response.reason_phrase or ""
            message = f"HTTP {exc.response.status_code} {reason}".strip()
            return ProviderResponse(
                success=False,
                provider=self.name,
                model=self.model,
                text="",
                error=message,
            )
        except httpx2.HTTPError as exc:
            return ProviderResponse(
                success=False,
                provider=self.name,
                model=self.model,
                text="",
                error=f"Connection error: {exc}",
            )
        except (KeyError, IndexError, ValueError):
            return ProviderResponse(
                success=False,
                provider=self.name,
                model=self.model,
                text="",
                error="Invalid response",
            )
        except Exception:
            return ProviderResponse(
                success=False,
                provider=self.name,
                model=self.model,
                text="",
                error="Unexpected error",
            )

    def _post(self, request: ModelRequest) -> httpx2.Response:
        """Post to the OpenAI-compatible chat completions endpoint."""
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        headers.update(self._extra_headers())

        payload: dict = {
            "model": self.model,
            "messages": _build_messages(request),
            "stream": False,
        }
        if request.temperature is not None:
            payload["temperature"] = request.temperature
        if request.structured_output and self.capabilities().structured_output:
            payload["response_format"] = {"type": "json_object"}
        return self._client.post(self._endpoint, headers=headers, json=payload)
