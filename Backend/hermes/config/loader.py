import os
from pathlib import Path

from dotenv import load_dotenv

from hermes.sandbox import resolve_sandbox_root

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
            sandbox_path=str(
                resolve_sandbox_root(os.getenv("HERMES_SANDBOX_PATH", HermesConfig.sandbox_path))
            ),
            openrouter_api_key=os.getenv("OPENROUTER_API_KEY", HermesConfig.openrouter_api_key),
            openrouter_url=os.getenv("OPENROUTER_URL", HermesConfig.openrouter_url),
            openrouter_http_referer=os.getenv(
                "OPENROUTER_HTTP_REFERER", HermesConfig.openrouter_http_referer
            ),
            openrouter_x_title=os.getenv("OPENROUTER_X_TITLE", HermesConfig.openrouter_x_title),
            openai_compatible_url=os.getenv(
                "OPENAI_COMPATIBLE_URL", HermesConfig.openai_compatible_url
            ),
            openai_compatible_api_key=os.getenv(
                "OPENAI_COMPATIBLE_API_KEY", HermesConfig.openai_compatible_api_key
            ),
            local_hermes_url=os.getenv("LOCAL_HERMES_URL", HermesConfig.local_hermes_url),
            local_hermes_api_key=os.getenv(
                "LOCAL_HERMES_API_KEY", HermesConfig.local_hermes_api_key
            ),
            local_model=os.getenv("LOCAL_HERMES_MODEL", HermesConfig.local_model),
            local_timeout=float(os.getenv("LOCAL_HERMES_TIMEOUT", HermesConfig.local_timeout)),
            # Agent loop bounds (Phase 3f)
            agent_max_iterations=int(
                os.getenv("HERMES_AGENT_MAX_ITERATIONS", HermesConfig.agent_max_iterations)
            ),
            agent_timeout=float(os.getenv("HERMES_AGENT_TIMEOUT", HermesConfig.agent_timeout)),
            # Router knobs (Phase 3f)
            router_mode=os.getenv("HERMES_ROUTER_MODE", HermesConfig.router_mode),
            router_min_score=int(
                os.getenv("HERMES_ROUTER_MIN_SCORE", HermesConfig.router_min_score)
            ),
            # Retrieval knobs (Phase 3f)
            retrieval_max_total_chars=int(
                os.getenv("HERMES_RETRIEVAL_MAX_CHARS", HermesConfig.retrieval_max_total_chars)
            ),
            retrieval_enabled=(
                os.getenv("HERMES_RETRIEVAL_ENABLED", "true").strip().lower() != "false"
            ),
        )

        if self._env_path is None:
            ConfigLoader._cached = config

        return config
