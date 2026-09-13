"""
browser_ask tool — DOM-aware browser interaction via Sarthi's existing
Browser Awareness skill.

Hermes requests a high-level objective ("find the pricing page on
example.com"); the skill opens the site in a temporary isolated Chrome
session, inspects the DOM (never pixel guessing), and performs validated
actions until the objective is met. Hermes never supplies coordinates.
"""

import logging
from typing import Any

from .base import BaseTool, ToolResult

logger = logging.getLogger(__name__)


class BrowserAskTool(BaseTool):
    """Ask a question of / perform an objective on a website (DOM-aware)."""

    name = "browser_ask"
    description = (
        "Open a website and perform a high-level objective on it using "
        "DOM-aware browsing (e.g. find the pricing page, read the first "
        "heading). Never uses screen coordinates."
    )
    parameters = {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "The website to interact with (e.g. 'example.com').",
            },
            "objective": {
                "type": "string",
                "description": "What to accomplish or find on the page.",
            },
        },
        "required": ["url"],
    }

    def execute(self, arguments: dict[str, Any]) -> ToolResult:
        """Validate inputs and delegate to the Browser Awareness skill."""
        url = str(arguments.get("url") or "").strip()
        objective = str(arguments.get("objective") or "").strip()

        if not url:
            return ToolResult(
                success=False,
                tool=self.name,
                error="No website was specified.",
                invalid=True,
            )

        # The skill's parse_browse_request expects the raw "browse ..." text
        # shape; reconstruct it so the URL/objective split stays in one place.
        text = f"/browse {url} {objective}".strip()

        try:
            from skills.browser_awareness.main import BrowserAwarenessSkill

            result = BrowserAwarenessSkill().execute(
                type("Intent", (), {"action": "browse", "raw_text": text, "target": url})()
            )
        except Exception as e:  # never leak internals upward
            logger.error("browser_ask failed unexpectedly for '%s': %s", url, e)
            return ToolResult(
                success=False,
                tool=self.name,
                error="The website task could not be completed.",
            )

        if result.get("success"):
            info = result.get("result") or {}
            return ToolResult(
                success=True,
                tool=self.name,
                result=info.get("message") or f"Completed the task on {url}.",
                data={"url": info.get("url", url), "objective": info.get("objective", objective)},
            )

        return ToolResult(
            success=False,
            tool=self.name,
            error=result.get("error") or "The website task could not be completed.",
        )
