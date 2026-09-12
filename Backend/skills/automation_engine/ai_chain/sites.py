"""
ai_chain/sites.py

Drives a single AI website end-to-end by controlling the laptop:

    1. Open the site in the default browser and focus its window.
    2. Click the message composer, paste the prompt, press Enter.
    3. While the AI streams its reply, periodically read the page and
       watch the transcript until it stops changing (that means
       generation finished).
    4. Return the reply from the final transcript.

Image-capable sites (Gemini) get an extra step: click the download
affordance of the newest generated image and harvest the file the
browser drops into the Downloads folder.

Reading replies without OCR/vision — v1.5 first, then v1.0:

- **v1.5 (DOM):** when the driver can attach read-only to the running
  Chrome (DevTools protocol, see dom.py) it pulls the page's HTML and
  regexes it for the affordance — ``aria-label="Copy"``,
  ``id="prompt-textarea"``, ``aria-label="Enter a prompt here"``, the
  image Download button — then clicks the exact spot. Matchers ship per
  site in registry.py and are overridable without code.
- **v1.0 (fallback):** where the site registers a Copy button (browser
  awareness registry — see registry.py) the driver clicks it at an
  estimated/calibrated point plus a scan grid, and the clipboard holds
  the assistant's message verbatim. Otherwise it works the way an RPA
  bot would: Ctrl+A / Ctrl+C on the focused page, then the reply is the
  text after the last occurrence of the prompt we sent (see
  parsing.extract_reply).

A read reports whether it came from the Copy button, so the prompt-based
heuristic is only used for whole-page copies.
"""

from __future__ import annotations

import time
from pathlib import Path

from utils.logger import get_logger

from . import handoff
from .awareness import AwarenessExtractor, needs_awareness
from .control import ScreenController
from .dom import get_dom_reader, keyword_for
from .models import SiteSpec
from .parsing import extract_reply, paste_verify_prefix, prompt_present
from .registry import (
    coordinate_scan_enabled,
    copy_scan_candidates,
    dom_action_enabled,
    get_dom_matchers,
    uses_button_copy,
)
from .screen import ScreenState, classify, state_message

logger = get_logger(__name__)

# Warn once per process when v1.5 is unavailable — the user saw the mouse
# "go random" with no explanation because this fallback used to be silent.
_dom_unavailable_logged = False


