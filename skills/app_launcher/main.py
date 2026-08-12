"""
Application Launcher Skill for Sarthi.

Launches desktop applications discovered by the Knowledge Layer.
Uses injected KnowledgeManager via self.knowledge (DI pattern).

ARCHITECTURE:
    This skill communicates ONLY through the Knowledge Layer.
    It never accesses databases or JSON files directly.
    Dependencies are injected via BaseSkill constructor.
"""

import logging
import subprocess
from typing import Any

from brain.intent import Intent
from skills.base import BaseSkill

logger = logging.getLogger(__name__)


class AppLauncherSkill(BaseSkill):
    """
    Application launcher skill.

    Launches desktop applications by name or alias.
    Uses Knowledge Layer for entity resolution and path lookup.

    Usage:
        skill = AppLauncherSkill(knowledge_manager=manager)
        result = skill.execute(Intent(action="open", target="chrome"))
    """

    name = "app_launcher"
    description = "Launches desktop applications via the Knowledge Layer"
    version = "1.0.0"

    # ------------------------------------------------------------------
    # BaseSkill interface
    # ------------------------------------------------------------------

    def execute(self, intent: Intent) -> dict[str, Any]:
        """
        Execute an application launch.

        Args:
            intent: Parsed Intent with action and target

        Returns:
            Dict with execution results
        """
        action = intent.action.lower() if intent.action else ""
        target = intent.target if intent.target else ""

        if action in ("open", "launch", "start", "run"):
            return self._open_app(target)

        return {
            "success": False,
            "status": "unknown_action",
            "error": f"AppLauncher does not support action: {action}",
        }

    # ------------------------------------------------------------------
    # Application launching
    # ------------------------------------------------------------------

    def _open_app(self, target: str) -> dict[str, Any]:
        """
        Open an application by name or alias.

        Uses self.knowledge for entity lookup (DI pattern).
        """
        logger.debug(f"Opening application: {target}")

        target = target.lower().strip()
        if not target:
            return {
                "success": False,
                "status": "error",
                "error": "No target specified",
            }

        try:
            app = self.knowledge.find_application(target)

            if app is None:
                return {
                    "success": False,
                    "status": "not_found",
                    "error": f"Application not found: {target}",
                }

            app_path = app.get("path")
            app_name = app.get("name")

            if not app_path:
                return {
                    "success": False,
                    "status": "error",
                    "error": f"No path found for application: {app_name}",
                }

            logger.debug(f"Launching: {app_path}")
            subprocess.Popen(app_path, shell=True)
            logger.info(f"Opened {app_name}")

            return {
                "success": True,
                "status": "executed",
                "result": {"application": app_name, "path": app_path},
            }

        except Exception as e:
            logger.error(f"Error opening application: {e}")
            return {
                "success": False,
                "status": "error",
                "error": str(e),
            }
