"""
Automation Engine — Skill Wrapper.

Wraps the AutomationEngine as a BaseSkill so it can be
discovered and invoked through the standard skill interface.

The AutomationEngine itself handles:
    - Running assistants (BrainAssistant)
    - Generating assistant.json from manifest.json
    - Previewing and applying changes

This skill wrapper provides:
    - execute(intent) — BaseSkill-compatible entry point
    - manifest.json — Allows discovery by SkillManager
"""

from typing import Any

from brain.intent import Intent
from config import SKILLS_DIR
from skills.base import BaseSkill

from .assistants.brain_assistant.main import BrainAssistant
from .engine import AutomationEngine


class AutomationSkill(BaseSkill):
    """
    Wraps the AutomationEngine as a discoverable skill.

    The Brain can call skill.execute(intent) to trigger
    automation workflows.
    """

    name = "automation_engine"
    description = "Generates assistant configs and automates code generation"
    version = "1.0.0"

    def __init__(self):
        self.engine = AutomationEngine()
        self.engine.register_assistant(BrainAssistant())

    def execute(self, intent: Intent) -> dict[str, Any]:
        """
        Execute an automation command.

        Currently supports:
            - "generate assistant for <skill>" — generate assistant.json

        Args:
            intent: Parsed Intent from the brain pipeline

        Returns:
            Dict with execution results
        """
        action = intent.action.lower()
        target = intent.target.lower()

        if "generate" in action or "generate" in target:
            return self._handle_generate(target)

        if "analyze" in action:
            return self._handle_analyze(target)

        return {
            "success": False,
            "status": "unknown_command",
            "error": f"Unsupported automation command: {action} {target}",
        }

    def _handle_generate(self, target: str) -> dict[str, Any]:
        """Generate assistant.json for a skill."""
        skill_folder = SKILLS_DIR / target
        if not skill_folder.exists():
            return {
                "success": False,
                "status": "skill_not_found",
                "error": f"Skill not found: {target}",
            }

        assistant = BrainAssistant()
        result = assistant.analyze(skill_folder)

        return {
            "success": True,
            "status": "generated",
            "result": {"path": str(result)},
        }

    def _handle_analyze(self, target: str) -> dict[str, Any]:
        """Analyze a skill's capabilities (stub)."""
        return {
            "success": True,
            "status": "analyzed",
            "result": {"target": target, "capabilities": []},
        }
