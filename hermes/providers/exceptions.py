class ProviderError(Exception):
    """Base exception for all provider errors."""


class ProviderUnavailable(ProviderError):  # noqa: N818 (spec-named)
    """Raised when a provider cannot be initialized or reached."""


class InvalidResponse(ProviderError):  # noqa: N818 (spec-named)
    """Raised when a provider returns a malformed or unusable response."""
