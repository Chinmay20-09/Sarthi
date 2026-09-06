"""
ai_chain/dom.py — v1.5

DOM-aware locating for the AI chain (regex over the page HTML instead of
blind coordinate guessing).

v1.0 found UI affordances (the message Copy button, the composer, the
image download button) by clicking *estimated window-fraction points* and,
when they missed, scanning a grid of candidate clicks — every click
verified only by whether it put text on the clipboard. That works, but it
is blind: after a UI change the estimates drift and the robot clicks
around the screen hoping to hit a button.

v1.5 flips it around. It attaches to the user's already-running Chrome
over the DevTools Protocol (read-only), pulls the page's HTML, and
**regexes it** for the affordance — exactly the strings a human would
look for: ``aria-label="Copy"``, ``id="prompt-textarea"``,
``aria-label="Enter a prompt here"``, ``aria-label="Download"``, ...
The matched element's bounding box is converted into a window-fraction
point and handed to the existing ScreenController, so the click is
verified by the clipboard exactly as before — only now it starts at the
*right* place instead of an estimate.

Why read-only + regex instead of clicking through CDP
-----------------------------------------------------
- The module's safety model stays untouched: hands-off mode, the
  Ctrl+Alt+X abort hotkey and the mouse-corner failsafe are all
  PyAutoGUI/ScreenController primitives, and the click path is
  identical.
- Unit tests keep running against the stub controller with zero browser
  dependencies (Playwright is imported lazily, same convention as
  ``browser_awareness``).
- If the attach fails, or a regex finds nothing (closed shadow roots,
  iframes, a UI redesign), every locator returns ``None`` and the driver
  falls back to the v1.0 point + scan grid + Ctrl+A page copy. Nothing
  breaks — v1.5 just stops guessing first.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Any
from urllib.parse import urlparse

from utils.logger import get_logger

logger = get_logger(__name__)

DEFAULT_CDP_URL = "http://127.0.0.1:9222"
CDP_URL_ENV = "AI_CHAIN_CDP_URL"
CDP_PORT_ENV = "AI_CHAIN_CDP_PORT"
MASTER_SWITCH_ENV = "AI_CHAIN_DOM"


def cdp_port() -> int:
    """The DevTools port to use (AI_CHAIN_CDP_URL port > AI_CHAIN_CDP_PORT > 9222).

    Shared with control.py so the robot launches its automation Chrome on
    exactly the port the DOM reader will attach to.
    """
    raw_url = os.getenv(CDP_URL_ENV, "").strip()
    if raw_url:
        port = urlparse(raw_url).port
        if port:
            return port
    raw_port = os.getenv(CDP_PORT_ENV, "").strip()
    try:
        return int(raw_port) if raw_port else 9222
    except ValueError:
        return 9222


def cdp_url() -> str:
    """The DevTools endpoint URL (AI_CHAIN_CDP_URL or http://127.0.0.1:<port>)."""
    raw_url = os.getenv(CDP_URL_ENV, "").strip()
    if raw_url:
        return raw_url.rstrip("/")
    return f"http://127.0.0.1:{cdp_port()}"


@dataclass(frozen=True)
class ViewportDims:
    """Browser window outer/inner sizes in CSS pixels (JS ``window.*``)."""

    outer_width: float
    inner_width: float
    outer_height: float
    inner_height: float


@dataclass(frozen=True)
class ElementRect:
    """Bounding box of an element relative to the viewport (CSS px)."""

    x: float
    y: float
    width: float
    height: float


# ----------------------------------------------------------------------
# Pure helpers (no browser needed — unit-testable)
# ----------------------------------------------------------------------


def dom_enabled() -> bool:
    """Master switch: ``AI_CHAIN_DOM=0`` disables all DOM locating."""
    return os.getenv(MASTER_SWITCH_ENV, "").strip() != "0"


def keyword_for(url: str) -> str:
    """Host keyword used to find the right tab: 'https://chatgpt.com/' -> 'chatgpt.com'."""
    host = (urlparse(url or "").netloc or "").lower()
    return host[4:] if host.startswith("www.") else host


def rect_to_fraction(dims: ViewportDims, rect: ElementRect) -> tuple[float, float]:
    """Convert an element's viewport-relative box into window fractions.

    The viewport sits inside the browser window below the chrome (tab
    strip, toolbar). The chrome offset is approximated from the
    difference between outer and inner window sizes — nearly all of it is
    top chrome, and clicking the *centre* of a button tolerates the few
    pixels of border error. Fractions are DPI-agnostic because both the
    element box and the window dims come from the same CSS-pixel space,
    so they convert cleanly against the real window rect.
    """
    chrome_x = max(0.0, (dims.outer_width - dims.inner_width) / 2.0)
    chrome_y = max(0.0, dims.outer_height - dims.inner_height)
    fx = (chrome_x + rect.x + rect.width / 2.0) / max(dims.outer_width, 1.0)
    fy = (chrome_y + rect.y + rect.height / 2.0) / max(dims.outer_height, 1.0)
    return (min(max(fx, 0.0), 1.0), min(max(fy, 0.0), 1.0))


@lru_cache(maxsize=64)
def _tag_attr_regex(tag: str, attribute: str) -> re.Pattern:
    """Regex for an opening tag carrying the attribute: <tag ... attr="v">."""
    tag_part = re.escape(tag) + r"\b" if tag else r"[a-zA-Z][\w-]*"
    attr_part = re.escape(attribute)
    return re.compile(
        rf"<{tag_part}[^>]*?\b{attr_part}\s*=\s*(\"([^\"]*)\"|'([^']*)')",
        re.IGNORECASE | re.DOTALL,
    )


def find_affordances(html: str, matcher: Any) -> list[str]:
    """All attribute values on matching tags, in document order.

    ``matcher`` is a registry.DomMatcher (duck-typed here to keep this
    module dependency-free): ``tag`` ('' = any element), ``attribute``
    ('' = no attribute check) and ``value_pattern`` (regex, checked
    case-insensitively against the attribute value).
    """
    tag = getattr(matcher, "tag", "") or ""
    attribute = getattr(matcher, "attribute", "") or ""
    pattern = getattr(matcher, "value_pattern", "") or ""
    if not attribute or not pattern:
        return []
    values: list[str] = []
    for match in _tag_attr_regex(tag, attribute).finditer(html or ""):
        value = match.group(2) if match.group(2) is not None else match.group(3)
        if value is not None and re.search(pattern, value, re.IGNORECASE):
            values.append(value)
    return values


def pick_element(
    html: str,
    candidates: dict[str, list[dict[str, Any]]],
    matchers: list,
) -> tuple[Any, str, ElementRect] | None:
    """Pick the winning affordance element from a snapshot (pure, testable).

    Matchers are tried in order — the first one whose regex hits the page
    HTML wins, and the *last* matching element in document order is
    chosen: chat UIs append messages at the bottom, so the newest
    message's affordance is the last match.

    Returns ``(matcher, attribute_value, rect)`` or ``None`` when no
    regex matched (the caller then falls back). Both ``locate`` (click
    points) and ``fill`` (backend send) must agree on the winner, which
    is why the decision lives in one pure function.
    """
    for matcher in matchers:
        if not find_affordances(html, matcher):
            continue  # regex says this affordance is not on the page
        key = f"{matcher.tag}|{matcher.attribute}"
        hits = [
            c
            for c in candidates.get(key, [])
            if re.search(matcher.value_pattern, c.get("v", ""), re.IGNORECASE)
        ]
        if not hits:
            continue  # e.g. element hidden behind a closed shadow root
        last = hits[-1]
        rect = ElementRect(
            x=float(last.get("x", 0.0)),
            y=float(last.get("y", 0.0)),
            width=float(last.get("w", 0.0)),
            height=float(last.get("h", 0.0)),
        )
        return matcher, str(last.get("v", "")), rect
    return None


# ----------------------------------------------------------------------
# CDP reader (lazy Playwright)
# ----------------------------------------------------------------------

# One evaluate both snapshots the HTML and harvests every candidate
# element (rect + attribute value) for the tag/attribute pairs the
# caller asked about. Python then regexes the *snapshot* to pick the
# winning element — the regex is the decision-maker, JS is only the
# ruler.
_SNAPSHOT_JS = """(pairs) => {
  const candidates = {};
  for (const [tag, attr] of pairs) {
    const key = tag + "|" + attr;
    const items = [];
    let elements = [];
    try {
      elements = tag
        ? Array.from(document.getElementsByTagName(tag))
        : Array.from(document.querySelectorAll("[" + attr + "]"));
    } catch (e) {}
    for (const el of elements) {
      let value = null;
      try { value = el.getAttribute(attr); } catch (e) {}
      if (value === null || value === undefined) continue;
      const r = el.getBoundingClientRect();
      items.push({ v: String(value), x: r.x, y: r.y, w: r.width, h: r.height });
    }
    candidates[key] = items;
  }
  return {
    html: document.documentElement.outerHTML,
    dims: {
      outer_width: window.outerWidth,
      inner_width: window.innerWidth,
      outer_height: window.outerHeight,
      inner_height: window.innerHeight,
    },
    candidates: candidates,
  };
}"""

# The backend send: focus the composer the Python regexes picked and
# insert the text — no mouse movement, no clipboard. ``execCommand
# ("insertText")`` is what contenteditable editors (Gemini's
# rich-textarea, ChatGPT's prompt box, Claude's ProseMirror) accept as
# trusted input; textareas/inputs get a direct value + input event.
_FILL_JS = """(args) => {
  const { tag, attr, value, text } = args;
  let elements = [];
  try {
    elements = tag
      ? Array.from(document.getElementsByTagName(tag))
      : Array.from(document.querySelectorAll("[" + attr + "]"));
  } catch (e) {
    return { ok: false, reason: "enumeration failed" };
  }
  let el = null;
  for (const candidate of elements) {
    if (candidate.getAttribute(attr) === value) el = candidate;  // last wins
  }
  if (!el) return { ok: false, reason: "composer element not found" };

  // Descend to the innermost editable: Gemini's <rich-textarea> carries
  // the label while the editable is a <div contenteditable> inside it.
  let target = el;
  for (let depth = 0; depth < 4; depth++) {
    if (
      target.isContentEditable ||
      target.tagName === "TEXTAREA" ||
      target.tagName === "INPUT"
    ) break;
    const inner = target.querySelector(
      '[contenteditable="true"], textarea, input'
    );
    if (!inner) break;
    target = inner;
  }
  try {
    target.focus();
  } catch (e) {
    return { ok: false, reason: "focus rejected" };
  }

  // Replace whatever is in the composer with the backend text.
  try {
    document.execCommand("selectAll", false, null);
  } catch (e) {}
  let inserted = false;
  try {
    inserted = document.execCommand("insertText", false, text);
  } catch (e) {
    inserted = false;
  }
  if (!inserted) {
    if (target.tagName === "TEXTAREA" || target.tagName === "INPUT") {
      target.value = text;
      target.dispatchEvent(new Event("input", { bubbles: true }));
    } else {
      return { ok: false, reason: "editor rejected insertText" };
    }
  }
  return { ok: true, chars: (target.value || target.innerText || "").length };
}"""


class DomReader:
    """Read-only window into the user's Chrome via the DevTools Protocol.

    Attaches once (Playwright, lazily imported), finds the tab whose URL
    matches the site, and lets Python regexes pick affordances out of the
    page HTML; the winner's bounding box comes back as window fractions
    for the ScreenController to click.
    """

    def __init__(self, cdp_url: str):
        self.cdp_url = cdp_url
        self._playwright: Any = None
        self._browser: Any = None
        self._connected = False

    def connect(self) -> None:
        """Attach to the running Chrome. Raises when it is not reachable."""
        from playwright.sync_api import sync_playwright

        self._playwright = sync_playwright().start()
        try:
            self._browser = self._playwright.chromium.connect_over_cdp(self.cdp_url)
            self._connected = True
        except Exception:
            self.close()
            raise

    def close(self) -> None:
        self._connected = False
        if self._browser is not None:
            try:
                self._browser.close()
            except Exception:
                pass
            self._browser = None
        if self._playwright is not None:
            try:
                self._playwright.stop()
            except Exception:
                pass
            self._playwright = None

    def _find_page(self, url_keyword: str) -> Any:
        """The tab the robot is driving: a visible match, else the newest.

        The robot opens a fresh tab per step, so a long-lived automation
        Chrome accumulates tabs from earlier runs. The FIRST matching tab
        may be a stale background one whose layout (scroll position, open
        messages) no longer matches what is on screen — click points and
        backend sends computed from it hit the wrong spot. So: prefer a
        matching tab whose ``document.visibilityState`` is "visible"
        (newest such tab), and only fall back to the newest hidden match.
        """
        if not self._connected or not url_keyword:
            return None
        try:
            matches: list[Any] = []
            for context in self._browser.contexts:
                for page in context.pages:
                    if url_keyword in (page.url or "").lower():
                        matches.append(page)
            for page in reversed(matches):  # newest first
                if self._is_visible(page):
                    return page
            return matches[-1] if matches else None
        except Exception as exc:  # pragma: no cover - live browser
            logger.debug(f"[dom] tab lookup failed: {exc}")
            return None

    @staticmethod
    def _is_visible(page: Any) -> bool:
        """True when the tab is the active one in its window (best effort)."""
        try:
            return page.evaluate("document.visibilityState") == "visible"
        except Exception:  # pragma: no cover - live browser
            return False

    def _snapshot_page(
        self, page: Any, matchers: list
    ) -> tuple[str, ViewportDims, dict[str, Any]] | None:
        """Pull the page HTML + candidate elements in one evaluate (None on error)."""
        try:
            snapshot: dict[str, Any] = page.evaluate(
                _SNAPSHOT_JS,
                sorted({(m.tag, m.attribute) for m in matchers}),
            )
        except Exception as exc:  # pragma: no cover - live browser
            logger.debug(f"[dom] snapshot failed: {exc}")
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

        Matchers are tried in order (``pick_element`` decides); the
        winner's bounding box becomes a window-fraction point for the
        ScreenController to click. Returns None when the attach failed,
        the tab is missing, or no regex matched (the caller then falls
        back to v1.0 locating).
        """
        if not self._connected or not matchers:
            return None
        page = self._find_page(url_keyword)
        if page is None:
            return None
        snap = self._snapshot_page(page, matchers)
        if snap is None:
            return None
        html, dims, candidates = snap
        won = pick_element(html, candidates, matchers)
        if won is None:
            return None
        _matcher, _value, rect = won
        return rect_to_fraction(dims, rect)

    def fill(self, url_keyword: str, matchers: list, text: str) -> bool:
        """Place ``text`` into the composer over CDP — the backend send.

        The Python regexes decide WHICH element is the composer (the same
        ``pick_element`` rules ``locate`` uses); a small DevTools script
        then focuses it and inserts the text. No mouse movement, no
        clipboard — used when the clipboard paste could not be verified
        into the composer (step 2 of the chain).

        Returns True when the text was inserted. Never raises for a
        missing tab/element — it returns False so the caller can fall
        back to the mouse path.
        """
        if not self._connected or not matchers or not (text or "").strip():
            return False
        page = self._find_page(url_keyword)
        if page is None:
            logger.info("[dom] backend send skipped: no matching tab is open")
            return False
        snap = self._snapshot_page(page, matchers)
        if snap is None:
            return False
        html, _dims, candidates = snap
        won = pick_element(html, candidates, matchers)
        if won is None:
            logger.info("[dom] backend send skipped: no composer element matched the HTML")
            return False
        matcher, value, _rect = won
        try:
            result: dict[str, Any] = page.evaluate(
                _FILL_JS,
                {"tag": matcher.tag, "attr": matcher.attribute, "value": value, "text": text},
            )
        except Exception as exc:  # pragma: no cover - live browser
            logger.info(f"[dom] backend send failed: {exc}")
            return False
        if result and result.get("ok"):
            logger.info(
                f"[dom] backend send inserted the prompt into the composer "
                f"({result.get('chars', '?')} chars)"
            )
            return True
        reason = (result or {}).get("reason", "unknown")
        logger.info(f"[dom] backend send rejected by the page: {reason}")
        return False


# ----------------------------------------------------------------------
# Tried-once singleton
# ----------------------------------------------------------------------

_reader: DomReader | None = None
_reader_tried = False


def get_dom_reader(endpoint: str | None = None) -> DomReader | None:
    """Attach to Chrome once; return the reader (or None, cached).

    Caching the failure matters: the driver polls every few seconds and
    must not keep retrying a dead CDP endpoint on every poll. Returns
    None quietly when the master switch is off, Playwright is missing,
    or Chrome is not exposing the debug port — the caller falls back to
    the v1.0 locating.
    """
    global _reader, _reader_tried
    if _reader_tried:
        return _reader
    _reader_tried = True
    if not dom_enabled():
        return None
    url = endpoint or cdp_url()
    reader = DomReader(url)
    try:
        reader.connect()
    except ImportError:
        # Playwright is an optional dependency ([browser] extra). Without
        # it the driver silently degrades to estimated clicks — say so.
        logger.warning(
            "[dom] Playwright is not installed — HTML-aware locating is OFF "
            "(the robot falls back to estimated click points). Install it "
            "with: pip install playwright"
        )
        reader.close()
        return None
    except Exception as exc:
        logger.warning(
            f"[dom] CDP attach to {url} failed ({exc}) — HTML-aware locating is OFF "
            "for this run (the robot falls back to estimated click points)."
        )
        reader.close()
        return None
    logger.info(f"[dom] attached to Chrome at {url}")
    _reader = reader
    return _reader


def reset_dom_reader() -> None:
    """Close the reader and forget the cached attempt (tests / run end)."""
    global _reader, _reader_tried
    if _reader is not None:
        _reader.close()
    _reader = None
    _reader_tried = False
