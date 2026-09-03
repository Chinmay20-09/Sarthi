"""
skills/browser_awareness/manager.py

Orchestration: the loop between page, inspector, Hermes and executor.

    inspect page -> Hermes observes -> Brain validates -> executor acts
    -> reinspect (page changed) -> ... -> done / blocked / step limit

Hermes never controls the browser: every step of the loop is driven here
and every Hermes recommendation passes through the pure schema
validation before the executor is allowed to touch the page.

The manager works against injected components (inspector/hermes/executor
interfaces) so the whole loop is unit-testable without a browser; the
real Playwright stack is wired up only for live runs.
"""

from __future__ import annotations

import re
from urllib.parse import urlparse

from utils.logger import get_logger
from utils.voice import announce

from .driver import BrowserSession, open_session
from .executor import SafeExecutor
from .hermes_inspector import HermesInspector
from .inspector import PlaywrightInspector
from .schemas import BrowserTaskResult, InspectionResult

logger = get_logger(__name__)

MAX_STEPS = 8

# Spoken progress (docs/ABSOLUTE.md voice contract — short phrases, spoken
# not read). Browser awareness drives its OWN browser session, so the
# "hands off the keyboard" warning does not apply — but the user still
# hears what the automation is doing, start to finish, like the AI chain.
# Dry runs (test mode) never reach the manager, so they never announce.
VOICE_START = "Browser awareness started. Opening {url}."
VOICE_DONE = "Done. {summary}"
VOICE_BLOCKED = "I could not complete the task. {summary}"
VOICE_CONFIRM = "I stopped before a high impact action. Waiting for your confirmation."
VOICE_FAILED = "Browser awareness failed."


class BrowserAwarenessManager:
    """Runs one browser-awareness task (one temporary browsing context)."""

    def __init__(
        self,
        session_factory=open_session,
        inspector_factory=PlaywrightInspector,
        hermes: HermesInspector | None = None,
        executor_factory=SafeExecutor,
        announce_progress: bool = True,
    ):
        self._session_factory = session_factory
        self._inspector_factory = inspector_factory
        self._hermes = hermes
        self._executor_factory = executor_factory
        self._announce = announce_progress
        self._steps: list[str] = []

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def run(
        self,
        url: str,
        objective: str = "",
        confirm: bool = False,
        max_steps: int = MAX_STEPS,
    ) -> BrowserTaskResult:
        """Complete one objective on ``url``; the context is always closed.

        Announces progress out loud (like the AI chain) unless
        ``announce_progress=False`` was passed to the constructor.
        """
        self._speak(VOICE_START.format(url=_short(url)))
        try:
            result = self._run(url, objective, confirm, max_steps)
            self._speak_terminal(result)
            return result
        finally:
            self._steps = []

    def _speak_terminal(self, result: BrowserTaskResult) -> None:
        """Spoken outcome for the terminal state (completed / blocked / ...)."""
        summary = result.final_understanding or result.message
        if result.status == "completed":
            self._speak(VOICE_DONE.format(summary=_first_sentence(summary)))
        elif result.status == "blocked":
            self._speak(VOICE_BLOCKED.format(summary=_first_sentence(summary)))
        elif result.status == "needs_confirmation":
            self._speak(VOICE_CONFIRM)
        elif result.status == "failed":
            self._speak(VOICE_FAILED)

    def _run(
        self,
        url: str,
        objective: str,
        confirm: bool,
        max_steps: int,
    ) -> BrowserTaskResult:
        """The inspect -> observe -> validate -> execute -> reinspect loop."""
        session: BrowserSession | None = None
        try:
            logger.info(f"[BROWSER] opening {url}")
            self._log(f"Opening {url}…")
            session = self._session_factory(url)
            page = session.page
            hermes = self._hermes or HermesInspector()
            inspector = self._inspector_factory(page)
            executor = self._executor_factory(page)

            snapshot = inspector.inspect()
            logger.info("[BROWSER] page loaded")
            self._log("Inspecting the page…")

            for step_number in range(1, max_steps + 1):
                logger.info(f"[HERMES] observation requested (step {step_number})")
                observation: InspectionResult = hermes.observe(objective, snapshot)

                if observation.status == "blocked":
                    logger.info("[BRAIN] objective blocked")
                    return BrowserTaskResult(
                        success=False,
                        status="blocked",
                        url=snapshot.url,
                        objective=objective,
                        message=observation.message
                        or "The objective cannot be reached from this page.",
                        steps=list(self._steps),
                        final_understanding=observation.understanding,
                    )
                if observation.status == "done":
                    logger.info("[BRAIN] task completed")
                    self._log(observation.understanding or "Done.")
                    summary = observation.understanding or "Done."
                    return BrowserTaskResult(
                        success=True,
                        status="completed",
                        url=snapshot.url,
                        objective=objective,
                        message=summary,
                        steps=list(self._steps),
                        final_understanding=observation.understanding,
                    )

                # A recommendation -> validate (pure gate) -> maybe execute.
                action = observation.action
                if action is None:
                    logger.warning("[BRAIN] continue without an action — stopping")
                    return BrowserTaskResult(
                        success=False,
                        status="blocked",
                        url=snapshot.url,
                        objective=objective,
                        message="The awareness model gave no next action.",
                        steps=list(self._steps),
                    )

                if action.type == "navigate":
                    self._log(f"Going to {action.url}…")
                else:
                    self._log(f"{action.type} {action.element_id or ''}".strip())
                logger.info(f"[BRAIN] action validated: {action.type}")
                self._speak(_spoken_action(action, snapshot))
                outcome = executor.perform(observation, snapshot, confirmed=confirm)

                if outcome.status == "needs_confirmation":
                    return BrowserTaskResult(
                        success=False,
                        status="needs_confirmation",
                        url=snapshot.url,
                        objective=objective,
                        message=outcome.message,
                        steps=list(self._steps),
                        final_understanding=observation.understanding,
                    )
                if not outcome.ok:
                    logger.info(f"[BRAIN] action rejected: {outcome.message}")
                    return BrowserTaskResult(
                        success=False,
                        status="blocked",
                        url=snapshot.url,
                        objective=objective,
                        message=outcome.message,
                        steps=list(self._steps),
                        final_understanding=observation.understanding,
                    )

                self._log(outcome.message or "Done.")
                # Page may have changed (navigation, click) — always
                # reinspect for the next decision.
                snapshot = inspector.inspect()

            return BrowserTaskResult(
                success=False,
                status="blocked",
                url=snapshot.url,
                objective=objective,
                message=(
                    f"Stopped after {max_steps} steps — the objective is not "
                    "complete yet. Re-run or give a more specific instruction."
                ),
                steps=list(self._steps),
            )
        except Exception as exc:
            logger.exception("Browser awareness run failed")
            return BrowserTaskResult(
                success=False,
                status="failed",
                url=url,
                objective=objective,
                message=f"Browser awareness failed: {exc}",
                steps=list(self._steps),
            )
        finally:
            if session is not None:
                logger.info("[BROWSER] destroying temporary context")
                self._log("Closing the temporary browser context.")
                session.close()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _log(self, message: str) -> None:
        self._steps.append(message)
        logger.info(f"[BROWSER] {message}")

    def _speak(self, message: str) -> None:
        """Best-effort spoken progress; never raises (utils.voice)."""
        if not self._announce or not message:
            return
        logger.info(f"[VOICE] {message}")
        announce(message)


