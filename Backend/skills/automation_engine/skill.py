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
from brain.modes import get_test_mode
from config import SKILLS_DIR
from skills.base import BaseSkill

from .ai_chain.chain import run_ai_chain
from .ai_chain.parsing import parse_chain_command
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
    version = "1.1.0"

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

        # Laptop-controlled AI chains: query -> AI1 -> AI2.
        # Examples: "chain make an image from chatgpt to gemini",
        #           "/chain <query> from chatgpt to gemini".
        if action in ("chain", "automate"):
            return self._handle_chain(intent)

        if "generate" in action or "generate" in target:
            return self._handle_generate(target)

        if "analyze" in action:
            return self._handle_analyze(target)

        return {
            "success": False,
            "status": "unknown_command",
            "error": f"Unsupported automation command: {action} {target}",
        }

    def _handle_chain(self, intent: Intent) -> dict[str, Any]:
        """
        Run a query through AI1 and paste its reply into AI2.

        Sarthi takes control of the laptop (HANDS-OFF warning is shown
        before anything moves). In test mode the chain is only planned.
        """
        text = intent.raw_text or intent.target or ""
        try:
            request = parse_chain_command(text)
        except Exception as exc:
            return {
                "success": False,
                "handled": True,
                "status": "error",
                "error": f"Could not understand the chain: {exc}",
            }

        try:
            # Test mode never touches the machine — it returns the plan.
            outcome = run_ai_chain(
                query=request.query,
                ai1=request.ai1,
                ai2=request.ai2,
                save_images=request.save_images,
                execute=False if get_test_mode() else None,
            )
        except Exception as exc:
            return {
                "success": False,
                "handled": True,
                "status": "error",
                "error": f"Chain failed to start: {exc}",
            }

        return {
            "success": outcome.success,
            "handled": True,
            "status": outcome.status,
            "result": {
                "message": outcome.message,
                "ai1": request.ai1,
                "ai2": request.ai2,
                "query": request.query,
                "steps": [
                    {
                        "ai": step.site_key,
                        "prompt": step.prompt[:200],
                        "response": step.response[:500],
                        "error": step.error,
                    }
                    for step in outcome.steps
                ],
                "run_dir": str(outcome.run_dir) if outcome.run_dir else None,
            },
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
