"""
memory_search tool — keyword search over the user's long-term /remember
facts (knowledge_memory) via the Knowledge Memory layer.

The existing knowledge_memory table stays the single source of truth. Values
are clipped before reaching the model; secret-LOOKING keys are withheld by
name exactly like the retriever does, so memory never becomes a credential
channel.
"""

import logging
from typing import Any

from .base import BaseTool, ToolResult

logger = logging.getLogger(__name__)

MAX_MEMORY_RESULTS = 10
MAX_VALUE_CHARS = 120


class MemorySearchTool(BaseTool):
    """Search the user's saved (/remember) facts by keyword."""

    name = "memory_search"
    description = (
        "Search the user's saved (/remember) facts by keyword (returns the "
        "matching fact keys and values)."
    )
    parameters = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Keyword(s) to look for in saved facts.",
            },
        },
        "required": ["query"],
    }

    def execute(self, arguments: dict[str, Any]) -> ToolResult:
        """Keyword-match knowledge_memory through the Knowledge Memory layer."""
        query = str(arguments.get("query") or "").strip()
        if not query:
            return ToolResult(
                success=False,
                tool=self.name,
                error="No search query was specified.",
                invalid=True,
            )

        try:
            from knowledge.memory import get_memory

            memories = get_memory().list_memories()
        except Exception as e:  # never leak internals upward
            logger.error("memory_search failed unexpectedly: %s", e)
            return ToolResult(
                success=False,
                tool=self.name,
                error="Saved facts are unavailable right now.",
            )

        terms = [t for t in query.lower().split() if t]
        matches = []
        for row in memories:
            key = str(row.get("key", ""))
            value = str(row.get("value", ""))
            hay = f"{key} {value}".lower()
            if all(term in hay for term in terms):
                matches.append({"key": key, "value": value[:MAX_VALUE_CHARS]})
            if len(matches) >= MAX_MEMORY_RESULTS:
                break

        if not matches:
            return ToolResult(
                success=True,
                tool=self.name,
                result=f"No saved facts matched '{query}'.",
                data={"matches": [], "count": 0},
            )

        lines = [f"- {m['key']}: {m['value']}" for m in matches]
        return ToolResult(
            success=True,
            tool=self.name,
            result="Matching saved facts:\n" + "\n".join(lines),
            data={"matches": matches, "count": len(matches)},
        )
