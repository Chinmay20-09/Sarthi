"""Provider selection and wiring — the only place Hermes maps a configured
provider name to a concrete adapter class.

Hermes core (orchestrator, tool planner, service, routes) never imports a
concrete provider. It asks this registry to build the ``ProviderManager``
from configuration. The default (unset ``HERMES_PROVIDER``) is the local
Hermes/Ollama provider — no cloud calls unless a remote provider is
configured. Remote providers stay available but dormant until opted in:

    provider = local | ollama    -> LocalHermesProvider (Ollama), local-only
    provider = openrouter        -> OpenRouterProvider, local Ollama fallback
    provider = openai_compatible -> OpenAICompatibleProvider, local fallback
    provider = openai            -> OpenAICompatibleProvider (OpenAI endpoint)

Adding a provider = writing one adapter (``AIProvider`` subclass),
registering it here, and configuring it — Hermes core is untouched.
"""

import logging
from dataclasses import asdict

from hermes.config.settings import HermesConfig

from .base import AIProvider
from .local_provider import LocalHermesProvider
from .manager import ProviderManager
from .openai_compatible import OpenAICompatibleProvider
from .openrouter_provider import OpenRouterProvider

logger = logging.getLogger(__name__)

# Canonical provider names registry understands.
LOCAL = "local"
OPENROUTER = "openrouter"
OPENAI_COMPATIBLE = "openai_compatible"

# Aliases accepted from configuration, all mapping to a canonical name.
_ALIASES = {
    "local": LOCAL,
    "local_hermes": LOCAL,
    "localhermes": LOCAL,
    "ollama": LOCAL,
    "openrouter": OPENROUTER,
    "openai": OPENAI_COMPATIBLE,
    "openai_compatible": OPENAI_COMPATIBLE,
    "openai-compatible": OPENAI_COMPATIBLE,
}


def resolve_provider_name(provider: str | None) -> str:
    """Map the configured provider string to a canonical name.

    Unknown values fall back to the *local* provider (never silently to a
    remote one — a typo must not spend cloud credits) and are logged loudly.
    """
    name = (provider or "").strip().lower()
    if name in _ALIASES:
        return _ALIASES[name]
    # Accept prefix-style values like the legacy "openrouter/free" or
    # "openrouter/custom" / "openai_compatible:x"
    if name.startswith("openrouter"):
        return OPENROUTER
    if name.startswith(("openai_compatible", "openai-compatible", "openai")):
        return OPENAI_COMPATIBLE
    logger.error(
        "Unknown HERMES_PROVIDER=%r — defaulting to the local provider (ollama). "
        "Supported values: local | ollama | openrouter | openai_compatible | openai.",
        provider,
    )
    return LOCAL


def create_primary(config: HermesConfig) -> AIProvider:
    """Build the configured primary provider adapter."""
    resolved = resolve_provider_name(config.provider)
    if resolved == LOCAL:
        return LocalHermesProvider(config)
    if resolved == OPENROUTER:
        return OpenRouterProvider(config)
    return OpenAICompatibleProvider(config)


def is_local_only(config: HermesConfig) -> bool:
    """True when the configured provider is local — no remote primary."""
    return resolve_provider_name(config.provider) == LOCAL


def create_fallback(config: HermesConfig) -> AIProvider | None:
    """Local Ollama fallback for remote primaries; None for local-only mode."""
    if is_local_only(config):
        return None
    return LocalHermesProvider(config)


def build_provider_manager(config: HermesConfig) -> ProviderManager:
    """Wire the configured primary (and local fallback for remote primaries)."""
    manager = ProviderManager()
    manager.initialize(create_primary(config))
    fallback = create_fallback(config)
    if fallback is not None:
        manager.set_fallback(fallback)
    return manager


def create_local_provider(config: HermesConfig | None = None) -> LocalHermesProvider:
    """Configured local (Ollama) provider.

    Browser-awareness observation and the ai_chain transcript extractor
    deliberately use the local model (cheap, offline, no cloud credits) —
    this helper keeps their wiring out of concrete-imports of the adapter.
    """
    if config is None:
        from hermes.config.loader import ConfigLoader

        config = ConfigLoader().load()
    return LocalHermesProvider(config)


def provider_status(config: HermesConfig, manager: ProviderManager | None = None) -> dict:
    """Compact diagnostic snapshot of the configured + active provider stack."""
    primary = manager.primary if manager is not None else None
    fallback = manager.fallback if manager is not None else None
    return {
        "provider": primary.name if primary is not None else "",
        "model": primary.model if primary is not None else "",
        "capabilities": asdict(primary.capabilities()) if primary is not None else {},
        "fallback_provider": fallback.name if fallback is not None else None,
        "fallback_model": fallback.model if fallback is not None else None,
        "configured_provider": config.provider,
        "configured_model": config.model,
    }
