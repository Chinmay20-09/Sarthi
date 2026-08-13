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
            return self._open_app(target, force=bool(getattr(intent, "force", False)))

        if action == "run_anyway":
            # Explicit bypass of the favourites gate (Run Anyway button)
            return self._open_app(target, force=True)

        return {
            "success": False,
            "status": "unknown_action",
            "error": f"AppLauncher does not support action: {action}",
        }

    # ------------------------------------------------------------------
    # Application launching
    # ------------------------------------------------------------------

    def _open_app(self, target: str, force: bool = False) -> dict[str, Any]:
        """
        Open an application by name or alias.

        Favourites launch directly. Apps in the ``ignored`` or ``unattended``
        categories return a ``needs_decision`` result so the chat UI can
        prompt the user (Favourite / Ignore / Run Anyway) before launching.
        ``force=True`` bypasses the gate (Run Anyway).

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
                    "error": (
                        f"Application not found: {target}. "
                        f"Ask me to 'scan my system' to discover it."
                    ),
                }

            app_path = app.get("path")
            app_name = app.get("name")
            app_status = app.get("app_status", "favourite")

            if not app_path:
                return {
                    "success": False,
                    "status": "error",
                    "error": f"No path found for application: {app_name}",
                }

            # Only favourites launch directly — everything else needs a decision
            if app_status != "favourite" and not force:
                return {
                    "success": False,
                    "status": "needs_decision",
                    "handled": True,
                    "error": (
                        f"{app_name} is {'in your ignored list' if app_status == 'ignored' else 'not categorized yet'}."
                    ),
                    "result": {
                        "visual": {
                            "type": "app_decision",
                            "data": {
                                "name": app_name,
                                "path": app_path,
                                "app_status": app_status,
                            },
                        }
                    },
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
