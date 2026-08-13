"""
BaseSkill — abstract contract for all Sarthi skills.

Every skill MUST implement this interface to be compatible with
the Brain's executor dispatch system.

The Brain only knows about skill.execute(intent).
It never accesses internal skill implementation.

ARCHITECTURE:
    Skills receive dependencies via constructor injection:
        - knowledge_manager (KnowledgeManager): Access to the Knowledge Layer
        - event_bus (EventBus): Access to the event system

    Skills NEVER import database modules directly.
    Skills communicate ONLY through the Knowledge Layer.

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
        knowledge_manager: Injected KnowledgeManager instance (optional)

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

    def __init__(self, knowledge_manager=None, event_bus=None):
        """
        Initialize a skill with dependency injection.

        Args:
            knowledge_manager: Optional KnowledgeManager instance.
                              If None, lazily loaded from get_manager() on first use.
            event_bus: Optional EventBus instance.
                      If None, lazily loaded from get_bus() on first use.
        """
        self._knowledge_manager = knowledge_manager
        self._event_bus = event_bus

    # ------------------------------------------------------------------
    # Dependency Injection Properties
    # ------------------------------------------------------------------

    @property
    def knowledge(self):
        """
        Get the KnowledgeManager (lazy-loaded with DI support).

        Skills should use this property instead of importing get_manager() directly.
        """
        if self._knowledge_manager is None:
            from knowledge.manager import get_manager

            self._knowledge_manager = get_manager()
        return self._knowledge_manager

    @property
    def events(self):
        """
        Get the EventBus (lazy-loaded with DI support).

        Skills should use this property instead of importing get_bus() directly.
        """
        if self._event_bus is None:
            from events import get_bus

            self._event_bus = get_bus()
        return self._event_bus

    # ------------------------------------------------------------------
    # Abstract Interface
    # ------------------------------------------------------------------

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
