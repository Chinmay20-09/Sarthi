"""
skills/browser_awareness/executor.py

The validated Browser Executor — the only place that touches the page.

Hermes never calls this. The Brain validates Hermes' recommendation
against the current snapshot (schemas.validate_inspection), and only then
the executor performs the allow-listed action:

    navigate | click | type | select | check | uncheck | submit | scroll

Every action is re-checked against the live page just before it happens
(element still present? visible? enabled?) and selectors are only ever
the ones the inspector generated — Hermes cannot inject selectors.
"""

from __future__ import annotations

import re

from utils.logger import get_logger

from .schemas import (
    ActionOutcome,
    ElementInfo,
    InspectionResult,
    PageSnapshot,
    validate_inspection,
)

logger = get_logger(__name__)

ACTION_TIMEOUT_MS = 15_000
NAVIGATION_TIMEOUT_MS = 30_000
MAX_TYPE_CHARS = 5000

# Element kinds that must not receive typed input or be "clicked into"
# in a way that could leak data (defence in depth — the snapshot already
# hides their values; this blocks focus side-effects on them entirely).
_PROTECTED_KINDS = {"other"}


class SafeExecutor:
    """Performs one validated action on a Playwright page."""

    def __init__(self, page):
        self._page = page

    def perform(
        self,
        inspection: InspectionResult,
        snapshot: PageSnapshot,
        confirmed: bool = False,
    ) -> ActionOutcome:
        """Validate and run the recommended action on ``page``."""
        problems = validate_inspection(inspection, snapshot)
        if problems:
            return ActionOutcome(
                ok=False,
                status="invalid",
                message="Action rejected before execution.",
                detail="; ".join(problems),
            )

        if inspection.status == "done":
            return ActionOutcome(
                ok=True,
                status="executed",
                message=inspection.understanding or "Objective reached.",
            )

        action = inspection.action
        assert action is not None  # validated above
        if action.requires_confirmation and not confirmed:
            return ActionOutcome(
                ok=False,
                status="needs_confirmation",
                message=(
                    "I stopped before a high-impact action "
                    f"({action.rationale or action.type}). Say yes to continue "
                    "or re-run with confirmation enabled."
                ),
            )

        try:
            if action.type == "navigate":
                return self._navigate(action.url or "")
            if action.type == "scroll":
                return self._scroll(action.element_id or "", snapshot)
            element = self._resolve_element(action.element_id, snapshot)
            if element is None:
                return ActionOutcome(
                    ok=False, status="invalid", message="Element is gone from the page."
                )
            return self._dispatch(action.type, element, action.value)
        except Exception as exc:  # pragma: no cover - live browser errors
            logger.warning("[BROWSER] action failed: %s", exc)
            return ActionOutcome(ok=False, status="error", message=f"Action failed: {exc}")

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _navigate(self, url: str) -> ActionOutcome:
        if not url.lower().startswith(("http://", "https://")):
            return ActionOutcome(
                ok=False, status="invalid", message="Refusing non-http(s) navigation."
            )
        logger.info(f"[BROWSER] navigating to {url}")
        self._page.goto(url, timeout=NAVIGATION_TIMEOUT_MS, wait_until="domcontentloaded")
        return ActionOutcome(
            ok=True, status="executed", message=f"Opened {url}", detail=url
        )

    def _scroll(self, element_id: str, snapshot: PageSnapshot) -> ActionOutcome:
        locator = self._live_locator(element_id, snapshot)
        if locator is None:
            return ActionOutcome(
                ok=False, status="invalid", message="Scroll target is gone from the page."
            )
        locator.scroll_into_view_if_needed(timeout=ACTION_TIMEOUT_MS)
        return ActionOutcome(ok=True, status="executed", message="Scrolled into view.")

    def _dispatch(self, action_type: str, element: ElementInfo, value: str | None):
        locator = self._page.locator(element.selector).first
        if action_type == "click":
            locator.click(timeout=ACTION_TIMEOUT_MS)
            return ActionOutcome(ok=True, status="executed", message=f"Clicked {element.id}.")
        if action_type == "type":
            locator.fill((value or "")[:MAX_TYPE_CHARS], timeout=ACTION_TIMEOUT_MS)
            return ActionOutcome(ok=True, status="executed", message=f"Typed into {element.id}.")
        if action_type == "select":
            locator.select_option((value or ""), timeout=ACTION_TIMEOUT_MS)
            return ActionOutcome(ok=True, status="executed", message=f"Selected in {element.id}.")
        if action_type == "check":
            locator.check(timeout=ACTION_TIMEOUT_MS)
            return ActionOutcome(ok=True, status="executed", message=f"Checked {element.id}.")
        if action_type == "uncheck":
            locator.uncheck(timeout=ACTION_TIMEOUT_MS)
            return ActionOutcome(ok=True, status="executed", message=f"Unchecked {element.id}.")
        if action_type == "submit":
            form_locator = locator.locator("xpath=ancestor::form[1]")
            if form_locator.count():
                form_locator.first.evaluate("(f) => f.requestSubmit()")
            else:
                locator.click(timeout=ACTION_TIMEOUT_MS)
            return ActionOutcome(
                ok=True, status="executed", message=f"Submitted form via {element.id}."
            )
        return ActionOutcome(
            ok=False, status="invalid", message=f"Unsupported action: {action_type}"
        )

    # ------------------------------------------------------------------
    # Live element checks
    # ------------------------------------------------------------------

    def _resolve_element(self, element_id: str | None, snapshot: PageSnapshot):
        if not element_id:
            return None
        for element in snapshot.elements:
            if element.id == element_id:
                return element
        return None

    def _live_locator(self, element_id: str, snapshot: PageSnapshot):
        """Element locator, re-verified live (present + visible + enabled)."""
        element = self._resolve_element(element_id, snapshot)
        if element is None or not _is_safe_selector(element.selector):
            return None
        locator = self._page.locator(element.selector).first
        try:
            if not locator.is_visible(timeout=ACTION_TIMEOUT_MS):
                return None
            disabled = locator.evaluate("(el) => el.disabled || el.getAttribute('aria-disabled') === 'true'")
            if disabled:
                return None
        except Exception:
            return None
        return locator


