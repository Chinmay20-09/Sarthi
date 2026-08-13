"""
User Config skill — stores user settings from chat commands persistently.

Currently supports the GitHub username used by the project_tracker skill,
so it only has to be configured once (previously it required setting the
SKILL_PROJECT_TRACKER_USERNAME environment variable on every launch).

Commands (via the chat section):
    - "set my github username to <name>"     → saves it permanently
    - "configure github username <name>"     → same as above
    - "set github username" (no value)       → prompts for the username in chat
    - "what is my github username"           → shows the saved value (or prompts)

Persistence:
    Values are stored in the SQLite ``settings`` table (key/value) through
    the centralized DatabaseManager, so they survive restarts.

ARCHITECTURE:
    Follows the standard skill contract — the Brain only calls execute(intent).
    The project_tracker skill reads the saved username through the same
    get_github_username() helper so both stay in sync.
"""

import logging
import re
from typing import Any

from brain.intent import Intent
from skills.base import BaseSkill

logger = logging.getLogger(__name__)

# Settings table key used for the GitHub username
GITHUB_USERNAME_KEY = "github_username"

# Actions that write a configuration value
SETTING_ACTIONS = {"set", "configure"}
# Actions that read/display a configuration value
QUERY_ACTIONS = {"what", "show", "status", "check"}


class UserConfigSkill(BaseSkill):
    """Saves user settings (like the GitHub username) so Sarthi remembers them."""

    name = "user_config"
    description = "Saves user settings (like your GitHub username) so Sarthi remembers them."
    version = "1.0.0"

    def __init__(self, db=None):
        """
        Initialize the user config skill.

        Args:
            db: Optional DatabaseManager instance. If None, lazily loads
                the global singleton on first use.
        """
        self._db = db

    # ------------------------------------------------------------------
    # Dependency injection
    # ------------------------------------------------------------------

    @property
    def db(self):
        """Lazily resolve the DatabaseManager instance."""
        if self._db is None:
            from database.manager import get_database

            self._db = get_database()
        return self._db

    def _ensure_table(self) -> None:
        """Ensure the settings table exists (idempotent)."""
        from database.models import CREATE_SETTINGS

        self.db.create_table(CREATE_SETTINGS)

    # ------------------------------------------------------------------
    # Persistent settings API (shared with project_tracker)
    # ------------------------------------------------------------------

    def set_github_username(self, username: str) -> bool:
        """
        Persist the GitHub username.

        Args:
            username: The GitHub username to save

        Returns:
            True if saved successfully
        """
        username = (username or "").strip()
        if not username:
            return False

        self._ensure_table()
        self.db.execute(
            "INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES (?, ?, datetime('now'))",
            (GITHUB_USERNAME_KEY, username),
        )
        logger.info(f"Saved GitHub username: {username}")
        return True

    def get_github_username(self) -> str | None:
        """
        Read the saved GitHub username.

        Returns:
            The saved username, or None if not configured yet
        """
        self._ensure_table()
        row = self.db.fetch_one(
            "SELECT value FROM settings WHERE key = ?", (GITHUB_USERNAME_KEY,)
        )
        return row["value"] if row else None

    # ------------------------------------------------------------------
    # BaseSkill interface
    # ------------------------------------------------------------------

    def execute(self, intent: Intent) -> dict[str, Any]:
        """
        Handle configuration commands.

        Owns intents that set or ask about the GitHub username:
            - action "set"/"configure" with github/username in the target
            - action "what"/"show"/"status"/"check" with username in the target
        """
        action = (intent.action or "").lower()
        target = (intent.target or "").lower()

        wants_set = action in SETTING_ACTIONS and ("github" in target or "username" in target)
        wants_query = action in QUERY_ACTIONS and "username" in target

        if wants_set:
            username = self._extract_username(intent.target)
            if username:
                if not self.set_github_username(username):
                    return {
                        "success": False,
                        "status": "error",
                        "error": "Could not save the GitHub username.",
                    }
                return {
                    "success": True,
                    "status": "executed",
                    "result": {"setting": GITHUB_USERNAME_KEY, "value": username},
                }
            # No value provided — prompt for it in the chat UI
            return self._prompt_result()

        if wants_query:
            saved = self.get_github_username()
            if saved:
                return {
                    "success": True,
                    "status": "executed",
                    "result": {
                        "setting": GITHUB_USERNAME_KEY,
                        "value": saved,
                        "message": f"Your GitHub username is {saved}.",
                    },
                }
            return self._prompt_result()

        # Not our command — let other skills try
        return {
            "success": False,
            "status": "unknown",
            "error": f"Unknown command: {intent.action} {intent.target}",
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _extract_username(self, target: str) -> str | None:
        """
        Pull the username out of a raw intent target.

        Handles forms like:
            "github username octocat"  ("to" is already stripped by the interpreter)
            "github octocat"
            "username octocat"
            "octocat"
            "github username"  → None (missing value)
        """
        text = re.sub(r"\s+", " ", (target or "").strip()).lower()

        # Strip known prefixes ("github username", "github", "username")
        for prefix in ("github username", "github user name", "github", "username", "user name"):
            if text.startswith(prefix):
                text = text[len(prefix):].lstrip()
                break

        # Strip any leading connectors that survived interpretation
        for connector in ("to ", "as ", "is ", "=", ":"):
            if text.startswith(connector):
                text = text[len(connector):].strip()
                break

        username = text.strip()
        return username or None

    def _prompt_result(self) -> dict[str, Any]:
        """Result that makes the chat UI render an input card asking for the username."""
        return {
            "success": False,
            "status": "needs_input",
            "handled": True,
            "error": (
                "What is your GitHub username? Type it below and I'll save it "
                "so you never have to configure it again."
            ),
            "result": {
                "visual": {
                    "type": "github_username_prompt",
                    "data": {"key": GITHUB_USERNAME_KEY},
                }
            },
        }
