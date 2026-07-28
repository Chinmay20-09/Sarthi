"""
Scanner Skill for Sarthi.

Discovers installed applications, games, and websites from the system
and passes results to the Knowledge Layer.

The scanner is a skill like any other. It NEVER edits databases directly.
It scans the system and returns results. The Knowledge Layer handles
persistence.

ARCHITECTURE:
    ScannerSkill lives in skills/ (not knowledge/) because scanning
    is a capability/ability, not a data operation.

    ScannerSkill uses self.knowledge (DI) for persistence.
    The actual scanner logic is in skills/scanner/application_scanner.py.
    No other module should scan applications directly.
"""

import logging
from typing import Any

from brain.intent import Intent
from skills.base import BaseSkill

logger = logging.getLogger(__name__)


class ScannerSkill(BaseSkill):
    """
    System scanner skill.

    Discovers and catalogs installed applications, games, and websites.
    Results are passed to the Knowledge Layer for persistence.

    Usage:
        skill = ScannerSkill(knowledge_manager=manager)
        skill.execute(intent)
    """

    name = "scanner"
    description = "Discovers installed applications and games from the system"
    version = "1.0.0"

    # ------------------------------------------------------------------
    # BaseSkill interface
    # ------------------------------------------------------------------

    def execute(self, intent: Intent) -> dict[str, Any]:
        """
        Execute a scan command.

        Supported actions:
            - "scan" or "refresh": Run full system scan

        Args:
            intent: Parsed Intent (action, target, confidence)

        Returns:
            Dict with execution results
        """
        action = intent.action.lower() if intent.action else ""

        if action in ("scan", "refresh", "discover"):
            return self._run_scan()

        return {
            "success": False,
            "status": "unknown",
            "error": f"Unknown scanner action: {action}",
        }

    # ------------------------------------------------------------------
    # Internal methods
    # ------------------------------------------------------------------

    def _run_scan(self) -> dict[str, Any]:
        """
        Execute full application and game discovery.

        Uses skills/scanner/application_scanner for actual scanning.
        Uses self.knowledge (DI) for persistence.
        """
        try:
            from skills.scanner.application_scanner import scan_all

            logger.info("Starting application scan...")
            applications = scan_all()

            # Save via Knowledge Layer (DI)
            self.knowledge.save_applications(applications)

            return {
                "success": True,
                "status": "scan_complete",
                "result": {
                    "applications_found": len(applications),
                },
            }
        except Exception as e:
            logger.error(f"Application scan failed: {e}")
            return {
                "success": False,
                "status": "error",
                "error": str(e),
            }
