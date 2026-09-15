"""The Hand interface — Sarthi's Brain/Hand execution boundary.

    Backend = Brain          Desktop = Hand
    (decides)                (performs + observes)

The Brain (brain/executor.py, skills, hermes tools) issues *validated
actions* through this contract; a Hand implementation performs them on a
device and returns structured results/observations. The Brain never
touches the OS directly, and the Hand never reasons: it does not
interpret natural language, call Hermes/LLMs, plan, or decide the next
step — it executes authorized operations and reports what happened.

Implementations:
    - hands.desktop.DesktopHand — the local Windows hand (same machine
      as the Brain today).
    - a future RemoteDesktopHand — the same contract over a network
      protocol; the Brain would not change. (Not implemented yet: the
      current local path stays in process.)

The contract is deliberately the exact public surface DesktopHand
already exposes — nothing new, nothing speculative:

    execute(action, target=None, **kwargs) -> dict   validated action in,
                                                     DesktopResult-shaped dict out
    capabilities() -> dict                           what this hand can do
    find_application_process(exe_name) -> list|None  read-only observation

Results are plain dicts (DesktopResult.to_dict(): success, action,
target, message, error, data). Expected operational failures are
returned, never raised past this boundary.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class Hand(Protocol):
    """Contract between the Brain (caller/authority) and a device Hand.

    Structural: any object with these three members satisfies the
    protocol — no inheritance required. ``@runtime_checkable`` lets the
    suite assert ``isinstance(DesktopHand(), Hand)``.
    """

    def execute(
        self,
        action: str,
        target: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Run one validated action and return a structured result.

        Implementations must allow-list ``action``, validate ``kwargs``
        against the action's spec, and return a DesktopResult-shaped
        dict (``success``, ``action``, ``message``, ``error``, ``data``)
        instead of raising for expected operational failures.
        """
        ...  # pragma: no cover

    def capabilities(self) -> dict[str, Any]:
        """Report what this hand can do (implemented + planned)."""
        ...  # pragma: no cover

    def find_application_process(self, exe_name: str) -> list[dict[str, Any]] | None:
        """Observe: running processes whose executable name matches.

        Read-only; returns None when nothing matches. Callers terminate
        by explicit pid afterwards — the hand never decides *which*
        process is "the one the user meant".
        """
        ...  # pragma: no cover
