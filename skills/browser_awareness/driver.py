"""
skills/browser_awareness/driver.py

Browser session lifecycle for Browser Awareness.

Two connection modes (env-selectable):

1. DEFAULT — Playwright launches the installed Chrome (channel="chrome")
   with a brand-new temporary profile, so nothing the automation does can
   touch the user's real browsing profile, cookies or session. The
   profile directory is deleted when the run ends. A visible window
   opens so the user can watch the automation work; set
   BROWSER_AWARENESS_HEADLESS=1 to hide it.

2. BROWSER_AWARENESS_CDP_URL=http://127.0.0.1:9222 — attach to Chrome
   that is ALREADY RUNNING with --remote-debugging-port=9222. The
   automation then opens a NEW TAB in that same Chrome window (e.g. the
   window where the Sarthi chat tab lives) instead of a separate one.
   Attach mode uses the running browser's profile, so isolation is only
   as good as that window's session — use it when you want the actions
   visible next to your chat. Each command opens its own tab; the tab is
   closed when the run ends (future work: reuse one dedicated tab).

Playwright is imported lazily: the rest of the capability imports and
tests cleanly without it.
"""

from __future__ import annotations

import os
import tempfile

from utils.logger import get_logger

logger = get_logger(__name__)

NAVIGATION_TIMEOUT_MS = 30_000


class BrowserSession:
    """Owns one automated browsing context for the duration of one run.

    ``close()`` destroys the temporary context (and profile) it created.
    In CDP attach mode it only closes the tab it opened — never the
    user's browser.
    """

    def __init__(self, page=None, context=None, owns_context: bool = False):
        self.page = page
        self._context = context
        self._owns_context = owns_context
        self._temp_owner = None

    def close(self) -> None:
        """Release the temporary browsing context (and its profile)."""
        try:
            if self.page is not None:
                # Close just our tab (CDP attach mode leaves the user's
                # Chrome window and other tabs untouched).
                self.page.close()
        except Exception as exc:  # pragma: no cover - live browser
            logger.debug(f"page close failed: {exc}")
        try:
            if self._context is not None and self._owns_context:
                self._context.close()
        except Exception as exc:  # pragma: no cover - live browser
            logger.debug(f"context close failed: {exc}")
        if self._temp_owner is not None:
            try:
                self._temp_owner.cleanup()
            except OSError:
                pass  # temp profile already gone
        self.page = None
        self._context = None


def open_session(url: str) -> BrowserSession:
    """Open ``url`` in an automated Chrome session (see module docstring)."""
    cdp_url = os.environ.get("BROWSER_AWARENESS_CDP_URL", "").strip()
    if cdp_url:
        logger.info(f"[BROWSER] attaching to running Chrome at {cdp_url}")
        return _attach_session(cdp_url, url)

    logger.info("[BROWSER] launching isolated Chrome (channel=chrome)")
    temp_owner = tempfile.TemporaryDirectory(prefix="sarthi_awareness_")
    try:
        from playwright.sync_api import sync_playwright

        playwright = sync_playwright().start()
        try:
            context = playwright.chromium.launch_persistent_context(
                user_data_dir=temp_owner.name,
                channel="chrome",
                headless=os.environ.get("BROWSER_AWARENESS_HEADLESS", "").strip() == "1",
                args=["--no-first-run", "--no-default-browser-check"],
            )
        except Exception as exc:
            playwright.stop()
            raise RuntimeError(
                "Browser Awareness could not launch Chrome. Install the driver "
                "with: pip install playwright  (Chrome must be installed). "
                f"Original error: {exc}"
            ) from exc

        page = context.pages[0] if context.pages else context.new_page()
        page.goto(url, timeout=NAVIGATION_TIMEOUT_MS, wait_until="domcontentloaded")
        session = BrowserSession(page=page, context=context, owns_context=True)
        session._temp_owner = temp_owner
        return session
    except Exception:
        temp_owner.cleanup()
        raise


def _attach_session(cdp_url: str, url: str) -> BrowserSession:
    """Attach to a running Chrome (--remote-debugging-port) and open a tab."""
    from playwright.sync_api import sync_playwright

    playwright = sync_playwright().start()
    try:
        browser = playwright.chromium.connect_over_cdp(cdp_url)
    except Exception as exc:
        playwright.stop()
        raise RuntimeError(
            "Could not attach to the running Chrome at "
            f"{cdp_url}. Start Chrome with: chrome.exe "
            "--remote-debugging-port=9222  "
            f"Original error: {exc}"
        ) from exc

    # contexts[0] is the real browser's default context — a new page in it
    # shows up as a new tab in the user's Chrome window.
    context = browser.contexts[0] if browser.contexts else browser.new_context()
    page = context.new_page()
    page.goto(url, timeout=NAVIGATION_TIMEOUT_MS, wait_until="domcontentloaded")
    return BrowserSession(page=page, context=context, owns_context=False)
