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
                # Dict results carry their own success/status/result through
                # (e.g. a needs_decision prompt from the app launcher)
                if isinstance(result, dict):
                    return {
                        "success": result.get("success", True),
                        "status": result.get("status", "executed"),
                        "result": result.get("result", result),
                        "error": result.get("error"),
                    }
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

                # A skill signals ownership of an intent it couldn't fulfill
                # (e.g. not_configured, needs_input) with handled=True. It
                # owns the intent — return its message immediately so a later
                # fallback skill (Natural Language Processor) cannot override
                # it with a generic conversation.
                if isinstance(result, dict) and result.get("handled"):
                    logger.debug(f"Skill '{skill.name}' claimed intent: {action} {intent.target}")
                    return {
                        "success": False,
                        "status": result.get("status", "error"),
                        "result": result.get("result"),
                        "error": result.get("error")
                        or f"Skill '{skill.name}' could not handle: {action} {intent.target}",
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
            from skills.app_launcher.main import AppLauncherSkill
            from skills.browser.main import BrowserSkill

            def handle_open(intent: Intent) -> dict[str, Any] | None:
                """Handle 'open' action — try website first, then app."""
                target = intent.target
                if not target:
                    return {"success": False, "status": "error", "error": "No target specified"}

                # Try opening as a website first
                site_result = BrowserSkill().execute(Intent(action="open", target=target))
                if site_result.get("success"):
                    info = site_result.get("result") or {}
                    return {
                        "action": "open_website",
                        "target": target,
                        "website": info.get("website", target),
                        "url": info.get("url", ""),
                    }

                # Fall back to opening as an application (favourites-gated)
                app_result = AppLauncherSkill().execute(Intent(action="open", target=target))
                if app_result.get("success"):
                    info = app_result.get("result") or {}
                    return {
                        "action": "open_application",
                        "target": target,
                        "application": info.get("application", target),
                        "path": info.get("path", ""),
                    }

                # needs_decision (ignored/unattended) and failures pass through
                return app_result

            self.register_handler("open", handle_open)

        except ImportError as e:
            logger.warning(f"Could not register built-in handlers: {e}")

        # Memory commands (/remember, /recall, /forget) — persisted to the
        # knowledge_memory table so the model can remember user facts.
        # Registered outside the try block: they need no app/browser imports.
        self.register_handler("remember", self._handle_remember)
        self.register_handler("recall", self._handle_recall)
        self.register_handler("forget", self._handle_forget)
        # Task cleanup — clean task history
        self.register_handler("clean", self._handle_clean)

    # ------------------------------------------------------------------
    # Memory handlers (/remember, /recall, /forget)
    # ------------------------------------------------------------------

    @staticmethod
    def _handle_remember(intent: Intent) -> dict[str, Any] | None:
        """Handle 'remember' — persist a fact to long-term memory."""
        from knowledge.memory import get_memory

        memory = get_memory()
        text = (intent.target or "").strip()
        if not text:
            return {
                "success": False,
                "status": "error",
                "error": "Nothing to remember. Try: /remember my name is Alice",
            }

        key, value = BrainExecutor._split_memory_entry(text)
        if not memory.remember_long(key, value):
            return {"success": False, "status": "error", "error": "Could not save to memory."}
        return {
            "success": True,
            "status": "executed",
            "result": {
                "message": f"Got it — I'll remember: {value}",
                "key": key,
                "value": value,
            },
        }

    @staticmethod
    def _handle_recall(intent: Intent) -> dict[str, Any] | None:
        """Handle 'recall' — return a saved memory (or list them all)."""
        from knowledge.memory import get_memory

        memory = get_memory()
        key = (intent.target or "").strip()
        if not key:
            memories = memory.list_memories()
            if not memories:
                return {
                    "success": False,
                    "status": "error",
                    "error": "I don't have anything saved yet.",
                }
            lines = "\n".join(f"{m['key']}: {m['value']}" for m in memories)
            return {"success": True, "status": "executed", "result": {"message": lines}}

        value = memory.recall_long(key)
        if value is None:
            return {
                "success": False,
                "status": "error",
                "error": f"I don't remember anything for '{key}'.",
            }
        return {
            "success": True,
            "status": "executed",
            "result": {"message": value, "key": key, "value": value},
        }

    @staticmethod
    def _handle_forget(intent: Intent) -> dict[str, Any] | None:
        """Handle 'forget' — delete a saved memory."""
        from knowledge.memory import get_memory

        key = (intent.target or "").strip()
        if not key:
            return {
                "success": False,
                "status": "error",
                "error": "Forget what? Try: /forget <key>",
            }
        if not get_memory().forget_long(key):
            return {"success": False, "status": "error", "error": "Could not forget that."}
        return {"success": True, "status": "executed", "result": {"message": f"Forgot: {key}"}}

    @staticmethod
    def _split_memory_entry(text: str) -> tuple[str, str]:
        """
        Split '/remember key: value' into (key, value).

        Accepts "key: value" or "key = value"; otherwise an auto-key
        (note_1, note_2, ...) is generated so plain facts like
        "/remember my name is Alice" still get stored.
        """
        for sep in (": ", " = "):
            if sep in text:
                key, value = text.split(sep, 1)
                key = key.strip().lower().replace(" ", "_")
                value = value.strip()
                if key and value:
                    return key, value

        return BrainExecutor._next_note_key(), text.strip()

    @staticmethod
    def _next_note_key() -> str:
        """Next auto-key like note_1, note_2, ... (past the highest existing)."""
        from knowledge.memory import get_memory

        numbers = []
        for m in get_memory().list_memories():
            key = m.get("key", "")
            if key.startswith("note_"):
                try:
                    numbers.append(int(key[len("note_") :]))
                except ValueError:
                    continue
        return f"note_{max(numbers, default=0) + 1}"

    # ------------------------------------------------------------------
    # Cleanup handler (/clean)
    # ------------------------------------------------------------------

    @staticmethod
    def _handle_clean(intent: Intent) -> dict[str, Any] | None:
        """Handle '/clear' — clean successful sandbox tasks, keep failed ones.

        Successful task directories and index entries are removed.
        Failed tasks are kept for review.
        The database (command_history, memory, chat) is never touched.
        """
        import json
        import shutil

        from hermes.config.loader import ConfigLoader
        from hermes.sandbox import TaskSandbox

        sandbox = TaskSandbox(ConfigLoader().load().sandbox_path)
        index = sandbox._load_index()

        if not index:
            return {
                "success": True,
                "status": "executed",
                "result": {
                    "message": "Sandbox is already clean — no tasks found.",
                    "deleted_count": 0,
                    "failed_count": 0,
                },
            }

        deleted_count = 0
        failed_records: list[dict] = []
        queries_to_remove: list[str] = []

        for query, records in index.items():
            still_has_failed = False
            for rec in records:
                task_id = rec.get("task_id", "")
                if rec.get("status") == "success":
                    # Delete the successful task directory
                    task_dir = sandbox._tasks_dir / task_id
                    if task_dir.is_dir():
                        shutil.rmtree(task_dir)
                    deleted_count += 1
                else:
                    failed_records.append(rec)
                    still_has_failed = True
            if not still_has_failed:
                queries_to_remove.append(query)

        # Prune queries that had no remaining failures
        for query in queries_to_remove:
            del index[query]

        # Rewrite the index with only failed entries
        sandbox._root.mkdir(parents=True, exist_ok=True)
        sandbox._index_path.write_text(
            json.dumps(index, indent=2), encoding="utf-8"
        )

        if failed_records:
            message = (
                f"Cleared {deleted_count} successful sandbox task(s). "
                f"{len(failed_records)} failed task(s) kept for review."
            )
        else:
            message = (
                f"All done! Cleared {deleted_count} successful sandbox task(s). "
                f"Sandbox is now empty."
            )

        return {
            "success": True,
            "status": "executed",
            "result": {
                "message": message,
                "deleted_count": deleted_count,
                "failed_count": len(failed_records),
            },
        }
