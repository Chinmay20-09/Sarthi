"""RemoteDesktopHand — the Desktop Hand, reached over IPC.

Implements the ``Hand`` contract (``hands/base.py``) on top of the
Brain↔Desktop Agent transport (``hands/transport.py``). This is the seam
AD-16 left prepared: the Brain programs against ``Hand``; whether the
action runs in-process (``DesktopHand``) or on another machine
(``RemoteDesktopHand``) is a configuration choice, not a code change.

    Brain (any OS) ──DesktopRequest──▶ Desktop Agent ──▶ DesktopHand ──▶ Windows

Responsibilities are unchanged: this class performs **no** reasoning and
**no** Windows automation of its own — it forwards validated actions and
returns the structured result. Validation happens on both ends: once
locally (``DesktopRequest`` shape) and once at the agent (the real
``DesktopHand`` allow-list + argument spec), which stays the single
physical execution layer.

Cross-platform: importable on Linux/Android — this module touches only
the transport client and the ``Hand`` protocol. The Windows-only imports
remain exclusively inside the agent's ``DesktopHand``.

Mode selection lives in ``hands/local.py`` (``get_desktop_hand``),
preserving ``hands.desktop.get_desktop_hand`` as the local-only factory.
"""

from __future__ import annotations

import logging
from typing import Any

from hands.base import Hand
from hands.desktop.models import DesktopRequest, DesktopResult
from hands.transport import DesktopAgentClient, get_desktop_agent_client

logger = logging.getLogger(__name__)

__all__ = ["RemoteDesktopHand"]


class RemoteDesktopHand:
    """``Hand`` implementation that submits actions to a Desktop Agent.

    Structural conformance to ``hands.base.Hand`` is asserted at import
    time (same pattern as ``DesktopHand``): ``execute``, ``capabilities``
    and ``find_application_process`` forward to the agent; results are
    DesktopResult-shaped dicts, and expected failures are returned, never
    raised.
    """

    def __init__(self, client: DesktopAgentClient | None = None):
        """Bind to a client (defaults to the configured shared client)."""
        self._client = client or get_desktop_agent_client()

    # ------------------------------------------------------------------
    # Hand contract
    # ------------------------------------------------------------------

    def execute(self, action: str, target: str | None = None, **kwargs: Any) -> dict[str, Any]:
        """Forward one action to the Desktop Agent."""
        return self._client.execute(action, target=target, **kwargs)

    def execute_request(self, request: DesktopRequest) -> dict[str, Any]:
        """Send a pre-built ``DesktopRequest`` through the transport."""
        return self._client.execute_request(request)

    def capabilities(self) -> dict[str, Any]:
        """The remote hand's report; structured failure when unreachable."""
        report = self._client.capabilities()
        if report is None:
            return DesktopResult.fail(
                action="capabilities",
                message="Desktop Agent is unreachable — no capability report.",
                error="transport_unavailable",
            ).to_dict()
        return report

    def find_application_process(self, exe_name: str) -> list[dict[str, Any]] | None:
        """Observe: matching processes on the agent's machine.

        Implemented with the registered ``get_processes`` action and
        client-side name filtering — the same logic as the local hand's
        method, with no new server-side surface. ``None`` when nothing
        matches or the agent is unreachable.
        """
        result = self._client.execute("get_processes")
        if not result.get("success"):
            logger.warning(
                "[IPC] find_application_process: get_processes failed: %s",
                result.get("error") or result.get("message"),
            )
            return None
        processes = result.get("data", {}).get("processes") or []
        wanted = (exe_name or "").lower()
        if not wanted:
            return None
        matches = [p for p in processes if (p.get("name") or "").lower() == wanted]
        return matches or None

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def health(self) -> dict[str, Any] | None:
        """Agent health payload (tests/monitoring convenience)."""
        return self._client.health()

    @property
    def client(self) -> DesktopAgentClient:
        """The underlying transport client."""
        return self._client


assert isinstance(RemoteDesktopHand(), Hand)
