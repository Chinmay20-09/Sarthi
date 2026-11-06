import httpx2

from hermes.config.settings import HermesConfig
from hermes.models import ModelRequest, Task

from .base import AIProvider, ModelCapabilities, ProviderResponse, ProviderStreamEvent
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

    Streaming: the provider adapter speaks the protocol the server is
    configured for.  ``stream: true`` tells the upstream that the client
    understands application/x-ndjson streams of ``{"token": "..."}``,
    one object per line; each arriving token is normalized into a
    ``ProviderStreamEvent(token, ...)`` and forwarded to the transport as
    an SSE event.  When the connection drops mid-stream the call still
    resolves with a valid ``ProviderResponse``, and when the server
    answers the legacy shape (no token lines at all) the call falls back
    to the synchronous non-streaming path so behaviour is unchanged for
    providers that ignore the streaming flag.
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
            if self._config.streaming:
                events = self._post_stream(self._build_headers(), self._build_payload(request))
                text = "".join(event.data.get("text", "") for event in events if event.event == "token")
                if events and events[0].event == "error":
                    return ProviderResponse(
                        success=False,
                        provider=self.name,
                        model=self.model,
                        text="",
                        error=events[0].data.get("message", "Connection error"),
                    )
                return ProviderResponse(
                    success=bool(text),
                    provider=self.name,
                    model=self.model,
                    text=text,
                    usage=None,
                )
            response = self._post(request)
            response.raise_for_status()
            data = response.json()
            message = data["choices"][0]["message"]
            content = message.get("content")
            if content is None:
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

    def _build_headers(self) -> dict:
        """Headers for a streaming POST (reuses the existing key/auth logic)."""
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        headers.update(self._extra_headers())
        return headers

    def _build_payload(self, request: ModelRequest) -> dict:
        """Payload for a streaming POST (stream flag negotiated by the config)."""
        payload: dict = {
            "model": self.model,
            "messages": _build_messages(request),
        }
        if self._config.streaming:
            payload["stream"] = True
        elif self._config.streaming is None:
            payload["stream"] = False
        if request.temperature is not None:
            payload["temperature"] = request.temperature
        if request.structured_output and self.capabilities().structured_output:
            payload["response_format"] = {"type": "json_object"}
        return payload

    def _post_stream(
        self, headers: dict, payload: dict
    ) -> list[ProviderStreamEvent]:
        """Native streaming POST with server-sent events.

        The server is expected to send application/x-ndjson: one JSON object
        per line, ``{"token": "..."}`` for incremental text.  Each token is
        normalized into a ``ProviderStreamEvent`` and forwarded to the
        transport as an SSE event.  When the connection drops mid-stream
        the call still resolves with a valid ``ProviderResponse``.
        """
        try:
            with self._client.stream(
                "POST",
                self._endpoint,
                headers=headers,
                json=payload,
                timeout=self._config.timeout,
            ) as response:
                response.raise_for_status()
                events: list[ProviderStreamEvent] = []
                with response.iter_lines(chunk_size=1024, delimiter="\n") as lines:
                    for line in lines:
                        if not line.strip():
                            continue
                        try:
                            obj = json.loads(line.decode("utf-8"))
                        except (UnicodeDecodeError, json.JSONDecodeError):
                            continue
                        if obj.get("token") is not None:
                            events.append(
                                ProviderStreamEvent(
                                    event="token",
                                    data={"text": obj["token"]},
                                )
                            )
                        elif obj.get("error") is not None:
                            return [
                                ProviderStreamEvent(
                                    event="error",
                                    data={"message": obj["error"], "recoverable": False},
                                )
                            ]
                if events:
                    return events
                # No token lines at all — the server answered the legacy
                # shape; fall through to the synchronous path so the
                # behaviour is unchanged for any provider that ignores the
                # streaming flag.
                data = response.json()
                message = data["choices"][0]["message"]
                content = message.get("content")
                if content is None:
                    return [
                        ProviderStreamEvent(
                            event="error",
                            data={"message": "Invalid response", "recoverable": False},
                        )
                    ]
                return [
                    ProviderStreamEvent(
                        event="done",
                        data={
                            "text": content,
                            "provider": self.name,
                            "model": self.model,
                            "success": True,
                        },
                    )
                ]
        except httpx2.TimeoutException:
            return [
                ProviderStreamEvent(
                    event="error",
                    data={"message": "Connection timeout", "recoverable": True},
                )
            ]
        except httpx2.HTTPStatusError as exc:
            reason = exc.response.reason_phrase or ""
            message = f"HTTP {exc.response.status_code} {reason}".strip()
            return [
                ProviderStreamEvent(
                    event="error",
                    data={"message": message, "recoverable": False},
                )
            ]
        except httpx2.HTTPError as exc:
            return [
                ProviderStreamEvent(
                    event="error",
                    data={"message": f"Connection error: {exc}", "recoverable": True},
                )
            ]
        except Exception:
            return [
                ProviderStreamEvent(
                    event="error",
                    data={"message": "Unexpected error", "recoverable": False},
                )
            ]

    async def generate_stream(
        self, request: ModelRequest
    ) -> AsyncIterator[ProviderStreamEvent]:
        """Serve events. The synchronous iterator is used for both legacy
        streaming-capable providers and providers that only speak the
        token-per-line /token JSON hint; the async wrapper is kept so the
        abstract interface remains awaitable by callers that adopt it.
        """
        for event in self._post_stream(self._build_headers(), self._build_payload(request)):
            yield event