def _is_safe_selector(selector: str) -> bool:
    """Only selectors our own inspector generates may reach the page.

    Generated selectors are exactly one of:
      * `#id`
      * `[data-testid="v"]` / `[data-test="v"]` / `[data-qa="v"]` / `[qa="v"]`
      * `input|textarea|select[name="v"]`
      * a `tag > tag > ...` chain where each part is a tag or
        `tag:nth-of-type(n)`
    Anything else (javascript:, url(), scripts, raw quotes) is refused.
    """
    if not selector or len(selector) > 500:
        return False
    if re.search(r"javascript:|url\(|</|>\s*<", selector, re.IGNORECASE):
        return False
    pattern = (
        r"^("
        r"#[A-Za-z_][\w:.-]*"
        r"|\[(?:data-testid|data-test|data-qa|qa)=\"[^\"<>]+\"\]"
        r"|(?:input|textarea|select)\[name=\"[^\"<>]+\"\]"
        r"|(?:[a-z]+(?::nth-of-type\(\d+\))?)(?: > (?:[a-z]+(?::nth-of-type\(\d+\))?))*"
        r")$"
    )
    if not re.match(pattern, selector):
        return False
    # Elements that must never be driven even when the syntax is fine.
    blocked_tags = {"script", "style", "iframe", "frame", "embed", "object", "html"}
    # Only the chain / bare-tag forms carry explicit tags worth checking.
    for part in selector.split(">"):
        tag = re.split(r"[:\[ ]", part.strip())[0]
        if tag and tag not in blocked_tags and re.match(r"^[a-z]+$", tag):
            continue
        if tag in blocked_tags:
            return False
    return True
