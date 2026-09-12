"""
ai_chain/selenium_dom.py

Selenium-backed twin of ``dom.DomReader`` — the primary DOM attachment.

It attaches to the ALREADY-RUNNING automation Chrome (the one
``control.py`` launched with ``--remote-debugging-port``, persistent
profile and logins) through Selenium's ``debuggerAddress`` capability.
No second browser is started and — unlike ``driver.quit()`` on a
launched session — the attachment is released without ever closing the
browser the robot depends on.

The affordance decision is Python-side and shared with the Playwright
reader: the page snapshot (HTML + candidate element boxes + window
dims) is fed to the same pure ``pick_element``/``rect_to_fraction``
helpers, so both backends pick the SAME element. Selenium is only the
ruler and the messenger — the BS4/regex parsing in ``dom.py`` is the
decision-maker, exactly like the Playwright path.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from utils.logger import get_logger

from .dom import (
    _FILL_JS,
    _SNAPSHOT_JS,
    ViewportDims,
    pick_element,
    rect_to_fraction,
)

logger = get_logger(__name__)


def debugger_address(cdp_url: str) -> str:
    """``http://127.0.0.1:9222`` -> ``127.0.0.1:9222`` (Selenium's format)."""
    netloc = (urlparse(cdp_url or "").netloc or "").strip()
    return netloc or "127.0.0.1:9222"


