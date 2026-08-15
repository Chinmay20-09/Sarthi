"""
open_website tool — opens a website through Sarthi's existing Browser skill.

The Browser skill resolves known websites (name/alias) via the Knowledge
Layer and launches them with webbrowser.open. For a raw URL that is not a
known website, this tool falls back to the SAME primitive the Browser
skill itself uses (webbrowser.open) — it does not introduce a parallel
execution system.
"""

import logging
import webbrowser
from typing import Any

from brain.intent import Intent
from skills.browser.main import BrowserSkill

from .base import BaseTool, ToolResult

logger = logging.getLogger(__name__)


def _looks_like_url(value: str) -> bool:
    """Best-effort check for a direct web URL (scheme or www.)."""
    lowered = value.lower()
    return lowered.startswith(("http://", "https://", "www."))


class OpenWebsiteTool(BaseTool):
    """Open a website (known to Sarthi or a raw URL) in the default browser."""

    name = "open_website"
    description = "Open a website in the default browser."
    parameters = {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "Website name, alias, or URL to open (e.g. 'https://example.com').",
            }
        },
        "required": ["url"],
    }

    def execute(self, arguments: dict[str, Any]) -> ToolResult:
        """Validate the url and delegate to Sarthi's Browser skill."""
        url = str(arguments.get("url") or "").strip()
        if not url:
            return ToolResult(
                success=False,
                tool=self.name,
                error="No website URL was specified.",
                invalid=True,
            )

        try:
            result = BrowserSkill().execute(Intent(action="open", target=url))
        except Exception as e:  # never leak internals upward
            logger.error("open_website failed unexpectedly for '%s': %s", url, e)
            return ToolResult(
                success=False,
                tool=self.name,
                error="The website could not be opened.",
            )

        if result.get("success"):
            info = result.get("result") or {}
            name = info.get("website", url)
            return ToolResult(
                success=True,
                tool=self.name,
                result=f"{name} opened",
                data={"website": name, "url": info.get("url", "")},
            )

        # Unknown to the knowledge layer — open a direct URL using the same
        # primitive the Browser skill uses.
        if _looks_like_url(url):
            try:
                webbrowser.open(url)
            except Exception as e:  # pragma: no cover - platform dependent
                logger.error("webbrowser.open failed for '%s': %s", url, e)
                return ToolResult(
                    success=False,
                    tool=self.name,
                    error="The website could not be opened.",
                )
            return ToolResult(
                success=True,
                tool=self.name,
                result=f"{url} opened",
                data={"website": url, "url": url},
            )

        return ToolResult(
            success=False,
            tool=self.name,
            error=result.get("error") or f"Website '{url}' could not be opened.",
        )
