import os
from pathlib import Path

from dotenv import load_dotenv

from .settings import HermesConfig


class ConfigLoader:
    """Loads HermesConfig from defaults and .env.

    The config is cached after the first load() call so repeated calls
    (e.g. every get_orchestrator()) don't re-read .env from disk.
    """

    _cached: HermesConfig | None = None

    def __init__(self, env_path: str | Path | None = None):
        self._env_path = env_path

    def load(self) -> HermesConfig:
        """Load configuration from .env; all env access lives here.

        The first call reads .env and caches the result. Subsequent calls
        return the cached config instantly (no disk I/O).
        """
        if ConfigLoader._cached is not None and self._env_path is None:
            return ConfigLoader._cached

        if self._env_path:
            load_dotenv(self._env_path)
        else:
            load_dotenv(Path(__file__).resolve().parents[2] / ".env")

        config = HermesConfig(
            provider=os.getenv("HERMES_PROVIDER", HermesConfig.provider),
            model=os.getenv("HERMES_MODEL", HermesConfig.model),
            temperature=float(os.getenv("HERMES_TEMPERATURE", HermesConfig.temperature)),
            timeout=float(os.getenv("HERMES_TIMEOUT", HermesConfig.timeout)),
            sandbox_path=os.getenv("HERMES_SANDBOX_PATH", HermesConfig.sandbox_path),
            openrouter_api_key=os.getenv("OPENROUTER_API_KEY", HermesConfig.openrouter_api_key),
            openrouter_url=os.getenv("OPENROUTER_URL", HermesConfig.openrouter_url),
            openrouter_http_referer=os.getenv(
                "OPENROUTER_HTTP_REFERER", HermesConfig.openrouter_http_referer
            ),
            openrouter_x_title=os.getenv("OPENROUTER_X_TITLE", HermesConfig.openrouter_x_title),
            local_hermes_url=os.getenv("LOCAL_HERMES_URL", HermesConfig.local_hermes_url),
            local_hermes_api_key=os.getenv(
                "LOCAL_HERMES_API_KEY", HermesConfig.local_hermes_api_key
            ),
            local_model=os.getenv("LOCAL_HERMES_MODEL", HermesConfig.local_model),
            local_timeout=float(os.getenv("LOCAL_HERMES_TIMEOUT", HermesConfig.local_timeout)),
        )

        if self._env_path is None:
            ConfigLoader._cached = config

        return config
