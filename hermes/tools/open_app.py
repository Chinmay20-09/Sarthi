"""
open_app tool — opens a desktop application through Sarthi's existing
Application Launcher skill (knowledge-layer entity resolution + launch).

This tool does NOT spawn a second executor: it delegates to
AppLauncherSkill, the exact skill the Brain's executor uses for the
"open" action.
"""

import logging
from typing import Any

from brain.intent import Intent
from skills.app_launcher.main import AppLauncherSkill

from .base import BaseTool, ToolResult

logger = logging.getLogger(__name__)


class OpenAppTool(BaseTool):
    """Open a desktop application known to Sarthi."""

    name = "open_app"
    description = "Open a desktop application that is known to Sarthi."
    parameters = {
        "type": "object",
        "properties": {
            "target": {
                "type": "string",
                "description": "Name or alias of the application to open (e.g. 'Chrome').",
            }
        },
        "required": ["target"],
    }

    def execute(self, arguments: dict[str, Any]) -> ToolResult:
        """Validate the target and delegate to Sarthi's AppLauncherSkill."""
        target = str(arguments.get("target") or "").strip()
        if not target:
            return ToolResult(
                success=False,
                tool=self.name,
                error="No application target was specified.",
                invalid=True,
            )

        try:
            result = AppLauncherSkill().execute(Intent(action="open", target=target))
        except Exception as e:  # never leak internals upward
            logger.error("open_app failed unexpectedly for '%s': %s", target, e)
            return ToolResult(
                success=False,
                tool=self.name,
                error="The application could not be opened.",
            )

        if result.get("success"):
            info = result.get("result") or {}
            app_name = info.get("application", target)
            return ToolResult(
                success=True,
                tool=self.name,
                result=f"{app_name} opened",
                data={"application": app_name},
            )

        status = result.get("status")
        if status == "needs_decision":
            app_name = ((result.get("result") or {}).get("visual") or {}).get("data", {}).get("name", target)
            return ToolResult(
                success=False,
                tool=self.name,
                error=f"{app_name} needs to be added to your favourites before it can be opened.",
                data={"application": app_name},
            )
        if status == "not_found":
            return ToolResult(
                success=False,
                tool=self.name,
                error=f"Application '{target}' could not be found.",
            )
        return ToolResult(
            success=False,
            tool=self.name,
            error=result.get("error") or f"Application '{target}' could not be opened.",
        )
