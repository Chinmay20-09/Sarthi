"""Brain ↔ Desktop Agent IPC transport.

This module is the network seam between the Brain (wherever it runs —
Windows today, Linux/Android tomorrow) and the Desktop Agent process
(``Backend/desktop_agent.py --server``, running on the Windows machine
next to the physical ``DesktopHand``).

    Brain                          Desktop Agent (laptop)
    DesktopRequest ──HTTP/JSON──▶  DesktopHand.execute()
    DesktopResult ◀──HTTP/JSON───  structured result

Contract (stable wire format — the server validates against the same
models, so no second schema exists):

    POST /execute   {"action": str, "args": {...}, "target": str|null}
                 →  {"success": bool, "action": str, "target": ..., ...}
    GET  /health    → {"status": "ok", "agent": "sarthi-desktop-agent", ...}
    GET  /capabilities → DesktopHand.capabilities() (implemented + planned)

Security boundary (explicit): this transport carries *only* structured
DesktopRequest actions. The server dispatches exclusively through the
hand's allow-listed action registry — there is no shell, eval, arbitrary
Python, or subprocess execution endpoint on either side, and none may be
added here. See docs/DESKTOP_AGENT_IPC.md.

Cross-platform rule: this file must stay importable on Linux/Android
(the Brain may run there). It imports httpx2 (already a core dependency)
and the pure-Pydantic models — never pywin32/pyautogui/psutil or any
other Windows-only module. ``remote.py`` wraps this client in a ``Hand``.

Host/port/timeout come from configuration (``config.DESKTOP_AGENT_*``,
env-overridable) — never hardcoded at call sites.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx2

from hands.desktop.models import DesktopRequest, DesktopResult

logger = logging.getLogger(__name__)

__all__ = [
    "TransportError",
    "EndpointUnavailableError",
    "DesktopAgentClient",
    "get_desktop_agent_client",
]

# Wire paths (fixed constants — part of the transport contract).
PATH_EXECUTE = "/execute"
PATH_HEALTH = "/health"
PATH_CAPABILITIES = "/capabilities"


class TransportError(Exception):
    """Base class for IPC transport failures (never an OS automation issue)."""


class EndpointUnavailableError(TransportError):
    """The Desktop Agent could not be reached in time (down/wrong host)."""


def _config_value(name: str, default: Any, cast: type) -> Any:
    """Read a SARTHI_DESKTOP_AGENT_* override lazily from the environment."""
    import os

    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return cast(raw)
    except ValueError:
        logger.warning(f"[IPC] invalid {name}={raw!r} — using default {default!r}")
        return default


def get_desktop_agent_host() -> str:
    """Configured Desktop Agent host (env > Backend/config default)."""
    from config import DESKTOP_AGENT_HOST

    return _config_value("SARTHI_DESKTOP_AGENT_HOST", DESKTOP_AGENT_HOST, str)


def get_desktop_agent_port() -> int:
    """Configured Desktop Agent port (env > Backend/config default)."""
    from config import DESKTOP_AGENT_PORT

    return _config_value("SARTHI_DESKTOP_AGENT_PORT", DESKTOP_AGENT_PORT, int)


def get_desktop_agent_timeout() -> float:
    """Configured request timeout in seconds (env > Backend/config default)."""
    from config import DESKTOP_AGENT_TIMEOUT

    return _config_value("SARTHI_DESKTOP_AGENT_TIMEOUT", DESKTOP_AGENT_TIMEOUT, float)


class DesktopAgentClient:
    """HTTP client for one Desktop Agent process.

    Submit structured ``DesktopRequest`` actions; receive structured
    ``DesktopResult`` dicts. Connection failures, timeouts and malformed
    replies never raise past ``execute()`` — they are shaped into
    structured failure results (``error: "transport_unavailable"`` /
    ``transport_bad_response``) so the Brain observes them exactly like a
    local hand failure.

    Importable on Linux/Android: no Windows-only imports, and no state
    beyond the endpoint coordinates.
    """

    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        timeout: float | None = None,
    ):
        """Fix the endpoint; defaults come from configuration."""
        self.host = host or get_desktop_agent_host()
        self.port = int(port or get_desktop_agent_port())
        self.timeout = float(timeout if timeout is not None else get_desktop_agent_timeout())
        self._base_url = f"http://{self.host}:{self.port}"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def base_url(self) -> str:
        """Endpoint this client targets (for logs and tests)."""
        return self._base_url

    def health(self, timeout: float | None = None) -> dict[str, Any] | None:
        """Agent health payload, or None when unreachable.

        Convenience for tests/monitoring; ``execute()`` never depends on
        a prior health probe.
        """
        body = self._get_json(PATH_HEALTH, timeout=timeout)
        return body if isinstance(body, dict) else None

    def capabilities(self, timeout: float | None = None) -> dict[str, Any] | None:
        """The remote hand's capability report, or None when unreachable."""
        body = self._get_json(PATH_CAPABILITIES, timeout=timeout)
        return body if isinstance(body, dict) else None

    def execute(
        self,
        action: str,
        target: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Submit one action to the Desktop Agent and return its result.

        Mirrors ``Hand.execute`` so ``RemoteDesktopHand`` can delegate
        verbatim. The request is validated *here first* (same model the
        server re-validates) so malformed local calls fail without a
        network round-trip. Returns a DesktopResult-shaped dict; see the
        class docstring for the transport-failure error codes.
        """
        request = DesktopRequest(action=action, args=dict(kwargs), target=target)
        return self.execute_request(request)

    def execute_request(self, request: DesktopRequest) -> dict[str, Any]:
        """Send a pre-built ``DesktopRequest`` (the wire-contract method)."""
        payload = request.model_dump(mode="json")
        try:
            response = httpx2.post(
                self._base_url + PATH_EXECUTE,
                json=payload,
                timeout=self.timeout,
            )
        except (httpx2.HTTPError, OSError) as exc:
            logger.warning(f"[IPC] agent unreachable at {self._base_url}: {exc}")
            return self._transport_failure(
                request.action,
                request.target,
                "transport_unavailable",
                f"Desktop Agent at {self._base_url} is unreachable: {exc}",
            )

        if response.status_code != 200:
            # The server answers 200 with a structured failure for
            # rejected *actions*; a non-200 means a transport-level
            # problem (bad route, crashed handler, proxy in the way).
            return self._transport_failure(
                request.action,
                request.target,
                "transport_bad_response",
                f"Desktop Agent returned HTTP {response.status_code} for {PATH_EXECUTE}",
            )

        try:
            body = response.json()
        except ValueError:
            return self._transport_failure(
                request.action,
                request.target,
                "transport_bad_response",
                "Desktop Agent returned a non-JSON response.",
            )

        if not isinstance(body, dict) or not isinstance(body.get("success"), bool):
            return self._transport_failure(
                request.action,
                request.target,
                "transport_bad_response",
                "Desktop Agent response is not a DesktopResult object.",
            )
        return body

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _get_json(self, path: str, timeout: float | None) -> dict[str, Any] | None:
        """GET a JSON object from the agent; None on any failure."""
        try:
            response = httpx2.get(self._base_url + path, timeout=timeout or self.timeout)
            if response.status_code != 200:
                return None
            body = response.json()
        except (httpx2.HTTPError, OSError, ValueError):
            return None
        return body if isinstance(body, dict) else None

    @staticmethod
    def _transport_failure(
        action: str, target: str | None, error: str, message: str
    ) -> dict[str, Any]:
        """A transport problem as a structured DesktopResult dict.

        Distinguishes "the desktop refused the action" from "no one was
        listening" — callers can retry the latter without re-deciding.
        """
        return DesktopResult.fail(
            action=action, message=message, target=target, error=error
        ).to_dict()


_client: DesktopAgentClient | None = None


def get_desktop_agent_client() -> DesktopAgentClient:
    """Shared client (created on first use; reads configuration once)."""
    global _client
    if _client is None:
        _client = DesktopAgentClient()
    return _client
