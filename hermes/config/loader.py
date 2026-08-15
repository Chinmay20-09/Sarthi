import os
from pathlib import Path

from dotenv import load_dotenv

from .settings import HermesConfig


class ConfigLoader:
    """Loads HermesConfig from defaults and .env."""

    def __init__(self, env_path: str | Path | None = None):
        self._env_path = env_path

    def load(self) -> HermesConfig:
        """Load configuration from .env; all env access lives here."""
        if self._env_path:
            load_dotenv(self._env_path)
        else:
            load_dotenv(Path(__file__).resolve().parents[2] / ".env")

        return HermesConfig(
            provider=os.getenv("HERMES_PROVIDER", HermesConfig.provider),
            model=os.getenv("HERMES_MODEL", HermesConfig.model),
            temperature=float(os.getenv("HERMES_TEMPERATURE", HermesConfig.temperature)),
            timeout=float(os.getenv("HERMES_TIMEOUT", HermesConfig.timeout)),
            sandbox_path=os.getenv("HERMES_SANDBOX_PATH", HermesConfig.sandbox_path),
            openrouter_api_key=os.getenv("OPENROUTER_API_KEY", HermesConfig.openrouter_api_key),
            openrouter_url=os.getenv("OPENROUTER_URL", HermesConfig.openrouter_url),
            openrouter_http_referer=os.getenv("OPENROUTER_HTTP_REFERER", HermesConfig.openrouter_http_referer),
            openrouter_x_title=os.getenv("OPENROUTER_X_TITLE", HermesConfig.openrouter_x_title),
            local_hermes_url=os.getenv("LOCAL_HERMES_URL", HermesConfig.local_hermes_url),
            local_hermes_api_key=os.getenv("LOCAL_HERMES_API_KEY", HermesConfig.local_hermes_api_key),
            local_model=os.getenv("LOCAL_HERMES_MODEL", HermesConfig.local_model),
        )
