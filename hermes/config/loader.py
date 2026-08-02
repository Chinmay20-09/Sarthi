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
            api_key=os.getenv("OPENROUTER_API_KEY", HermesConfig.api_key),
            http_referer=os.getenv("OPENROUTER_HTTP_REFERER", HermesConfig.http_referer),
            x_title=os.getenv("OPENROUTER_X_TITLE", HermesConfig.x_title),
        )
