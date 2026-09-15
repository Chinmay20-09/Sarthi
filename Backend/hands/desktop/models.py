"""
Typed models for the Desktop hand.

Every action returns a ``DesktopResult`` — a structured success/failure
record that never hides what happened. Requests may be built with the
``DesktopRequest`` model (action + arguments) for callers that want a
single validated object; the hand's ``execute()`` also accepts plain
kwargs, which are normalized into this shape internally.

No reasoning, no policy — pure data contracts.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class DesktopRequest(BaseModel):
    """One explicit Desktop action: an action name plus its arguments.

    Actions are validated against the hand's registered capability map
    before anything runs; unknown actions and malformed arguments are
    rejected without touching Windows.

    ``target`` is the optional human-facing label the local hand already
    accepts (e.g. "chrome") — carried into the result for display, never
    used for routing. This is also the wire format of the Desktop Agent
    IPC transport (``hands/transport.py`` ↔ ``desktop_agent.py --server``):
    JSON of exactly this model.
    """

    action: str = Field(min_length=1)
    args: dict[str, Any] = Field(default_factory=dict)
    target: str | None = None


class DesktopResult(BaseModel):
    """Structured outcome of one Desktop action.

    ``success`` is authoritative; failures always carry a human-readable
    ``message`` (and optional ``error`` detail). Never raise past this
    boundary for expected operational failures — return one of these.
    """

    success: bool
    action: str
    target: str | None = None
    message: str = ""
    error: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def ok(
        cls,
        action: str,
        message: str,
        target: str | None = None,
        **data: Any,
    ) -> DesktopResult:
        """Build a success result."""
        return cls(success=True, action=action, target=target, message=message, data=data)

    @classmethod
    def fail(
        cls,
        action: str,
        message: str,
        target: str | None = None,
        error: str | None = None,
        **data: Any,
    ) -> DesktopResult:
        """Build a failure result. Failures are never hidden — they are returned."""
        return cls(
            success=False,
            action=action,
            target=target,
            message=message,
            error=error or message,
            data=data,
        )

    def to_dict(self) -> dict[str, Any]:
        """Plain-dict shape for callers that do not want the model object."""
        out: dict[str, Any] = {
            "success": self.success,
            "action": self.action,
            "target": self.target,
            "message": self.message,
        }
        if self.error is not None:
            out["error"] = self.error
        if self.data:
            out["data"] = self.data
        return out
