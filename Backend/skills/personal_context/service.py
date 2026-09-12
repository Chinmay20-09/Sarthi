"""Personal Context Service — the ONLY component that reads personal data.

Architecture:
    Hermes
      -> personal_context tool
        -> PersonalContextService   (this module)
          -> DatabaseManager        (settings table)

The service is the privacy boundary. It accepts a *field name*, never SQL,
never a table name, never arbitrary keys. Lookups are:
    - allowlisted:  only SAFE_FIELDS are ever read (SECRET_FIELDS are refused
                    before any database access)
    - parameterised: the value reaches SQL only as a bound parameter
    - least-privilege: one field per call — the full profile is never returned

Values live in the existing ``settings`` key/value table (the same table the
user_config skill writes "github_username" to). No new database system, no
second abstraction — this reuses DatabaseManager.
"""

import logging
from typing import Any

from database.manager import DatabaseManager, get_database
from database.models import CREATE_SETTINGS

from .fields import FIELD_CATEGORIES, SAFE_FIELDS, SECRET_FIELDS, normalize_field, storage_key

logger = logging.getLogger(__name__)

# Safe, user-facing messages (never leak internals).
NOT_STORED = "No personal information is stored for this field."
UNKNOWN_FIELD = "Unknown personal field. Use list_available_fields to see which fields are stored."
BLOCKED_FIELD = "This field is blocked and cannot be retrieved."


class PersonalContextService:
    """Controlled, read-only retrieval of safe personal profile fields."""

    def __init__(self, db: DatabaseManager | None = None):
        """
        Initialize the service.

        Args:
            db: DatabaseManager instance. If None, uses the global singleton.
        """
        self._db = db

    # ------------------------------------------------------------------
    # Dependency injection
    # ------------------------------------------------------------------

    @property
    def db(self) -> DatabaseManager:
        """Lazily resolve the shared DatabaseManager instance."""
        if self._db is None:
            self._db = get_database()
        return self._db

    def _ensure_table(self) -> None:
        """Ensure the settings table exists (idempotent, shared schema)."""
        self.db.create_table(CREATE_SETTINGS)

    # ------------------------------------------------------------------
    # Retrieval API
    # ------------------------------------------------------------------

    def get_field(self, field: str | None) -> dict[str, Any]:
        """
        Retrieve ONE safe personal field by name.

        Args:
            field: The canonical field name (e.g. "github", "email").

        Returns:
            Dict with success/field/value/error/category:
                {"success": True, "field": "github", "value": "...", "error": None, "category": "links"}
                {"success": False, "field": ..., "value": None, "error": "...", "category": ...}
        """
        field = normalize_field(field)
        category = self._category_of(field)

        # Secrets are refused up front — the database is never touched for them.
        if field in SECRET_FIELDS:
            logger.info("personal_context: blocked retrieval attempt for field '%s'", field)
            return self._result(False, field, None, BLOCKED_FIELD, category)

        # Unknown fields fail safely before any query is built.
        if field not in SAFE_FIELDS:
            logger.info("personal_context: unknown field requested: '%s'", field)
            return self._result(False, field, None, UNKNOWN_FIELD, None)

        try:
            self._ensure_table()
            # storage_key() only ever returns an allowlisted key for a safe field.
            row = self.db.fetch_one(
                "SELECT value FROM settings WHERE key = ?",
                (storage_key(field),),
            )
        except Exception as e:  # never leak internals upward
            logger.error("personal_context: lookup failed for field '%s': %s", field, e)
            return self._result(
                False, field, None, "The value could not be retrieved right now.", category
            )

        value = (row or {}).get("value")
        if value is None or str(value).strip() == "":
            logger.info("personal_context: no stored value for field '%s'", field)
            return self._result(False, field, None, NOT_STORED, category)

        logger.info("personal_context: retrieved field '%s'", field)  # name only — never the value
        return self._result(True, field, value, None, category)

    def list_available_fields(self) -> list[str]:
        """
        Names of safe fields that actually have stored values.

        Returns field NAMES only — never values. Used by the tool so Hermes
        can ask about fields that exist instead of guessing.
        """
        try:
            self._ensure_table()
            keys = [storage_key(field) for field in sorted(SAFE_FIELDS)]
            placeholders = ",".join("?" for _ in keys)
            rows = self.db.fetch_all(
                "SELECT key FROM settings "
                f"WHERE key IN ({placeholders}) AND value IS NOT NULL AND value != ''",
                tuple(keys),
            )
        except Exception as e:
            logger.error("personal_context: list_available_fields failed: %s", e)
            return []

        stored_keys = {row["key"] for row in rows}
        return [field for field in sorted(SAFE_FIELDS) if storage_key(field) in stored_keys]

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _category_of(self, field: str) -> str | None:
        """The logical category a safe field belongs to, or None."""
        for category, fields in FIELD_CATEGORIES.items():
            if field in fields:
                return category
        return None

    @staticmethod
    def _result(
        success: bool, field: str, value: Any, error: str | None, category: str | None
    ) -> dict[str, Any]:
        """Build the structured result dict used by the tool and skill."""
        return {
            "success": success,
            "field": field,
            "value": value,
            "error": error,
            "category": category,
        }
