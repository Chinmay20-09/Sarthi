import httpx

from hermes.config.settings import HermesConfig
from hermes.models import Task

from .base import AIProvider, ProviderResponse


class LocalHermesProvider(AIProvider):
    """Local provider backed by Ollama HTTP API."""

    name = "Ollama"

    def __init__(self, config: HermesConfig):
        self._config = config

    def generate(self, task: Task) -> ProviderResponse:
        """Send chat completion request to Ollama. Never raises upward."""
        if not self._config.local_hermes_url:
            return ProviderResponse(
                success=False,
                provider=self.name,
                model=self._config.model,
                text="",
                error="Missing Ollama URL",
            )

        try:
            response = self._post(task.prompt)
            response.raise_for_status()
            content = response.json()["message"]["content"]
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
        """Post to Ollama chat API."""
        url = f"{self._config.local_hermes_url}/api/chat"
        headers = {
            "Content-Type": "application/json",
        }

        return httpx.post(
            url,
            headers=headers,
            json={
                "model": self._config.model,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
            },
            timeout=self._config.timeout,
        )
