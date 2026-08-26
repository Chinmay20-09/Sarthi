import httpx

from hermes.config.settings import HermesConfig
from hermes.models import Task

from .base import AIProvider, ProviderResponse


class OpenRouterProvider(AIProvider):
    """OpenRouter provider backed by a persistent httpx HTTP client."""

    name = "OpenRouter"
    endpoint = "https://openrouter.ai/api/v1/chat/completions"

    def __init__(self, config: HermesConfig):
        self._config = config
        # Persistent client for connection pooling — avoids a new TCP
        # handshake on every generate() call.
        self._client = httpx.Client(timeout=config.timeout)

    def generate(self, task: Task) -> ProviderResponse:
        """Send one chat completion request. Never raises upward."""
        # support backward-compatible api_key field or the explicit openrouter_api_key
        api_key = getattr(self._config, "openrouter_api_key", None) or getattr(self._config, "api_key", None)
        if not api_key:
            return ProviderResponse(
                success=False,
                provider=self.name,
                model=self._config.model,
                text="",
                error="Missing API key",
            )

        try:
            response = self._post(task)
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
            return ProviderResponse(
                success=True,
                provider=self.name,
                model=self._config.model,
                text=content,
            )
        except httpx.TimeoutException:
            return ProviderResponse(
                success=False,
                provider=self.name,
                model=self._config.model,
                text="",
                error="Connection timeout",
            )
        except httpx.HTTPStatusError as exc:
            reason = exc.response.reason_phrase or ""
            message = f"HTTP {exc.response.status_code} {reason}".strip()
            return ProviderResponse(
                success=False,
                provider=self.name,
                model=self._config.model,
                text="",
                error=message,
            )
        except httpx.HTTPError as exc:
            return ProviderResponse(
                success=False,
                provider=self.name,
                model=self._config.model,
                text="",
                error=f"Connection error: {exc}",
            )
        except (KeyError, IndexError, ValueError):
            return ProviderResponse(
                success=False,
                provider=self.name,
                model=self._config.model,
                text="",
                error="Invalid response",
            )
        except Exception:
            return ProviderResponse(
                success=False,
                provider=self.name,
                model=self._config.model,
                text="",
                error="Unexpected error",
            )

    def _post(self, task: Task) -> httpx.Response:
        api_key = getattr(self._config, "openrouter_api_key", None) or getattr(self._config, "api_key", None)
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        if getattr(self._config, "openrouter_http_referer", ""):
            headers["HTTP-Referer"] = self._config.openrouter_http_referer
        if getattr(self._config, "openrouter_x_title", ""):
            headers["X-Title"] = self._config.openrouter_x_title
        url = getattr(self._config, "openrouter_url", self.endpoint)
        messages: list[dict] = []
        if task.instructions:
            messages.append({"role": "system", "content": task.instructions})
        # Facts the user saved with /remember, injected as a system message so
        # the model actually remembers them (the memory prompt injection).
        if task.memory:
            messages.append({"role": "system", "content": task.memory})
        # Prior conversation turns from the session, oldest first
        for turn in task.history or []:
            role = turn.get("role") if isinstance(turn, dict) else None
            content = turn.get("content") if isinstance(turn, dict) else None
            if role in ("user", "assistant") and content:
                messages.append({"role": role, "content": content})
        messages.append({"role": "user", "content": task.prompt})
        return self._client.post(
            url,
            headers=headers,
            json={
                "model": self._config.model,
                "messages": messages,
                "temperature": self._config.temperature,
                "stream": False,
            },
        )
