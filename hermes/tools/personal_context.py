"""personal_context tool — safely retrieve one specific personal profile field.

This tool does NOT access the database. It delegates to
PersonalContextService (skills/personal_context/service.py), the only
component allowed to read personal data. Hermes requests exactly one safe
field per call; secrets, unknown fields, and whole-profile requests fail
safely, and no arbitrary SQL or table names are ever accepted.

Flow:
    Hermes -> personal_context tool -> PersonalContextService -> Database
"""

import logging
from typing import Any

from .base import BaseTool, ToolResult

logger = logging.getLogger(__name__)

# Available safe fields, for the tool description (names only — never values).
from skills.personal_context.fields import SAFE_FIELDS  # noqa: E402

_FIELD_LIST = ", ".join(sorted(SAFE_FIELDS))


class PersonalContextTool(BaseTool):
    """Retrieve a specific safe personal profile field when required for a task."""

    name = "personal_context"
    description = (
        "Retrieve a specific safe personal profile field when required for a task. "
        f"Available fields: {_FIELD_LIST}. "
        "Use operation 'list_available_fields' to see which fields are actually stored."
    )
    parameters = {
        "type": "object",
        "properties": {
            "field": {
                "type": "string",
                "description": (
                    f"The exact personal profile field required (one of: {_FIELD_LIST})."
                ),
            },
            "operation": {
                "type": "string",
                "description": (
                    "Optional. 'list_available_fields' returns the names of "
                    "stored fields; omit (or 'get_field') to retrieve one field."
                ),
            },
        },
    }

    # ------------------------------------------------------------------
    # Service wiring (patched in tests)
    # ------------------------------------------------------------------

    def _get_service(self):
        """Instantiate the PersonalContextService (the DB-facing component)."""
        from skills.personal_context.service import PersonalContextService

        return PersonalContextService()

    # ------------------------------------------------------------------
    # BaseTool interface
    # ------------------------------------------------------------------

    def execute(self, arguments: dict[str, Any]) -> ToolResult:
        """Validate the request and delegate to the personal context service."""
        operation = str(arguments.get("operation") or "get_field").strip().lower()

        if operation == "list_available_fields":
            try:
                fields = self._get_service().list_available_fields()
            except Exception as e:  # never leak internals upward
                logger.error("personal_context list failed: %s", e)
                return ToolResult(
                    success=False,
                    tool=self.name,
                    error="Personal information could not be checked right now.",
                )
            summary = ", ".join(fields) if fields else "(no personal information stored)"
            return ToolResult(
                success=True,
                tool=self.name,
                result=f"Stored personal fields: {summary}",
                data={"fields": fields},
            )

        if operation not in ("get_field", ""):
            return ToolResult(
                success=False,
                tool=self.name,
                error=("Unknown operation. Use 'get_field' (default) or 'list_available_fields'."),
                invalid=True,
            )

        field = str(arguments.get("field") or "").strip()
        if not field:
            return ToolResult(
                success=False,
                tool=self.name,
                error=(
                    "A field is required. Use list_available_fields to see which fields are stored."
                ),
                invalid=True,
            )

        try:
            result = self._get_service().get_field(field)
        except Exception as e:  # never leak internals upward
            logger.error("personal_context lookup failed for '%s': %s", field, e)
            return ToolResult(
                success=False,
                tool=self.name,
                error="The personal information could not be retrieved right now.",
            )

        if result.get("success"):
            return ToolResult(
                success=True,
                tool=self.name,
                result=f"{result['field']}: {result['value']}",
                data={
                    "field": result.get("field"),
                    "value": result.get("value"),
                    "category": result.get("category"),
                },
            )

        return ToolResult(
            success=False,
            tool=self.name,
            error=result.get("error") or "The personal information is not available.",
            data={"field": result.get("field")},
        )
