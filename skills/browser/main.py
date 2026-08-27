"""
Browser Skill for Sarthi.

Opens websites in the default browser via the Knowledge Layer.
Uses injected KnowledgeManager via self.knowledge (DI pattern).

ARCHITECTURE:
    This skill communicates ONLY through the Knowledge Layer.
    It never accesses databases or JSON files directly.
    Dependencies are injected via BaseSkill constructor.
"""

import logging
import webbrowser
from typing import Any

from brain.intent import Intent
from brain.modes import get_test_mode
from skills.base import BaseSkill

logger = logging.getLogger(__name__)


class BrowserSkill(BaseSkill):
    """
    Browser skill.

    Opens websites by name or alias in the default browser.
    Uses Knowledge Layer for website lookup.

    Usage:
        skill = BrowserSkill(knowledge_manager=manager)
        result = skill.execute(Intent(action="open", target="google"))
    """

    name = "browser"
    description = "Opens websites in the default browser via the Knowledge Layer"
    version = "1.0.0"

    # ------------------------------------------------------------------
    # BaseSkill interface
    # ------------------------------------------------------------------

    def execute(self, intent: Intent) -> dict[str, Any]:
        """
        Execute a website open.

        Args:
            intent: Parsed Intent with action and target

        Returns:
            Dict with execution results
        """
        action = intent.action.lower() if intent.action else ""
        target = intent.target if intent.target else ""

        if action in ("open", "launch", "start", "go"):
            return self._open_website(target)

        return {
            "success": False,
            "status": "unknown_action",
            "error": f"Browser does not support action: {action}",
        }

    # ------------------------------------------------------------------
    # Website opening
    # ------------------------------------------------------------------

    def _open_website(self, target: str) -> dict[str, Any]:
        """
        Open a website by name or alias.

        Uses self.knowledge for entity lookup (DI pattern).
        """
        logger.debug(f"Opening website: {target}")

        target = target.lower().strip()
        if not target:
            return {
                "success": False,
                "status": "error",
                "error": "No target specified",
            }

        try:
            website = self.knowledge.find_website(target)

            if website is None:
                return {
                    "success": False,
                    "status": "not_found",
                    "error": f"Website not found: {target}",
                }

            url = website.get("url")
            name = website.get("name")

            if not url:
                return {
                    "success": False,
                    "status": "error",
                    "error": f"No URL found for website: {name}",
                }

            if get_test_mode():
                logger.info(f"[TEST] Would open {name} at {url}")
                return {
                    "success": True,
                    "status": "test_mode",
                    "result": {"website": name, "url": url, "test_mode": True},
                }

            webbrowser.open(url)
            logger.info(f"Opened {name} at {url}")

            return {
                "success": True,
                "status": "executed",
                "result": {"website": name, "url": url},
            }

        except Exception as e:
            logger.error(f"Error opening website: {e}")
            return {
                "success": False,
                "status": "error",
                "error": str(e),
            }
