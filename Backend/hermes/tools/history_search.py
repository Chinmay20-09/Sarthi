"""
history_search tool — keyword search over Sarthi's existing command_history
(via the Knowledge Memory layer — no new database, no new table).

Hermes uses this to ground questions like "what did I do with the exports
last week" in what the user actually ran.
"""

import logging
from typing import Any

from .base import BaseTool, ToolResult

logger = logging.getLogger(__name__)

MAX_HISTORY_RESULTS = 10


class HistorySearchTool(BaseTool):
    """Search the user's past commands by keyword."""

    name = "history_search"
    description = (
        "Search the user's past commands by keyword (returns matching "
        "commands with their action, target, and success)."
    )
    parameters = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Keyword(s) to look for in past commands.",
            },
            "limit": {
                "type": "string",
                "description": "Maximum number of matches to return (default 10).",
            },
        },
        "required": ["query"],
    }

    def execute(self, arguments: dict[str, Any]) -> ToolResult:
        """Keyword-match command_history through the Knowledge Memory layer."""
        query = str(arguments.get("query") or "").strip()
        if not query:
            return ToolResult(
                success=False,
                tool=self.name,
                error="No search query was specified.",
                invalid=True,
            )

        try:
            limit = max(1, min(int(str(arguments.get("limit") or 10)), 50))
        except (TypeError, ValueError):
            limit = 10

        try:
            from knowledge.memory import get_memory

            history = get_memory().get_history(limit=200)
        except Exception as e:  # never leak internals upward
            logger.error("history_search failed unexpectedly: %s", e)
            return ToolResult(
                success=False,
                tool=self.name,
                error="Command history is unavailable right now.",
            )

        lowered = query.lower()
        terms = [t for t in lowered.split() if t]
        matches = []
        for row in history:
            command = str(row.get("command", ""))
            hay = f"{command} {row.get('action', '')} {row.get('target', '')}".lower()
            # Every term must appear somewhere in the row (AND matching).
            if all(term in hay for term in terms):
                matches.append(
                    {
                        "command": command[:120],
                        "action": row.get("action", ""),
                        "target": row.get("target", ""),
                        "success": bool(row.get("success")),
                        "timestamp": row.get("timestamp", ""),
                    }
                )
            if len(matches) >= max(limit, MAX_HISTORY_RESULTS):
                break

        matches = matches[:limit]
        if not matches:
            return ToolResult(
                success=True,
                tool=self.name,
                result=f"No past commands matched '{query}'.",
                data={"matches": [], "count": 0},
            )

        lines = [f"- {m['command']} ({'ok' if m['success'] else 'failed'})" for m in matches]
        return ToolResult(
            success=True,
            tool=self.name,
            result="Matching past commands:\n" + "\n".join(lines),
            data={"matches": matches, "count": len(matches)},
        )
