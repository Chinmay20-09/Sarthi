"""
ai_chain/sites.py

Drives a single AI website end-to-end by controlling the laptop:

    1. Open the site in the default browser and focus its window.
    2. Click the message composer, paste the prompt, press Enter.
    3. While the AI streams its reply, periodically Select-All + Copy
       the page and watch the copied transcript until it stops changing
       (that means generation finished).
    4. Return the reply extracted from the final transcript.

Image-capable sites (Gemini) get an extra step: click the download
affordance of the newest generated image and harvest the file the
browser drops into the Downloads folder.

Reading replies without OCR/vision is done the way an RPA bot would:
Ctrl+A / Ctrl+C on the focused page, then the reply is the text after
the last occurrence of the prompt we sent (see parsing.extract_reply).
"""

from __future__ import annotations

import time
from pathlib import Path

from utils.logger import get_logger

from .awareness import AwarenessExtractor, needs_awareness
from .control import ScreenController
from .models import SiteSpec
from .parsing import extract_reply, paste_verify_prefix, prompt_present
from .screen import ScreenState, classify, state_message

logger = get_logger(__name__)

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}

# Do not declare "done" before at least this much time has passed —
# a reply that has not started streaming yet would otherwise look stable.
MIN_FINISH_SECONDS = 12.0


