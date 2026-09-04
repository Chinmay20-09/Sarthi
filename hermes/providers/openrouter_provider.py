
from hermes.config.settings import HermesConfig

from .openai_compatible import OpenAICompatibleProvider


class OpenRouterProvider(OpenAICompatibleProvider):
    """OpenRouter adapter — an OpenAI-compatible endpoint with its own URL,
    key, and optional site headers.

    All request/response normalization (ModelRequest -> chat-completions,
    response -> ProviderResponse) is inherited from
    ``OpenAICompatibleProvider``; this class only overrides the
    OpenRouter-specific wiring (endpoint, api key source, headers).
    """

    name = "OpenRouter"
    default_endpoint = "https://openrouter.ai/api/v1/chat/completions"

    def _resolve_endpoint(self, config: HermesConfig) -> str:
        return (config.openrouter_url or self.default_endpoint).rstrip("/") or ""

    def _resolve_api_key(self, config: HermesConfig) -> str:
        return config.openrouter_api_key or config.api_key

    def _requires_api_key(self) -> bool:
        # OpenRouter always needs a key — fail fast with a clear error.
        return True

    def _extra_headers(self) -> dict:
        headers = {}
        if getattr(self._config, "openrouter_http_referer", ""):
            headers["HTTP-Referer"] = self._config.openrouter_http_referer
        if getattr(self._config, "openrouter_x_title", ""):
            headers["X-Title"] = self._config.openrouter_x_title
        return headers