def _warn_dom_unavailable(spec: SiteSpec) -> None:
    global _dom_unavailable_logged
    if _dom_unavailable_logged:
        return
    _dom_unavailable_logged = True
    logger.warning(
        f"[{spec.label}] v1.5 DOM locating unavailable (no Chrome DevTools "
        "endpoint) — falling back to estimated points. Let Sarthi launch its "
        "automation Chrome (default) or start Chrome with "
        "--remote-debugging-port, or set AI_CHAIN_CDP_URL."
    )


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
        dom_reader=None,
    ):
        self.ctrl = controller
        # Optional browser-awareness extractor (injected in tests). When
        # None, the local Hermes model is used lazily when needed.
        self._awareness = awareness
        # Optional v1.5 DOM reader (injected in tests). When None, the
        # shared tried-once Chrome attachment is used lazily (see dom.py).
        self._dom_reader = dom_reader

    # ------------------------------------------------------------------
    # Public flow
    # ------------------------------------------------------------------

    def ask(self, spec: SiteSpec, prompt: str, prompt_key: str | None = None) -> str:
        """
        Send ``prompt`` to the AI on ``spec`` and return its reply text.

        ``prompt_key`` names the backend hand-off entry holding this
        prompt (chain.py saves one per step). When given, every paste
        retry re-copies FROM the backend instead of trusting the
        clipboard, which verification copies keep clobbering.

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
        self._confirm_composer(spec, prompt, prompt_key=prompt_key)
        logger.info(f"[{spec.label}] prompt sent ({len(prompt)} chars)")
        self.ctrl.press("enter")

        transcript, via_button = self._wait_for_reply(spec, prompt)

        reply = ""
        if via_button:
            # The site's Copy button gave us the assistant's message
            # verbatim. No prompt-based extraction or screen classification
            # applies: a Copy button only exists on a real message, so the
            # text is already the reply — and it never carries the sent
            # prompt, which would only confuse the heuristic.
            reply = transcript.strip()
        else:
            # A copy that is smaller than a page is a message element
            # captured whole (a click that landed inside the chat instead
            # of empty page space). Re-read once or twice before deciding
            # anything; a re-read may now hit the Copy button.
            for _ in range(2):
                if classify(transcript, prompt, spec) is not ScreenState.FRAGMENT:
                    break
                logger.info(f"[{spec.label}] copy looks like an element fragment — re-reading")
                transcript, via_button = self._read_transcript(spec)
                if via_button:
                    reply = transcript.strip()
                    break

            if not reply:
                state = classify(transcript, prompt, spec)
                if state in (ScreenState.LOGIN_WALL, ScreenState.LANDING_PAGE):
                    raise RuntimeError(state_message(state, spec))
                if state is ScreenState.LOADING and not spec.image_capable:
                    raise RuntimeError(state_message(state, spec))
                if state is ScreenState.EMPTY:
                    raise RuntimeError(state_message(state, spec))

                reply = extract_reply(transcript, prompt, spec.footer_markers)

                # Browser awareness: the copy-paste heuristic trusts its
                # result only when it found the prompt in the transcript AND
                # text after it. Deterministic screen states (login wall,
                # landing, loading, empty) never reach the model — only
                # ambiguous transcripts that look like a conversation
                # (fragments, unknown layouts, empty replies) do.
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
        # v1.5: regex the HTML for the image's Download affordance; falls
        # back to the estimated/calibrated point when DOM locating is off
        # or finds nothing.
        point = self._dom_point(spec, "download")
        if point is not None:
            fx, fy = point
        else:
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

    def _dom_point(self, spec: SiteSpec, action: str) -> tuple[float, float] | None:
        """
        v1.5: locate an affordance by regexing the page HTML.

        Returns the window-fraction centre of the element, or None when
        DOM locating is disabled, unregistered for this action, the
        Chrome attachment failed, or the regex found nothing — the caller
        then falls back to the v1.0 estimated point/scan behaviour.
        """
        if not dom_action_enabled(spec.key, action):
            return None
        matchers = get_dom_matchers(spec.key, action)
        if not matchers:
            return None
        reader = self._dom_reader if self._dom_reader is not None else get_dom_reader()
        if reader is None:
            _warn_dom_unavailable(spec)
            return None
        try:
            point = reader.locate(keyword_for(spec.url), matchers)
        except Exception as exc:
            logger.debug(f"[{spec.label}] DOM locate failed: {exc}")
            return None
        if point is not None:
            logger.info(f"[{spec.label}] DOM located {action} at ({point[0]:.2f}, {point[1]:.2f})")
        return point

    def _confirm_composer(
        self, spec: SiteSpec, prompt: str, prompt_key: str | None = None, attempts: int = 3
    ) -> None:
        """
        Make sure ``prompt`` is really sitting in the composer.

        After a paste, Ctrl+A / Ctrl+C inside the composer and compare the
        round-trip text with the start of the prompt. Each failed retry
        clicks the NEXT composer candidate (DOM hit, calibrated estimate,
        then nudged variants) — retrying the identical wrong point could
        never succeed, which is exactly what burned the Gemini step in
        live runs. The paste itself is re-copied from the backend
        hand-off (``prompt_key``) so a clobbered clipboard cannot poison
        the retry.

        Raises:
            RuntimeError — the prompt could not be placed in the composer.
        """
        candidates: list[tuple[float, float]] | None = None  # built lazily on first retry
        for attempt in range(1, attempts + 1):
            if self._composer_holds(spec, prompt):
                return
            logger.warning(
                f"[{spec.label}] paste did not land in the composer "
                f"(attempt {attempt}/{attempts}) — re-focusing and retrying"
            )
            if attempt < attempts:
                if candidates is None:
                    candidates = self._composer_candidates(spec)
                point = candidates[min(attempt, len(candidates) - 1)]
                logger.info(
                    f"[{spec.label}] trying composer candidate at ({point[0]:.2f}, {point[1]:.2f})"
                )
                self._focus_composer(spec, point)
                self._clear_composer()
                backend = handoff.load(prompt_key) if prompt_key else ""
                self.ctrl.paste(backend or prompt)

        saved = (
            f" The prompt is safe in the backend hand-off ({handoff.describe()})."
            if prompt_key
            else ""
        )
        raise RuntimeError(
            f"[{spec.label}] could not get the prompt into the message box — "
            "the paste is not landing where expected. "
            + saved
            + " Recalibrate the composer point and rerun: "
            f"python -m skills.automation_engine.ai_chain.calibrate "
            f"--site {spec.key} --point composer --record"
        )

    def _composer_candidates(self, spec: SiteSpec) -> list[tuple[float, float]]:
        """Ordered composer click points: DOM hit, estimate, nudged variants.

        Retries must try somewhere NEW — the same wrong point re-clicked
        three times is three guaranteed failures.
        """
        points: list[tuple[float, float]] = []
        dom_hit = self._dom_point(spec, "composer")
        if dom_hit is not None:
            points.append(dom_hit)
        points.append(spec.composer)
        points.append((spec.composer[0], max(0.5, spec.composer[1] - 0.04)))
        points.append((0.5, 0.9))
        unique: list[tuple[float, float]] = []
        seen: set[tuple[float, float]] = set()
        for point in points:
            key = (round(point[0], 3), round(point[1], 3))
            if key not in seen:
                seen.add(key)
                unique.append(point)
        return unique

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

    def _focus_composer(self, spec: SiteSpec, point: tuple[float, float] | None = None) -> None:
        """Click the composer so paste lands in the right field."""
        rect = self.ctrl.window_rect(spec.title_keyword)
        # v1.5: regex the page HTML for the real composer element first;
        # fall back to the calibrated estimate when DOM locating is off
        # or finds nothing. ``point`` overrides both (retry candidates).
        if point is None:
            point = self._composer_candidates(spec)[0]
        x, y = self.ctrl.fraction_point(rect, *point)
        self.ctrl.click(x, y)
        time.sleep(0.6)

    def _read_transcript(self, spec: SiteSpec) -> tuple[str, bool]:
        """Read the reply area; returns (text, via_button_copy).

        Preferred: click the site's registered "Copy" button (browser
        awareness registry), so the clipboard holds ONLY the assistant's
        message — no Ctrl+A of the whole website on every poll. The bool
        tells callers the text is a verbatim message (no prompt-based
        heuristic applies). When the site has no registered button or the
        click misses (clipboard empty after the retries), fall back to
        focusing the conversation area and Select-All + Copy the page,
        returning ``(text, False)``.
        """
        rect = self.ctrl.window_rect(spec.title_keyword)
        # Click into the conversation area first: it moves the caret out
        # of the composer and, on most UIs, reveals the message actions.
        hx, hy = self.ctrl.fraction_point(rect, *spec.read_point)
        self.ctrl.click(hx, hy)
        time.sleep(0.4)

        if uses_button_copy(spec.key):
            # v1.5 — the page HTML tells us where the button is (regex),
            # so start there instead of at an estimate.
            point = self._dom_point(spec, "copy")
            if point is not None:
                x, y = self.ctrl.fraction_point(rect, *point)
                text = self.ctrl.copy_with_button(x, y)
                if text:
                    return text, True
                logger.info(
                    f"[{spec.label}] DOM Copy hit missed the clipboard — falling back to scan"
                )

            # v1.0 fallback — DOM locating failed or is off. Click the
            # single CALIBRATED point (verified by the clipboard: a Copy
            # button is the only affordance that puts message text there).
            # The multi-point scan grid is DISABLED by default — HTML
            # element discovery must not guess coordinates
            # (AI_CHAIN_COORDINATE_SCAN=1 re-enables the legacy grid).
            candidates = copy_scan_candidates(spec.key)
            if candidates:
                budget = len(candidates) if coordinate_scan_enabled() else 1
                for fx, fy in candidates[:budget]:
                    x, y = self.ctrl.fraction_point(rect, fx, fy)
                    text = self.ctrl.copy_with_button(x, y)
                    if text:
                        return text, True
                    logger.info(
                        f"[{spec.label}] Copy button miss at ({fx:.2f}, {fy:.2f}) — "
                        "falling back to the page copy"
                    )
                logger.info(f"[{spec.label}] Copy button not found — falling back to page copy")

        return self.ctrl.select_all_and_copy(), False

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
        last_via_button = False
        stable_count = 0
        chrome_streak = 0

        while time.time() - started < spec.max_wait:
            self.ctrl.check_abort()
            time.sleep(spec.poll_interval)

            transcript, via_button = self._read_transcript(spec)
            reply = extract_reply(transcript, prompt, spec.footer_markers)
            elapsed = time.time() - started

            # Fail fast on deterministic non-conversation screens. A Copy
            # button read is a real message by construction — the button
            # only exists next to a reply — so screen classification does
            # not apply to it.
            if not via_button:
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
            last_via_button = via_button

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
        return last_text, last_via_button


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