class WebAiDriver:
    """Operates one AI website through a ScreenController."""

    def __init__(
        self,
        controller: ScreenController,
        awareness: AwarenessExtractor | None = None,
    ):
        self.ctrl = controller
        # Optional browser-awareness extractor (injected in tests). When
        # None, the local Hermes model is used lazily when needed.
        self._awareness = awareness

    # ------------------------------------------------------------------
    # Public flow
    # ------------------------------------------------------------------

    def ask(self, spec: SiteSpec, prompt: str) -> str:
        """
        Send ``prompt`` to the AI on ``spec`` and return its reply text.

        Raises:
            AbortError — user interrupted the run
            RuntimeError — site could not be reached / no reply came back
        """
        logger.info(f"[{spec.label}] opening {spec.url}")
        self.ctrl.open_site(spec.url, spec.title_keyword, spec.page_load_wait)
        time.sleep(spec.page_load_wait)

        self._focus_composer(spec)
        self.ctrl.paste(prompt)
        # Browser awareness (write side): confirm the paste actually landed
        # in the composer before pressing Enter. The old flow pressed Enter
        # blindly — when the click missed the message box the prompt went
        # nowhere and the run burned its whole wait budget on a new-chat
        # landing page.
        self._confirm_composer(spec, prompt)
        logger.info(f"[{spec.label}] prompt sent ({len(prompt)} chars)")
        self.ctrl.press("enter")

        transcript = self._wait_for_reply(spec, prompt)

        # A copy that is smaller than a page is a message element captured
        # whole (a click that landed inside the chat instead of empty page
        # space). Re-read once or twice before deciding anything.
        for _ in range(2):
            if classify(transcript, prompt, spec) is not ScreenState.FRAGMENT:
                break
            logger.info(f"[{spec.label}] copy looks like an element fragment — re-reading")
            transcript = self._read_transcript(spec)

        state = classify(transcript, prompt, spec)
        if state in (ScreenState.LOGIN_WALL, ScreenState.LANDING_PAGE):
            raise RuntimeError(state_message(state, spec))
        if state is ScreenState.LOADING and not spec.image_capable:
            raise RuntimeError(state_message(state, spec))
        if state is ScreenState.EMPTY:
            raise RuntimeError(state_message(state, spec))

        reply = extract_reply(transcript, prompt, spec.footer_markers)

        # Browser awareness: the copy-paste heuristic trusts its result only
        # when it found the prompt in the transcript AND text after it.
        # Deterministic screen states (login wall, landing, loading, empty)
        # never reach the model — only ambiguous transcripts that look like
        # a conversation (fragments, unknown layouts, empty replies) do.
        if needs_awareness(reply, transcript, prompt):
            aware = self._awareness_extract(transcript, prompt)
            if aware:
                logger.info(f"[{spec.label}] reply recovered via browser awareness")
                reply = aware
            else:
                raise RuntimeError(
                    f"[{spec.label}] no reply found on the page — browser awareness "
                    "saw only page chrome. Is the site logged in and on a new chat?"
                )

        logger.info(f"[{spec.label}] reply captured ({len(reply)} chars)")
        return reply

    def download_last_image(self, spec: SiteSpec, downloads_dir: Path) -> Path | None:
        """
        Click the newest image's download affordance and harvest the file.

        The exact click point comes from calibration when available; the
        fallback estimates it just above the composer (the newest image
        always sits there because the page auto-scrolls to the bottom).
        Returns the harvested file path, or None.
        """
        rect = self.ctrl.window_rect(spec.title_keyword)
        fx, fy = spec.image_download_point or (spec.composer[0], spec.composer[1] - 0.12)
        x, y = self.ctrl.fraction_point(rect, fx, fy)

        attempt_started = time.time()
        for attempt in range(1, 5):
            self.ctrl.check_abort()
            logger.info(f"[{spec.label}] image download attempt {attempt}/4 at ({x}, {y})")
            self.ctrl.click(x, y)
            found = _newest_download(downloads_dir, since=attempt_started - 2.0)
            if found is not None:
                logger.info(f"[{spec.label}] harvested download: {found.name}")
                return found
            time.sleep(3.0)
        return None

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _awareness_extract(self, transcript: str, prompt: str) -> str:
        """Ask the (local Hermes) awareness model to read the transcript."""
        extractor = self._awareness or AwarenessExtractor()
        return extractor.extract(transcript, prompt)

    def _confirm_composer(self, spec: SiteSpec, prompt: str, attempts: int = 3) -> None:
        """
        Make sure ``prompt`` is really sitting in the composer.

        After a paste, Ctrl+A / Ctrl+C inside the composer and compare the
        round-trip text with the start of the prompt. When the paste missed
        (the click before it did not land on the message box), re-focus the
        composer, clear it and paste again — up to ``attempts`` times — then
        fail with an actionable error instead of sending nothing.

        Raises:
            RuntimeError — the prompt could not be placed in the composer.
        """
        for attempt in range(1, attempts + 1):
            if self._composer_holds(spec, prompt):
                return
            logger.warning(
                f"[{spec.label}] paste did not land in the composer "
                f"(attempt {attempt}/{attempts}) — re-focusing and retrying"
            )
            if attempt < attempts:
                self._focus_composer(spec)
                self._clear_composer()
                self.ctrl.paste(prompt)

        raise RuntimeError(
            f"[{spec.label}] could not get the prompt into the message box — "
            "the paste is not landing where expected. Recalibrate the "
            "composer point and rerun: "
            f"python -m skills.automation_engine.ai_chain.calibrate "
            f"--site {spec.key} --point composer --record"
        )

    def _composer_holds(self, spec: SiteSpec, prompt: str) -> bool:
        """True when the composer's current text starts with the prompt."""
        if self.ctrl.dry_run:
            return True
        text = self.ctrl.select_all_and_copy()
        return prompt_present(text, paste_verify_prefix(prompt))

    def _clear_composer(self) -> None:
        """Select all in the composer and delete it before a retry paste."""
        self.ctrl.hotkey("ctrl", "a")
        self.ctrl.press("backspace")
        time.sleep(0.2)

    def _focus_composer(self, spec: SiteSpec) -> None:
        """Click the composer so paste lands in the right field."""
        rect = self.ctrl.window_rect(spec.title_keyword)
        x, y = self.ctrl.fraction_point(rect, *spec.composer)
        self.ctrl.click(x, y)
        time.sleep(0.6)

    def _read_transcript(self, spec: SiteSpec) -> str:
        """Focus the conversation area (not the composer) and copy the page."""
        rect = self.ctrl.window_rect(spec.title_keyword)
        x, y = self.ctrl.fraction_point(rect, *spec.read_point)
        self.ctrl.click(x, y)
        time.sleep(0.4)
        return self.ctrl.select_all_and_copy()

    def _wait_for_reply(self, spec: SiteSpec, prompt: str) -> str:
        """
        Poll the copied transcript until the AI stops streaming.

        Stability heuristic: the transcript text must stay identical for
        ``stable_polls`` consecutive reads, and generation must have had
        at least MIN_FINISH_SECONDS to start. Falls back to the last
        transcript on timeout (never raises for a slow reply).

        Screen-state awareness: when the browser is showing a login wall
        or a fresh new-chat landing (the prompt never made it onto the
        page), the copy is dead stable from the first read — detect that
        after two consecutive reads and fail fast with a precise message
        instead of polling until ``max_wait``.
        """
        started = time.time()
        last_text = ""
        stable_count = 0
        chrome_streak = 0

        while time.time() - started < spec.max_wait:
            self.ctrl.check_abort()
            time.sleep(spec.poll_interval)

            transcript = self._read_transcript(spec)
            reply = extract_reply(transcript, prompt, spec.footer_markers)
            elapsed = time.time() - started

            # Fail fast on deterministic non-conversation screens.
            state = classify(transcript, prompt, spec)
            if state in (ScreenState.LOGIN_WALL, ScreenState.LANDING_PAGE):
                chrome_streak += 1
            else:
                chrome_streak = 0
            if chrome_streak >= 2:
                raise RuntimeError(state_message(state, spec))

            if transcript == last_text and elapsed > MIN_FINISH_SECONDS:
                stable_count += 1
            else:
                stable_count = 0
            last_text = transcript

            # Pure-image replies may leave no text at all — give the
            # image site its full budget unless text is stable.
            image_mode = spec.image_capable and not reply.strip()
            if stable_count >= spec.stable_polls and (reply.strip() or not image_mode):
                logger.info(f"[{spec.label}] reply stable after {elapsed:.0f}s")
                break

            progress = f"{elapsed:.0f}/{spec.max_wait:.0f}s, {len(reply)} reply chars"
            logger.info(f"[{spec.label}] waiting for reply ({progress})")

        if not last_text:
            raise RuntimeError(
                f"[{spec.label}] no reply detected within {spec.max_wait:.0f}s. "
                "Is the site open, logged in, and on a new chat?"
            )
        return last_text


# ----------------------------------------------------------------------
# Downloads-folder helpers
# ----------------------------------------------------------------------


def _newest_download(downloads_dir: Path, since: float) -> Path | None:
    """Newest image downloaded after ``since``, or None."""
    if not downloads_dir.exists():
        return None
    candidates = []
    for path in downloads_dir.iterdir():
        if not path.is_file() or path.suffix.lower() not in IMAGE_EXTENSIONS:
            continue
        try:
            if path.stat().st_mtime >= since:
                candidates.append(path)
        except OSError:
            continue
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)
