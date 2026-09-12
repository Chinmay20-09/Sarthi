"""Personal Context skill — safely retrieve specific user-provided personal
information when required for a task.

ARCHITECTURE:
    The skill NEVER touches the database directly. It delegates every lookup
    to PersonalContextService, which owns the only allowed database access.

    Brain path (this module): answers direct questions like "what is my email"
    or "what is my college" through the executor's skill fallback.
    Hermes path (hermes/tools/personal_context.py): Hermes requests one safe
    field through the tool registry; the tool calls the same service.

    Ownership is deliberately narrow:
        - queries only ("what"/"show"/"check" actions)
        - target mentions a recognised personal field
        - targets mentioning project/repo/username words are left to the
          project_tracker and user_config skills.

    Retrieval is display-only. External submission of this information (e.g.
    form filling) is a future workflow that must add a confirmation boundary.
"""

import logging
from typing import Any

from brain.intent import Intent
from skills.base import BaseSkill

from .fields import FIELD_ALIASES, display_name, normalize_field
from .service import PersonalContextService

logger = logging.getLogger(__name__)

# Actions this skill answers. "check"/"status" are deliberately excluded —
# "check github" / "status github" belong to the project_tracker skill.
QUERY_ACTIONS = {"what", "show"}

# Words that route an intent to another skill instead (project_tracker,
# user_config). When any appears in the target, this skill declines.
NOT_OWNED_WORDS = {
    "project",
    "projects",
    "repo",
    "repos",
    "status",
    "pending",
    "sync",
    "new",
    "username",
    "tracker",
    "profile",
    "all",
    "everything",
}


class PersonalContextSkill(BaseSkill):
    """Answers questions about stored personal profile fields."""

    name = "personal_context"
    description = (
        "Safely retrieve specific user-provided personal information when required for a task."
    )
    version = "1.0.0"

    def __init__(self, service: PersonalContextService | None = None):
        """
        Initialize the skill.

        Args:
            service: PersonalContextService instance. If None, lazily loads
                the default service on first use.
        """
        self._service = service

    # ------------------------------------------------------------------
    # Dependency injection
    # ------------------------------------------------------------------

    @property
    def service(self) -> PersonalContextService:
        """Lazily resolve the PersonalContextService."""
        if self._service is None:
            self._service = PersonalContextService()
        return self._service

    # ------------------------------------------------------------------
    # BaseSkill interface
    # ------------------------------------------------------------------

    def execute(self, intent: Intent) -> dict[str, Any]:
        """
        Answer a personal-information query, or decline politely.

        Args:
            intent: Parsed intent (e.g. action="what", target="email").

        Returns:
            Dict with success/status/result. When this skill owns the query
            but no value is stored, handled=True keeps the fallback from
            overriding the honest "not stored" answer.
        """
        action = (intent.action or "").lower()
        target = (intent.target or "").lower()

        if action not in QUERY_ACTIONS:
            return self._decline(intent)

        target_words = set(target.split())
        if target_words & NOT_OWNED_WORDS:
            return self._decline(intent)

        field = self._find_field(target)
        if field is None:
            return self._decline(intent)

        result = self.service.get_field(field)
        if result.get("success"):
            label = display_name(field)
            return {
                "success": True,
                "status": "executed",
                "result": {
                    "message": f"Your {label} is {result['value']}.",
                    "field": result["field"],
                    "value": result["value"],
                    "category": result.get("category"),
                },
            }

        error = result.get("error") or "No personal information is stored for this field."
        return {
            "success": False,
            "status": "error",
            "handled": True,  # own the answer so the NLP fallback can't invent one
            "error": error,
            "result": {
                "field": result.get("field") or normalize_field(field),
                "value": None,
            },
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _find_field(self, target: str) -> str | None:
        """Map a target phrase to a canonical safe field name, or None."""
        for alias, canonical in FIELD_ALIASES.items():
            if alias in target:
                return canonical
        return None

    @staticmethod
    def _decline(intent: Intent) -> dict[str, Any]:
        """Not our command — let other skills (and the NLP fallback) try."""
        return {
            "success": False,
            "status": "unknown",
            "error": f"Unknown command: {intent.action} {intent.target}",
        }
