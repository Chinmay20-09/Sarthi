"""
Executor for Sarthi's Brain.

Dispatches resolved intents to the appropriate handler.
Supports skill-based dispatch where each capability is a separate skill.

The Executor maintains a registry of handlers:
    - Built-in handlers (e.g., open_app, open_site from actions/)
    - Skill handlers (loaded from skills/ directory and registered by action)
    - Fallback: tries all registered skills when no direct handler matches
"""

import logging
from collections.abc import Callable
from typing import Any

from brain.context import BrainContext
from brain.intent import Intent
from skills.base import BaseSkill

logger = logging.getLogger(__name__)


# Type alias for intent handler functions
IntentHandler = Callable[[Intent], dict[str, Any] | None]


class BrainExecutor:
    """
    Dispatches intents to registered handlers.

    Maintains a handler registry. Built-in handlers for common actions
    (open apps, open websites) are registered by default.

    Skills can register themselves via register_skill(), which adds
    their execute() method as a fallback handler for unrecognized actions.
    """

    def __init__(self):
        """Initialize executor with default handlers."""
        self._handlers: dict[str, IntentHandler] = {}
        self._default_handler: IntentHandler | None = None
        self._skills: list[BaseSkill] = []
        self._register_builtin_handlers()

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register_handler(self, action: str, handler: IntentHandler) -> None:
        """
        Register a handler for a specific action.

        Args:
            action: The action string (e.g., "open", "search", "check")
            handler: Function that takes an Intent and returns result dict
        """
        self._handlers[action] = handler
        logger.debug(f"Registered handler for action '{action}'")

    def set_default_handler(self, handler: IntentHandler) -> None:
        """Set the fallback handler for unrecognized actions."""
        self._default_handler = handler
        logger.debug("Registered default handler")

    def register_skill(self, skill: BaseSkill) -> None:
        """
        Register a skill for intent dispatch.

        This adds the skill to the fallback pool. When no direct action
        handler matches, each registered skill's execute() method is
        tried in order.

        Args:
            skill: An instantiated BaseSkill subclass
        """
        self._skills.append(skill)
        logger.debug(f"Registered skill: {skill.name} ({skill.__class__.__name__})")

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    def execute(self, intent: Intent, context: BrainContext | None = None) -> dict[str, Any]:
        """
        Execute an intent by dispatching to the appropriate handler.

        Dispatch order:
            1. Direct action handler (e.g., "open" → open handler)
            2. Default fallback handler
            3. Registered skills (tried in order — first match wins)
            4. No handler found error

        Args:
            intent: The resolved Intent to execute
            context: Optional pipeline context for logging/debugging

        Returns:
            Dict with execution results:
                - success: bool
                - status: str
                - result: Optional result data
                - error: Optional error message
        """
        action = intent.action
        logger.debug(f"Executing intent: {action} {intent.target}")

        # Step 1: Try direct action handler
        handler = self._handlers.get(action)
        if handler:
            try:
                result = handler(intent)
                return {
                    "success": True,
                    "status": "executed",
                    "result": result,
                    "error": None,
                }
            except Exception as e:
                logger.error(f"Handler failed for action '{action}': {e}")
                return {
                    "success": False,
                    "status": "error",
                    "result": None,
                    "error": str(e),
                }

        # Step 2: Try default handler
        if self._default_handler:
            try:
                result = self._default_handler(intent)
                return {
                    "success": True,
                    "status": "executed",
                    "result": result,
                    "error": None,
                }
            except Exception as e:
                logger.error(f"Default handler failed: {e}")
                return {
                    "success": False,
                    "status": "error",
                    "result": None,
                    "error": str(e),
                }

        # Step 3: Try registered skills as fallback
        for skill in self._skills:
            try:
                result = skill.execute(intent)
                if isinstance(result, dict) and result.get("success"):
                    logger.debug(f"Skill '{skill.name}' handled intent: {action} {intent.target}")
                    return {
                        "success": True,
                        "status": result.get("status", "executed"),
                        "result": result.get("result", result),
                        "error": None,
                    }
            except Exception as e:
                logger.debug(f"Skill '{skill.name}' could not handle intent: {e}")
                continue

        # No handler found
        logger.warning(f"No handler for action '{action}'")
        return {
            "success": False,
            "status": "no_handler",
            "result": None,
            "error": f"Unknown action: {action}",
        }

    # ------------------------------------------------------------------
    # Built-in handlers
    # ------------------------------------------------------------------

    def _register_builtin_handlers(self) -> None:
        """Register default action handlers (apps, websites)."""
        try:
            from actions.apps import open_app
            from actions.browser import open_site

            def handle_open(intent: Intent) -> dict[str, Any] | None:
                """Handle 'open' action — try website first, then app."""
                target = intent.target
                if not target:
                    return {"message": "No target specified"}

                # Try opening as a website first
                if open_site(target):
                    return {"action": "open_website", "target": target}

                # Fall back to opening as an application
                if open_app(target):
                    return {"action": "open_application", "target": target}

                return {"message": f"Could not open '{target}'"}

            self.register_handler("open", handle_open)

        except ImportError as e:
            logger.warning(f"Could not register built-in handlers: {e}")
