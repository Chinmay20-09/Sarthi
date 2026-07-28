"""
Browser Skill for Sarthi.

Opens websites discovered by the Knowledge Layer.
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
from skills.base import BaseSkill

logger = logging.getLogger(__name__)


class BrowserSkill(BaseSkill):
    """
    Website opening skill.

    Opens websites by name or alias.
    Uses Knowledge Layer for entity resolution and URL lookup.

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
        Execute a website opening.

        Args:
            intent: Parsed Intent with action and target

        Returns:
            Dict with execution results
        """
        action = intent.action.lower() if intent.action else ""
        target = intent.target if intent.target else ""

        if action in ("open", "go", "navigate"):
            return self._open_site(target)

        return {
            "success": False,
            "status": "unknown_action",
            "error": f"Browser does not support action: {action}",
        }

    # ------------------------------------------------------------------
    # Website opening
    # ------------------------------------------------------------------

    def _open_site(self, target: str) -> dict[str, Any]:
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

            logger.debug(f"Opening: {url}")
            webbrowser.open(url)
            logger.info(f"Opened {name}")

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
