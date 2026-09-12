"""
skills/browser_awareness/driver.py

Browser session lifecycle for Browser Awareness.

Two stacks, one interface (env-selectable via BROWSER_AWARENESS_DRIVER):

    selenium   — the PRIMARY stack. webdriver.Chrome either launches an
                 isolated Chrome (temporary profile) or, when
                 BROWSER_AWARENESS_CDP_URL is set, ATTACHES to an
                 already-running Chrome via the debuggerAddress
                 capability. Selenium Manager fetches the matching
                 chromedriver on demand.
    playwright — the FALLBACK stack (when Selenium is not installed or
                 is explicitly selected against). Launches Chrome via
                 channel="chrome" or attaches over CDP.

Two connection modes (either stack):

1. DEFAULT — an isolated browser with a brand-new temporary profile, so
   nothing the automation does can touch the user's real browsing
   profile, cookies or session. The profile directory is deleted when
   the run ends. A visible window opens so the user can watch the
   automation work; set BROWSER_AWARENESS_HEADLESS=1 to hide it
   (launch mode only).

2. BROWSER_AWARENESS_CDP_URL=http://127.0.0.1:9222 — attach to Chrome
   that is ALREADY RUNNING with --remote-debugging-port=9222. The
   automation then opens a NEW TAB in that same Chrome window (e.g. the
   window where the Sarthi chat tab lives) instead of a separate one.
   Attach mode uses the running browser's profile, so isolation is only
   as good as that window's session — use it when you want the actions
   visible next to your chat. Each command opens its own tab; the tab
   is closed when the run ends (never the browser itself).

Selenium/Playwright are imported lazily: the rest of the capability
imports and tests cleanly without either.
"""

from __future__ import annotations

import os
import tempfile
from urllib.parse import urlparse

from utils.logger import get_logger

from .inspector import BeautifulSoupInspector, PlaywrightInspector
from .selenium_page import SeleniumPageAdapter

logger = get_logger(__name__)

NAVIGATION_TIMEOUT_MS = 30_000

DRIVER_ENV = "BROWSER_AWARENESS_DRIVER"


def driver_backend() -> str:
    """'selenium' | 'playwright' — Selenium is primary, Playwright fallback.

    ``BROWSER_AWARENESS_DRIVER=selenium|playwright`` pins a stack;
    unset (or anything else) auto-selects Selenium when it is
    installed, Playwright otherwise.
    """
    raw = os.environ.get(DRIVER_ENV, "").strip().lower()
    if raw in ("selenium", "playwright"):
        return raw
    try:
        import selenium  # noqa: F401

        return "selenium"
    except ImportError:
        return "playwright"


class BrowserSession:
    """Owns one automated browsing context for the duration of one run.

    ``close()`` destroys the temporary context (and profile) it created.
    In CDP attach mode it only closes the tab it opened — never the
    user's browser. ``inspector_factory`` pairs the session with the
    inspector that understands its page object (BeautifulSoup for
    Selenium, Playwright's JS-walk inspector for Playwright).
    """

    def __init__(
        self,
        page=None,
        context=None,
        owns_context: bool = False,
        inspector_factory=None,
    ):
        self.page = page
        self._context = context
        self._owns_context = owns_context
        self._temp_owner = None
        self.inspector_factory = inspector_factory or PlaywrightInspector
        # Selenium-only state (None on the Playwright path).
        self._driver = None
        self._owns_browser = False
        self._tab_handle = None
        self._original_handle = None

    def close(self) -> None:
        """Release the temporary browsing context (and its profile)."""
        if self._driver is not None:
            self._close_selenium()
        else:
            self._close_playwright()
        if self._temp_owner is not None:
            try:
                self._temp_owner.cleanup()
            except OSError:
                pass  # temp profile already gone
            self._temp_owner = None

    def _close_playwright(self) -> None:
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
        self.page = None
        self._context = None

    def _close_selenium(self) -> None:
        # Attach mode: close ONLY our tab and hand focus back to the
        # tab the user was on. Never quit() the driver here — quitting
        # a debuggerAddress-attached session shuts the user's whole
        # Chrome down.
        if not self._owns_browser and self._tab_handle is not None:
            try:
                self._driver.switch_to.window(self._tab_handle)
                self._driver.close()
            except Exception as exc:  # pragma: no cover - live browser
                logger.debug(f"tab close failed: {exc}")
            try:
                self._driver.switch_to.window(self._original_handle)
            except Exception as exc:  # pragma: no cover - live browser
                logger.debug(f"focus restore failed: {exc}")
        if self._owns_browser:
            try:
                self._driver.quit()
            except Exception as exc:  # pragma: no cover - live browser
                logger.debug(f"driver quit failed: {exc}")
        self.page = None
        self._driver = None


