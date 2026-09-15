"""Local vs remote desktop execution mode for the Brain.

The Brain's one seam for "give me the desktop hand": returns the
in-process ``DesktopHand`` (mode ``local`` — the pre-IPC behaviour,
byte-for-byte unchanged) or the ``RemoteDesktopHand`` (mode ``remote`` —
the same ``Hand`` contract over the IPC transport).

    SARTHI_DESKTOP_AGENT_MODE=local  → DesktopHand        (in process)
    SARTHI_DESKTOP_AGENT_MODE=remote → RemoteDesktopHand  (via Desktop Agent)

Everything above the ``Hand`` interface (executor close handler, skills,
future Hermes tools) keeps calling ``get_desktop_hand()`` and never
learns which mode is active — the mode is invisible above the boundary.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

__all__ = ["get_desktop_hand"]


def get_desktop_hand():
    """Return the configured desktop hand for this process.

    ``remote`` mode constructs the ``RemoteDesktopHand`` eagerly (no OS
    backends are created, so this is safe on any OS); ``local`` keeps the
    existing lazy in-process ``DesktopHand`` singleton unchanged.
    """
    mode = os.environ.get("SARTHI_DESKTOP_AGENT_MODE", "").strip().lower()
    if not mode:
        from config import DESKTOP_AGENT_MODE

        mode = str(DESKTOP_AGENT_MODE).strip().lower()

    if mode == "remote":
        from hands.remote import RemoteDesktopHand

        logger.debug("[Hands] desktop execution mode: remote (Desktop Agent IPC)")
        return RemoteDesktopHand()

    if mode not in ("", "local"):
        logger.warning(
            "[Hands] unknown SARTHI_DESKTOP_AGENT_MODE=%r — falling back to local", mode
        )
    from hands.desktop import get_desktop_hand as get_local_desktop_hand

    return get_local_desktop_hand()