class SeleniumDomReader:
    """Read-only window into the automation Chrome via Selenium.

    Attaches once, finds the tab whose URL matches the site, and lets
    the shared Python-side ``pick_element`` pick affordances out of the
    page snapshot; the winner's bounding box comes back as window
    fractions for the ScreenController to click. ``fill`` performs the
    backend send through the same shared DevTools script the Playwright
    reader uses.
    """

    def __init__(self, cdp_url: str):
        self.cdp_url = cdp_url
        self._driver: Any = None
        self._connected = False

    def connect(self) -> None:
        """Attach to the running Chrome. Raises when it is not reachable."""
        from selenium import webdriver

        options = webdriver.ChromeOptions()
        options.add_experimental_option("debuggerAddress", debugger_address(self.cdp_url))
        try:
            # Selenium Manager fetches a matching chromedriver on demand;
            # an offline machine without a cached driver lands in the
            # caller's "backend failed" fallback.
            self._driver = webdriver.Chrome(options=options)
        except Exception:
            self.close()
            raise
        self._connected = True

    def close(self) -> None:
        """Release the attachment WITHOUT quitting the browser.

        ``driver.quit()`` on a debuggerAddress-attached session shuts
        down the whole automation Chrome — its profile holds the site
        logins and the robot reuses the window across steps. Dropping
        the reference is all the teardown an attachment needs; the
        Selenium Manager-spawned chromedriver is reaped when this
        process exits.
        """
        self._connected = False
        self._driver = None

    # ------------------------------------------------------------------
    # Tab selection
    # ------------------------------------------------------------------

    def _find_page(self, url_keyword: str) -> str | None:
        """The window handle of the tab the robot is driving.

        Prefer a matching tab whose ``document.visibilityState`` is
        "visible" (the one on screen — click points and backend sends
        computed from a background tab hit the wrong spot), falling back
        to the first matching handle otherwise. Handle order carries no
        recency guarantee, so among visible matches the last one wins
        (best effort, same spirit as the Playwright reader's newest
        visible tab).
        """
        if not self._connected or not url_keyword:
            return None
        try:
            handles = list(self._driver.window_handles)
        except Exception as exc:  # pragma: no cover - live browser
            logger.debug(f"[dom/selenium] window handle lookup failed: {exc}")
            return None
        matching: list[str] = []
        visible: list[str] = []
        for handle in handles:
            try:
                self._driver.switch_to.window(handle)
                if url_keyword not in (self._driver.current_url or "").lower():
                    continue
            except Exception:  # pragma: no cover - live browser
                continue
            matching.append(handle)
            try:
                if self._driver.execute_script("return document.visibilityState") == "visible":
                    visible.append(handle)
            except Exception:  # pragma: no cover - live browser
                continue
        chosen = visible[-1] if visible else (matching[0] if matching else None)
        if chosen is not None:
            try:
                self._driver.switch_to.window(chosen)
            except Exception:  # pragma: no cover - live browser
                return None
        return chosen

    # ------------------------------------------------------------------
    # Snapshot + actions (same decision logic as dom.DomReader)
    # ------------------------------------------------------------------

    def _snapshot_page(self, matchers: list) -> tuple[str, ViewportDims, dict[str, Any]] | None:
        """Pull the page HTML + candidate elements in one evaluate (None on error)."""
        try:
            snapshot: dict[str, Any] = self._driver.execute_script(
                f"const snapshot = {_SNAPSHOT_JS}; return snapshot(arguments[0]);",
                sorted({(m.tag, m.attribute) for m in matchers}),
            )
        except Exception as exc:  # pragma: no cover - live browser
            logger.debug(f"[dom/selenium] snapshot failed: {exc}")
            return None
        html = snapshot.get("html", "") or ""
        dims = ViewportDims(
            outer_width=float(snapshot["dims"]["outer_width"]),
            inner_width=float(snapshot["dims"]["inner_width"]),
            outer_height=float(snapshot["dims"]["outer_height"]),
            inner_height=float(snapshot["dims"]["inner_height"]),
        )
        candidates = snapshot.get("candidates", {}) or {}
        return html, dims, candidates

    def locate(self, url_keyword: str, matchers: list) -> tuple[float, float] | None:
        """Find an affordance; return its window-fraction centre or None.

        Same contract as ``DomReader.locate``: returns None when the
        attach failed, the tab is missing, or nothing matched (the
        caller falls back to v1.0 locating).
        """
        if not self._connected or not matchers:
            return None
        if self._find_page(url_keyword) is None:
            return None
        snap = self._snapshot_page(matchers)
        if snap is None:
            return None
        html, dims, candidates = snap
        won = pick_element(html, candidates, matchers)
        if won is None:
            return None
        _matcher, _value, rect = won
        return rect_to_fraction(dims, rect)

    def fill(self, url_keyword: str, matchers: list, text: str) -> bool:
        """Place ``text`` into the composer over the debug port.

        Same contract as ``DomReader.fill``: the shared Python-side
        ``pick_element`` decides WHICH element is the composer; a small
        DevTools script focuses it and inserts the text. No mouse
        movement, no clipboard. Never raises — returns False so the
        caller can fall back to the mouse path.
        """
        if not self._connected or not matchers or not (text or "").strip():
            return False
        if self._find_page(url_keyword) is None:
            logger.info("[dom/selenium] backend send skipped: no matching tab is open")
            return False
        snap = self._snapshot_page(matchers)
        if snap is None:
            return False
        html, _dims, candidates = snap
        won = pick_element(html, candidates, matchers)
        if won is None:
            logger.info("[dom/selenium] backend send skipped: no composer element matched the HTML")
            return False
        matcher, value, _rect = won
        try:
            result: dict[str, Any] = self._driver.execute_script(
                f"const fill = {_FILL_JS}; return fill(arguments[0]);",
                {
                    "tag": matcher.tag,
                    "attr": matcher.attribute,
                    "value": value,
                    "text": text,
                },
            )
        except Exception as exc:  # pragma: no cover - live browser
            logger.info(f"[dom/selenium] backend send failed: {exc}")
            return False
        if result and result.get("ok"):
            logger.info(
                f"[dom/selenium] backend send inserted the prompt into the composer "
                f"({result.get('chars', '?')} chars)"
            )
            return True
        reason = (result or {}).get("reason", "unknown")
        logger.info(f"[dom/selenium] backend send rejected by the page: {reason}")
        return False