def open_session(url: str) -> BrowserSession:
    """Open ``url`` in an automated Chrome session (see module docstring)."""
    cdp_url = os.environ.get("BROWSER_AWARENESS_CDP_URL", "").strip()
    backend = driver_backend()
    if backend == "selenium":
        return open_selenium_session(url, cdp_url)

    if cdp_url:
        logger.info(f"[BROWSER] attaching to running Chrome at {cdp_url} (playwright)")
        return _attach_session(cdp_url, url)

    logger.info("[BROWSER] launching isolated Chrome (playwright, channel=chrome)")
    return _launch_playwright_session(url)


# ----------------------------------------------------------------------
# Selenium (primary)
# ----------------------------------------------------------------------


def open_selenium_session(url: str, cdp_url: str = "") -> BrowserSession:
    """Open ``url`` through Selenium (attach mode when ``cdp_url`` is set)."""
    from selenium import webdriver

    options = webdriver.ChromeOptions()
    options.add_argument("--no-first-run")
    options.add_argument("--no-default-browser-check")
    headless = os.environ.get("BROWSER_AWARENESS_HEADLESS", "").strip() == "1"

    if cdp_url:
        logger.info(f"[BROWSER] attaching to running Chrome at {cdp_url} (selenium)")
        options.add_experimental_option("debuggerAddress", _cdp_host_port(cdp_url))
        driver = _make_chrome(webdriver, options)
        original = driver.current_window_handle
        # A new tab in the user's Chrome window (never a second browser).
        driver.switch_to.new_window("tab")
        driver.get(url)
        session = BrowserSession(
            page=SeleniumPageAdapter(driver),
            inspector_factory=BeautifulSoupInspector,
        )
        session._driver = driver
        session._tab_handle = driver.current_window_handle
        session._original_handle = original
        return session

    temp_owner = tempfile.TemporaryDirectory(prefix="sarthi_awareness_")
    try:
        options.add_argument(f"--user-data-dir={temp_owner.name}")
        if headless:
            options.add_argument("--headless=new")
        logger.info("[BROWSER] launching isolated Chrome (selenium)")
        driver = _make_chrome(webdriver, options)
        driver.get(url)
        session = BrowserSession(
            page=SeleniumPageAdapter(driver),
            inspector_factory=BeautifulSoupInspector,
        )
        session._driver = driver
        session._owns_browser = True
        session._temp_owner = temp_owner
        return session
    except Exception:
        temp_owner.cleanup()
        raise


def _make_chrome(webdriver, options):
    """Start Chrome through Selenium or fail with an actionable message."""
    try:
        return webdriver.Chrome(options=options)
    except Exception as exc:
        raise RuntimeError(
            "Browser Awareness could not start Chrome through Selenium. Chrome "
            "must be installed (Selenium Manager fetches the driver on demand), "
            "or pick the Playwright stack with BROWSER_AWARENESS_DRIVER=playwright. "
            f"Original error: {exc}"
        ) from exc


def _cdp_host_port(cdp_url: str) -> str:
    """``http://127.0.0.1:9222`` -> ``127.0.0.1:9222`` (debuggerAddress)."""
    netloc = (urlparse(cdp_url or "").netloc or "").strip()
    return netloc or "127.0.0.1:9222"


# ----------------------------------------------------------------------
# Playwright (fallback)
# ----------------------------------------------------------------------


def _launch_playwright_session(url: str) -> BrowserSession:
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
