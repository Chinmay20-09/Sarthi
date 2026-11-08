import logging

import httpx2

from hermes.config.settings import HermesConfig
from hermes.config.model_profiles import DEFAULT_MODEL_PROFILE, MODEL_PROFILES
from hermes.models import ModelRequest, Task

from .base import AIProvider, ModelCapabilities, ProviderResponse, ProviderStreamEvent

logger = logging.getLogger(__name__)


class LocalHermesProvider(AIProvider):
    """Ollama adapter: maps ModelRequest onto Ollama's /api/chat wire format.

    The only provider-specific code in the file is the Ollama request
    building and response parsing below — swap the configured provider and
    this class is never referenced by Hermes core.
    """

    name = "Ollama"

    def __init__(self, config: HermesConfig):
        self._config = config
        # Persistent client for connection pooling — avoids a new TCP
        # handshake on every generate() call.
        # CPU-only inference on large models can take 60-120s+, so we use
        # a dedicated, longer timeout for the local provider.
        local_timeout = getattr(config, "local_timeout", None) or (config.timeout * 3)
        self._client = httpx2.Client(timeout=local_timeout)

    @property
    def model(self) -> str:
        """Model selected by the active local resource profile."""
        return self._active_profile()["model"]

    def _active_profile(self) -> dict:
        profile_name = getattr(self._config, "local_model_profile", DEFAULT_MODEL_PROFILE)
        try:
            from database.manager import get_database

            row = get_database().fetch_one(
                "SELECT value FROM settings WHERE key = ?", ("hermes_model_profile",)
            )
            saved_profile = row["value"] if row else None
            if saved_profile in MODEL_PROFILES:
                profile_name = saved_profile
        except Exception:
            pass
        profile = dict(MODEL_PROFILES.get(profile_name, MODEL_PROFILES[DEFAULT_MODEL_PROFILE]))
        if profile_name == "high":
            profile["model"] = self._config.local_model or self._config.model or profile["model"]
        return profile

    def capabilities(self) -> ModelCapabilities:
        """Ollama JSON mode is honored (format=json); native tool schemas are not
        translated — Hermes' prompt-based tool protocol + validation is used instead."""
        return ModelCapabilities(
            tool_calling=False,
            structured_output=True,
            vision=False,
            streaming=False,
            context_window=None,
        )

    def generate(self, task_or_request: Task | ModelRequest) -> ProviderResponse:
        """Send chat completion request to Ollama. Never raises upward.

        Accepts a Task for legacy direct call sites (browser-awareness
        inspectors, tests) and normalizes via ``as_request``; through the
        ProviderManager it always receives a ModelRequest.
        """
        request = self.as_request(task_or_request)
        if not self._config.local_hermes_url:
            return ProviderResponse(
                success=False,
                provider=self.name,
                model=self.model,
                text="",
                error="Missing Ollama URL",
            )

        # CPU-only inference can overrun even the long local budget when Ollama
        # is cold-loading the model on the first request. Retry once on a pure
        # timeout: by the second attempt the model is warm, so a slow first
        # call no longer fails the whole task. Non-timeout errors (HTTP errors,
        # bad payloads) are never retried.
        profile = self._active_profile()
        response = self._attempt(request, profile)
        if not response.success and response.error == "Connection timeout":
            logger.warning("Ollama generation timed out (model %s) — retrying once", self.model)
            response = self._attempt(request, profile)
        return response

    def _attempt(self, request: ModelRequest, profile: dict | None = None) -> ProviderResponse:
        """One post/parse round-trip to Ollama, mapping failures to a response."""
        try:
            profile = profile or self._active_profile()
            response = self._post(request, profile)
            response.raise_for_status()
            content = response.json()["message"]["content"]
            return ProviderResponse(
                success=True,
                provider=self.name,
                model=profile["model"],
                text=content,
            )
        except httpx2.TimeoutException:
            return ProviderResponse(
                success=False,
                provider=self.name,
                model=(profile or self._active_profile())["model"],
                text="",
                error="Connection timeout",
            )
        except httpx2.HTTPStatusError as exc:
            reason = self._error_reason(exc.response)
            return ProviderResponse(
                success=False,
                provider=self.name,
                model=(profile or self._active_profile())["model"],
                text="",
                error=reason,
            )
        except httpx2.HTTPError as exc:
            return ProviderResponse(
                success=False,
                provider=self.name,
                model=(profile or self._active_profile())["model"],
                text="",
                error=f"Connection error: {exc}",
            )
        except (KeyError, IndexError, ValueError):
            return ProviderResponse(
                success=False,
                provider=self.name,
                model=(profile or self._active_profile())["model"],
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

    def _post(self, request: ModelRequest, profile: dict | None = None) -> httpx2.Response:
        """Post to Ollama chat API."""
        url = f"{self._config.local_hermes_url}/api/chat"
        headers = {
            "Content-Type": "application/json",
        }
        profile = profile or self._active_profile()
        payload = self._build_payload(request, profile=profile)
        return self._client.post(url, headers=headers, json=payload)

    def _build_payload(
        self, request: ModelRequest, *, profile: dict | None = None, stream: bool = False
    ) -> dict:
        """Build a bounded Ollama payload for the selected resource tier."""
        profile = profile or self._active_profile()
        payload: dict = {
            "model": profile["model"],
            "messages": _build_messages(request),
            "stream": stream,
            "keep_alive": getattr(self._config, "local_keep_alive", "30s"),
            "options": {"num_ctx": profile["num_ctx"]},
        }
        if request.structured_output and self.capabilities().structured_output:
            payload["format"] = "json"
        if request.temperature is not None:
            payload["options"]["temperature"] = request.temperature
        return payload

    def _post_stream(self, request: ModelRequest) -> list[ProviderStreamEvent]:
        """Incremental Ollama `/api/chat` pull ("stream": true). The server
        sends one JSON object per line (NDJSON), each line being the full
        cumulative message state or a plain incremental delta; the adapter
        normalizes every line into a ``ProviderStreamEvent(token, ...)``
        so the transport can render text as it arrives.

        Connection failures during the pull are returned as an error event
        rather than raised, and a fully received but unknown response shape
        degrades to the legacy synchronous result instead of failing the
        whole run.
        """
        try:
            response = self._client.post(
                f"{self._config.local_hermes_url}/api/chat",
                headers={"Content-Type": "application/json"},
                json=self._build_payload(request, stream=True),
                timeout=self._config.local_timeout,
            )
            response.raise_for_status()
            events: list[ProviderStreamEvent] = []
            for line in response.text.splitlines():
                if not line.strip():
                    continue
                try:
                    obj = response.json()
                except ValueError:
                    continue
                # NDJSON pull: the server sends one complete object per line.
                # The model message carries the full text so far, so every
                # line can yield a token.
                if isinstance(obj, dict):
                    message = obj.get("message") or {}
                    content = message.get("content")
                    if content:
                        events.append(
                            ProviderStreamEvent(
                                event="token",
                                data={"text": content},
                            )
                        )
                elif isinstance(obj, str):
                    # Delta-only streaming: the line itself is the new text.
                    if obj:
                        events.append(
                            ProviderStreamEvent(
                                event="token",
                                data={"text": obj},
                            )
                        )
            if events:
                return events
            # No tokens parsed: the model did not stream incrementally.
            # Return the same graceful error as the legacy path.
            return [
                ProviderStreamEvent(
                    event="error",
                    data={"message": "Incomplete stream", "recoverable": True},
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
            reason = self._error_reason(exc.response)
            return [
                ProviderStreamEvent(
                    event="error",
                    data={"message": reason, "recoverable": False},
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

    async def generate_stream(self, request: ModelRequest) -> AsyncIterator[ProviderStreamEvent]:
        """Ollama streaming via the incremental `/api/chat` pull.

        The synchronous `_post_stream` is the streaming-capable path and is
        wrapped with an async iterator so the provider abstraction is
        awaitable by the orchestrator without changing the synchronous
        ``generate`` fallback.
        """
        for event in self._post_stream(request):
            yield event

    @staticmethod
    def _error_reason(response: httpx2.Response) -> str:
        """Build a readable error message, including Ollama's error body when present."""
        message = f"HTTP {response.status_code} {response.reason_phrase or ''}".strip()
        try:
            error = response.json().get("error")
        except Exception:
            error = None
        if error:
            return f"{message} ({error})"
        return message


def _build_messages(request: ModelRequest) -> list[dict]:
    """Build the OpenAI-style messages array from a provider-neutral request.

    Shared by the Ollama and OpenAI-compatible adapters so both wire
    formats assemble the same conversation: system instructions, /remember
    memory, prior session turns, then the current prompt.
    """
    messages: list[dict] = []
    if request.instructions:
        messages.append({"role": "system", "content": request.instructions})
    # Facts the user saved with /remember, injected as a system message so
    # the model actually remembers them (the memory prompt injection).
    if request.memory:
        messages.append({"role": "system", "content": request.memory})
    # Prior conversation turns from the session, oldest first
    for turn in request.history or []:
        role = turn.get("role") if isinstance(turn, dict) else None
        content = turn.get("content") if isinstance(turn, dict) else None
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": request.prompt})
    return messages
