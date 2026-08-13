import httpx

from hermes.config.settings import HermesConfig
from hermes.models import Task

from .base import AIProvider, ProviderResponse


class OpenRouterProvider(AIProvider):
    """OpenRouter provider backed by an httpx HTTP client."""

    name = "OpenRouter"
    endpoint = "https://openrouter.ai/api/v1/chat/completions"

    def __init__(self, config: HermesConfig):
        self._config = config

    def generate(self, task: Task) -> ProviderResponse:
        """Send one chat completion request. Never raises upward."""
        if not self._config.api_key:
            return ProviderResponse(
                success=False,
                provider=self.name,
                model=self._config.model,
                text="",
                error="Missing API key",
            )

        try:
            response = self._post(task.prompt)
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

    def _post(self, prompt: str) -> httpx.Response:
        headers = {
            "Authorization": f"Bearer {self._config.api_key}",
            "Content-Type": "application/json",
        }
        if self._config.http_referer:
            headers["HTTP-Referer"] = self._config.http_referer
        if self._config.x_title:
            headers["X-Title"] = self._config.x_title
        return httpx.post(
            self.endpoint,
            headers=headers,
            json={
                "model": self._config.model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": self._config.temperature,
                "stream": False,
            },
            timeout=self._config.timeout,
        )
