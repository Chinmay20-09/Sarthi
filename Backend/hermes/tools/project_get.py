"""
project_get tool — current project/repo status through Sarthi's existing
Project Tracker skill (GitHub sync state, pending repos, last commits).

Hermes uses this when a complex task needs the user's actual project context
("take the latency problem to ChatGPT" needs to know what Sarthi's backend
looks like first).
"""

import logging
from typing import Any

from brain.intent import Intent

from .base import BaseTool, ToolResult

logger = logging.getLogger(__name__)


class ProjectGetTool(BaseTool):
    """Fetch current project/repository status from the Project Tracker."""

    name = "project_get"
    description = (
        "Get the user's current project/repository status (tracked repos, "
        "pending work, latest commits) from the Project Tracker."
    )
    parameters = {
        "type": "object",
        "properties": {
            "operation": {
                "type": "string",
                "description": (
                    "What to fetch: 'status' (default, project status summary) "
                    "or 'check' (new repositories since last sync)."
                ),
            },
        },
        "required": [],
    }

    def execute(self, arguments: dict[str, Any]) -> ToolResult:
        """Delegate to the Project Tracker skill's deterministic handlers."""
        operation = str(arguments.get("operation") or "status").strip().lower()
        if operation not in ("status", "check"):
            return ToolResult(
                success=False,
                tool=self.name,
                error="Unknown operation. Use 'status' or 'check'.",
                invalid=True,
            )

        try:
            from skills.project_tracker.main import GitHubProjectSkill

            skill = GitHubProjectSkill()
            result = skill.execute(Intent(action=operation, target="projects"))
        except Exception as e:  # never leak internals upward
            logger.error("project_get failed unexpectedly: %s", e)
            return ToolResult(
                success=False,
                tool=self.name,
                error="Project status is unavailable right now.",
            )

        if result.get("success"):
            status_text = result.get("status") or result.get("result") or ""
            if isinstance(status_text, dict):
                status_text = status_text.get("message", str(status_text))
            return ToolResult(
                success=True,
                tool=self.name,
                result=str(status_text)[:800] or "Project status retrieved.",
                data={"operation": operation},
            )

        return ToolResult(
            success=False,
            tool=self.name,
            error=result.get("error") or "Project status could not be retrieved.",
        )
