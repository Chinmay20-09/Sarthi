"""Desktop hand — Sarthi's physical execution layer for Windows.

Public entry point: ``DesktopHand``. Example:

    from hands.desktop import DesktopHand

    desktop = DesktopHand()
    result = desktop.execute("open_url", target="docs", url="https://example.com")
    result["success"]  # True
"""

from hands.desktop.capabilities import CAPABILITIES, PLANNED_CAPABILITIES
from hands.desktop.filesystem import FilesystemBackend, FilesystemScopeError
from hands.desktop.hand import DesktopHand, get_desktop_hand
from hands.desktop.models import DesktopRequest, DesktopResult

__all__ = [
    "CAPABILITIES",
    "DesktopHand",
    "DesktopRequest",
    "DesktopResult",
    "FilesystemBackend",
    "FilesystemScopeError",
    "PLANNED_CAPABILITIES",
    "get_desktop_hand",
]
