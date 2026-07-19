"""
Executor for Sarthi's Brain.

Dispatches resolved intents to the appropriate handler.
Supports skill-based dispatch where each capability is a separate skill.

The Executor maintains a registry of handlers:
    - Built-in handlers (e.g., open_app, open_site from actions/)
    - Skill handlers (loaded from skills/ directory)
    - Fallback handler for unknown actions
"""

import logging
from collections.abc import Callable
from typing import Any

from brain.context import BrainContext
from brain.intent import Intent

logger = logging.getLogger(__name__)


# Type alias for intent handler functions
IntentHandler = Callable[[Intent], dict[str, Any] | None]


class BrainExecutor:
    """
    Dispatches intents to registered handlers.

    Maintains a handler registry. Built-in handlers for common actions
    (open apps, open websites) are registered by default.

    Skills can register their own handlers via register_handler().
    """

    def __init__(self):
        """Initialize executor with default handlers."""
        self._handlers: dict[str, IntentHandler] = {}
        self._default_handler: IntentHandler | None = None
        self._register_builtin_handlers()

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register_handler(self, action: str, handler: IntentHandler) -> None:
        """
        Register a handler for a specific action.

        Args:
            action: The action string (e.g., "open", "search", "play")
            handler: Function that takes an Intent and returns result dict
        """
        self._handlers[action] = handler
        logger.debug(f"Registered handler for action '{action}'")

    def set_default_handler(self, handler: IntentHandler) -> None:
        """Set the fallback handler for unrecognized actions."""
        self._default_handler = handler
        logger.debug("Registered default handler")

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    def execute(self, intent: Intent, context: BrainContext | None = None) -> dict[str, Any]:
        """
        Execute an intent by dispatching to the appropriate handler.

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

        # Find handler for this action
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

        # Try default handler if no specific handler found
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
