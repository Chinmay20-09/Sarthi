"""
skills/browser_awareness/main.py

Browser Awareness — Sarthi capability skill.

The Brain's deterministic skills handle known apps/websites ("open
youtube", "search python"). When a command targets an arbitrary website
with a task Hermes has no deterministic recipe for — "open example.com
and find the pricing page" — this skill:

    1. opens the site in a temporary, isolated Chrome session,
    2. inspects the page into a compact snapshot,
    3. lets Hermes *observe* (never control) and recommend one action,
    4. validates the recommendation, executes it, reinspects,
    5. reports the result and destroys the temporary context.

Test mode plans the run without touching the machine.
"""

from __future__ import annotations

import re
from typing import Any

from brain.intent import Intent
from brain.modes import get_test_mode
from skills.base import BaseSkill
from utils.logger import get_logger

from .manager import BrowserAwarenessManager

logger = get_logger(__name__)

# A bare domain or full URL ("example.com", "www.example.com/pricing").
_URL_RE = re.compile(r"(?i)(?:https?://)?(?:www\.)?[a-z0-9-]+(?:\.[a-z0-9-]+)+(?:[/:][^\s]*)?")

# Leading connectors/fillers that may precede the objective clause.
_OBJECTIVE_LEAD_RE = re.compile(r"^(?:and\s+|then\s+|to\s+|please\s+)*", re.IGNORECASE)


class BrowserAwarenessSkill(BaseSkill):
    """Opens + inspects arbitrary websites and executes validated actions."""

    name = "browser_awareness"
    description = (
        "Inspects websites the Brain cannot drive deterministically and "
        "performs validated actions on them (find/click/type/submit)."
    )
    version = "1.0.0"

    # ------------------------------------------------------------------
    # BaseSkill interface
    # ------------------------------------------------------------------

    def execute(self, intent: Intent) -> dict[str, Any]:
        """Run one browser-awareness task for a ``browse`` intent."""
        action = (intent.action or "").lower()
        if action not in ("browse", "open_browser_awareness"):
            return {
                "success": False,
                "status": "unknown_action",
                "error": f"Browser awareness does not support action: {action}",
            }

        text = (intent.raw_text or intent.target or "").strip()
        url, objective = parse_browse_request(text)
        if not url:
            return {
                "success": False,
                "status": "error",
                "error": (
                    "I need a website to inspect. Try: /browse example.com and "
                    "find the pricing page"
                ),
            }

        if get_test_mode():
            return self._plan(url, objective)

        logger.info(f"[BROWSER AWARENESS] task: {objective or 'describe page'} on {url}")
        result = BrowserAwarenessManager().run(url=url, objective=objective)
        return {
            "success": result.success,
            "handled": True,
            "status": result.status,
            "result": {
                "message": result.message,
                "url": result.url,
                "objective": result.objective,
                "steps": result.steps,
                "understanding": result.final_understanding,
            },
            "error": None if result.success else result.message,
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _plan(self, url: str, objective: str) -> dict[str, Any]:
        plan = [
            f"1. Open {url} in a temporary, isolated Chrome session",
            "2. Inspect the page into a compact snapshot",
            "3. Hermes observes the page and recommends one validated action",
            "4. Execute + reinspect until the objective is reached",
            f"5. Objective: {objective or 'describe the page'}",
        ]
        message = "Planned browser-awareness task: " + " | ".join(plan)
        logger.info(message)
        return {
            "success": True,
            "handled": True,
            "status": "planned",
            "result": {"message": message, "url": url, "objective": objective, "steps": plan},
        }


def parse_browse_request(text: str) -> tuple[str, str]:
    """Split a browse request into (url, objective).

    Understands:
        /browse example.com and find the pricing page
        browse example.com find the pricing page
        open example.com and find the More Information link

    When no objective is given, the page is simply described.
    """
    cleaned = (text or "").strip()
    # Drop a leading slash command token ("/browse ...").
    if cleaned.startswith("/"):
        cleaned = re.sub(r"^/\S+\s*", "", cleaned).strip()

    match = _URL_RE.search(cleaned)
    if match is None:
        return "", ""

    url = _normalise_url(match.group(0).strip())
    suffix = cleaned[match.end() :].strip()
    objective = _OBJECTIVE_LEAD_RE.sub("", suffix).strip(" ,.!?;:").strip()
    return url, objective


def _normalise_url(raw: str) -> str:
    """Guarantee an http(s) scheme (https by default)."""
    candidate = raw.strip().rstrip(".,!?;:")
    if "://" in candidate:
        return candidate
    return f"https://{candidate}"
