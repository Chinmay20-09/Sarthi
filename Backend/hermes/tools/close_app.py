"""
close_app tool — closes a running desktop application through Sarthi's
existing close path (brain executor's close handler: knowledge lookup +
Desktop hand termination by explicit pid).

Hermes never kills processes directly; it requests the high-level close and
Sarthi decides HOW (knowledge resolution, pid targeting, graceful close).
"""

import logging
from typing import Any

from brain.intent import Intent

from .base import BaseTool, ToolResult

logger = logging.getLogger(__name__)


class CloseAppTool(BaseTool):
    """Close a running desktop application known to Sarthi."""

    name = "close_app"
    description = "Close a running desktop application that is known to Sarthi."
    parameters = {
        "type": "object",
        "properties": {
            "target": {
                "type": "string",
                "description": "Name or alias of the application to close (e.g. 'Spotify').",
            }
        },
        "required": ["target"],
    }

    def execute(self, arguments: dict[str, Any]) -> ToolResult:
        """Validate the target and delegate to the brain executor's close handler."""
        target = str(arguments.get("target") or "").strip()
        if not target:
            return ToolResult(
                success=False,
                tool=self.name,
                error="No application target was specified.",
                invalid=True,
            )

        try:
            # The brain executor registers the "close" handler (knowledge
            # lookup + Desktop hand close by pid). Going through the executor
            # keeps exactly one close implementation in the project.
            from brain.executor import BrainExecutor

            result = BrainExecutor().execute(Intent(action="close", target=target))
        except Exception as e:  # never leak internals upward
            logger.error("close_app failed unexpectedly for '%s': %s", target, e)
            return ToolResult(
                success=False,
                tool=self.name,
                error="The application could not be closed.",
            )

        if result.get("success"):
            app_name = result.get("application", target)
            closed = result.get("closed", 1)
            return ToolResult(
                success=True,
                tool=self.name,
                result=f"Closed {app_name}.",
                data={"application": app_name, "closed": closed},
            )

        return ToolResult(
            success=False,
            tool=self.name,
            error=result.get("error") or f"{target} could not be closed.",
            data={"status": result.get("status")},
        )
