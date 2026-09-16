"""
search_web tool — runs a web search through Sarthi's existing Browser skill
(the same deterministic path "search X" takes), then returns the result URL.

Hermes requests "search the web for X"; Sarthi decides HOW (knowledge-backed
site search, Google fallback, real browser). No raw HTTP, no scraping here.
"""

import logging
from typing import Any

from brain.intent import Intent

from .base import BaseTool, ToolResult

logger = logging.getLogger(__name__)


class SearchWebTool(BaseTool):
    """Search the web through Sarthi's browser pipeline."""

    name = "search_web"
    description = (
        "Search the web for a query (opens the results in the browser and returns the search URL)."
    )
    parameters = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The search query (e.g. 'python asyncio tutorial').",
            }
        },
        "required": ["query"],
    }

    def execute(self, arguments: dict[str, Any]) -> ToolResult:
        """Validate the query and delegate to the Browser skill's search path."""
        query = str(arguments.get("query") or "").strip()
        if not query:
            return ToolResult(
                success=False,
                tool=self.name,
                error="No search query was specified.",
                invalid=True,
            )

        try:
            from skills.browser.main import BrowserSkill

            result = BrowserSkill().execute(Intent(action="search", target=query))
        except Exception as e:  # never leak internals upward
            logger.error("search_web failed unexpectedly for '%s': %s", query, e)
            return ToolResult(
                success=False,
                tool=self.name,
                error="The web search could not be completed.",
            )

        if result.get("success"):
            info = result.get("result") or {}
            url = info.get("url", "")
            return ToolResult(
                success=True,
                tool=self.name,
                result=f"Searching the web for '{query}'.",
                data={"query": query, "url": url},
            )

        return ToolResult(
            success=False,
            tool=self.name,
            error=result.get("error") or "The web search could not be completed.",
        )
