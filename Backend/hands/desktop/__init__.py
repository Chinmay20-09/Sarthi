"""Desktop hand — the local (same-machine) implementation of the Hand
interface.

The Hand interface (``hands.base.Hand``) is the Brain/Hand boundary: the
Brain issues validated actions, the hand performs and observes. This
package provides ``DesktopHand``, the local Windows implementation
(tomorrow a RemoteDesktopHand would implement the same contract over a
network protocol).

Example:

    from hands.desktop import DesktopHand

    desktop = DesktopHand()
    result = desktop.execute("open_url", target="docs", url="https://example.com")
    result["success"]  # True
"""

from hands.base import Hand
from hands.desktop.capabilities import CAPABILITIES, PLANNED_CAPABILITIES
from hands.desktop.filesystem import FilesystemBackend, FilesystemScopeError
from hands.desktop.hand import DesktopHand, get_desktop_hand
from hands.desktop.models import DesktopRequest, DesktopResult

# The local hand implements the Brain/Hand contract (asserted once at
# import; the test suite locks it too). Cheap: runtime_checkable protocol.
assert isinstance(DesktopHand(), Hand)

__all__ = [
    "CAPABILITIES",
    "DesktopHand",
    "DesktopRequest",
    "DesktopResult",
    "FilesystemBackend",
    "FilesystemScopeError",
    "Hand",
    "PLANNED_CAPABILITIES",
    "get_desktop_hand",
]
