"""
BaseSkill — abstract contract for all Sarthi skills.

Every skill MUST implement this interface to be compatible with
the Brain's executor dispatch system.

The Brain only knows about skill.execute(intent).
It never accesses internal skill implementation.

Usage:
    class MySkill(BaseSkill):
        name = "my_skill"
        description = "Does something useful"

        def execute(self, intent: Intent) -> Dict[str, Any]:
            if intent.action == "do_thing":
                return {"success": True, "result": "Done!"}
            return {"success": False, "error": f"Unknown action: {intent.action}"}
"""

from abc import ABC, abstractmethod
from typing import Any

from brain.intent import Intent


class BaseSkill(ABC):
    """
    Abstract base class for all Sarthi skills.

    Every skill MUST implement execute(intent) to be compatible
    with the Brain's executor dispatch system.

    The Brain only knows about skill.execute(intent).
    It never accesses internal skill implementation.

    Attributes:
        name: Human-readable skill name (displayed in UI, logs)
        description: Brief description of the skill's purpose
        version: Semantic version string

    Subclasses must implement:
        execute(self, intent: Intent) -> Dict[str, Any]

    Usage:
        class MySkill(BaseSkill):
            name = "my_skill"
            description = "Does something useful"

            def execute(self, intent: Intent) -> Dict[str, Any]:
                if intent.action == "do_thing":
                    return {"success": True, "result": "Done!"}
                return {"success": False, "error": f"Unknown action: {intent.action}"}
    """

    name: str = "unnamed_skill"
    description: str = ""
    version: str = "0.1.0"

    @abstractmethod
    def execute(self, intent: Intent) -> dict[str, Any]:
        """
        Execute a command based on a parsed intent.

        This is the ONLY method the Brain calls on skills.
        The Brain never accesses internal implementation details.

        Args:
            intent: Parsed Intent from the brain pipeline
                   (intent.action, intent.target, intent.confidence)

        Returns:
            Dict with execution results:
                - success: bool
                - status: str (summary message)
                - result: Any (optional result data)
                - error: str (error message if failed)
        """
        ...

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} '{self.name}'>"
