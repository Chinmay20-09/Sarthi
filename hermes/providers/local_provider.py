import httpx

from hermes.config.settings import HermesConfig
from hermes.models import Task

from .base import AIProvider, ProviderResponse


class LocalHermesProvider(AIProvider):
    """Local provider backed by Ollama HTTP API."""

    name = "Ollama"

    def __init__(self, config: HermesConfig):
        self._config = config

    @property
    def _model(self) -> str:
        """Local model name as installed in Ollama, falling back to the generic model."""
        return self._config.local_model or self._config.model

    def generate(self, task: Task) -> ProviderResponse:
        """Send chat completion request to Ollama. Never raises upward."""
        if not self._config.local_hermes_url:
            return ProviderResponse(
                success=False,
                provider=self.name,
                model=self._model,
                text="",
                error="Missing Ollama URL",
            )

        try:
            response = self._post(task)
            response.raise_for_status()
            content = response.json()["message"]["content"]
            return ProviderResponse(
                success=True,
                provider=self.name,
                model=self._model,
                text=content,
            )
        except httpx.TimeoutException:
            return ProviderResponse(
                success=False,
                provider=self.name,
                model=self._model,
                text="",
                error="Connection timeout",
            )
        except httpx.HTTPStatusError as exc:
            reason = self._error_reason(exc.response)
            return ProviderResponse(
                success=False,
                provider=self.name,
                model=self._model,
                text="",
                error=reason,
            )
        except httpx.HTTPError as exc:
            return ProviderResponse(
                success=False,
                provider=self.name,
                model=self._model,
                text="",
                error=f"Connection error: {exc}",
            )
        except (KeyError, IndexError, ValueError):
            return ProviderResponse(
                success=False,
                provider=self.name,
                model=self._model,
                text="",
                error="Invalid response",
            )
        except Exception:
            return ProviderResponse(
                success=False,
                provider=self.name,
                model=self._model,
                text="",
                error="Unexpected error",
            )

    def _post(self, task: Task) -> httpx.Response:
        """Post to Ollama chat API."""
        url = f"{self._config.local_hermes_url}/api/chat"
        headers = {
            "Content-Type": "application/json",
        }
        messages: list[dict] = []
        if task.instructions:
            messages.append({"role": "system", "content": task.instructions})
        messages.append({"role": "user", "content": task.prompt})
        return httpx.post(
            url,
            headers=headers,
            json={
                "model": self._model,
                "messages": messages,
                "stream": False,
            },
            timeout=self._config.timeout,
        )

    @staticmethod
    def _error_reason(response: httpx.Response) -> str:
        """Build a readable error message, including Ollama's error body when present."""
        message = f"HTTP {response.status_code} {response.reason_phrase or ''}".strip()
        try:
            error = response.json().get("error")
        except Exception:
            error = None
        if error:
            return f"{message} ({error})"
        return message