def _spoken_action(action, snapshot) -> str:
    """Short, human line for what is about to happen (spoken aloud).

    Element text/labels are taken from the snapshot so the voice names
    what the user can see ("Clicking Pricing") — never ids or raw
    values.
    """
    if action.type == "navigate":
        return f"Opening {_short(action.url or '')}."
    label = _element_label(action.element_id, snapshot)
    verbs = {
        "click": f"Clicking {label or 'the element'}.",
        "type": f"Typing into {label or 'the field'}.",
        "select": f"Choosing an option in {label or 'the dropdown'}.",
        "check": f"Checking {label or 'the box'}.",
        "uncheck": f"Unchecking {label or 'the box'}.",
        "submit": "Submitting the form.",
        "scroll": f"Scrolling to {label or 'the section'}.",
    }
    return verbs.get(action.type, f"{action.type} {label or ''}.".strip())


def _element_label(element_id: str | None, snapshot) -> str:
    """The most user-facing text of an element (never its stored value)."""
    if not element_id:
        return ""
    for element in snapshot.elements:
        if element.id == element_id:
            for candidate in (element.text, element.label, element.placeholder, element.name):
                if candidate and len(candidate) <= 60:
                    return candidate
            return (element.text or element.label or element.placeholder or element.name)[:60]
    return ""


def _short(url: str) -> str:
    """Human-short version of a URL (host + short path) for speech."""
    text = (url or "").strip()
    parsed = urlparse(text if "://" in text else f"https://{text}")
    host = (parsed.netloc or text).replace("www.", "")
    return host[:60] or text[:60]


def _first_sentence(text: str) -> str:
    """First sentence of a message, capped for speech."""
    cleaned = re.sub(r"\s+", " ", (text or "").strip())
    for end in (". ", "! ", "? ", "\n"):
        cut = cleaned.find(end)
        if 0 < cut <= 160:
            cleaned = cleaned[: cut + 1]
            break
    return cleaned[:160].rstrip()
