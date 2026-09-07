"""
skills/browser_awareness/inspector.py

DOM inspection into the compact PageSnapshot — two implementations:

  * PlaywrightInspector — runs one page-side script that walks the live
    DOM for visible, interactive elements and computes a stable CSS
    selector for each (the original, JS-based inspection).
  * BeautifulSoupInspector — parses the raw HTML (Selenium
    ``page_source`` / Playwright ``content()``) with BeautifulSoup — no
    page-side JavaScript at all. This is the inspector paired with the
    Selenium driver.

Both produce the *raw* facts; the compact, sanitized PageSnapshot is
built by the pure page_snapshot module. Raw HTML never leaves this
module.

All heavy imports (playwright, bs4) are lazy so this module — and the
whole capability — imports cleanly and stays unit-testable on machines
without them.
"""

from __future__ import annotations

from collections import Counter

from utils.logger import get_logger

from .page_snapshot import build_page_snapshot
from .schemas import PageSnapshot

logger = get_logger(__name__)

# Time budget for the page to reach a usable state before inspection.
NAVIGATION_TIMEOUT_MS = 30_000

_INSPECT_JS = r"""
() => {
  const visible = (el) => {
    if (!el || el.nodeType !== 1) return false;
    const style = window.getComputedStyle(el);
    if (style.display === 'none' || style.visibility === 'hidden'
        || el.getAttribute('aria-hidden') === 'true') return false;
    const rect = el.getBoundingClientRect();
    return rect.width > 0 && rect.height > 0;
  };
  const enabled = (el) => !el.disabled
    && el.getAttribute('aria-disabled') !== 'true';

  const stableSelector = (el) => {
    if (el.id && document.querySelectorAll('#' + CSS.escape(el.id)).length === 1) {
      return '#' + CSS.escape(el.id);
    }
    for (const attr of ['data-testid', 'data-test', 'data-qa', 'qa']) {
      const val = el.getAttribute(attr);
      if (val && document.querySelectorAll('[' + attr + '="' + CSS.escape(val) + '"]').length === 1) {
        return '[' + attr + '="' + CSS.escape(val) + '"]';
      }
    }
    if (el.name && (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA'
        || el.tagName === 'SELECT') && document.querySelectorAll(
          el.tagName.toLowerCase() + '[name="' + CSS.escape(el.name) + '"]').length === 1) {
      return el.tagName.toLowerCase() + '[name="' + CSS.escape(el.name) + '"]';
    }
    // Fall back to a tag:nth-of-type(n) path — stable against re-renders
    // of identical siblings.
    const parts = [];
    let node = el;
    while (node && node.nodeType === 1 && node.tagName !== 'BODY'
        && node.tagName !== 'HTML') {
      const tag = node.tagName.toLowerCase();
      let nth = 1;
      let sibling = node;
      while ((sibling = sibling.previousElementSibling) !== null) {
        if (sibling.tagName.toLowerCase() === tag) nth += 1;
      }
      parts.unshift(tag + ':nth-of-type(' + nth + ')');
      node = node.parentElement;
    }
    return parts.join(' > ');
  };

  const kindOf = (el) => {
    const tag = el.tagName.toLowerCase();
    const type = (el.getAttribute('type') || '').toLowerCase();
    if (tag === 'a' || (tag === 'button' && el.getAttribute('role') === 'link')
        || el.getAttribute('role') === 'link') return 'link';
    if (tag === 'button' || el.getAttribute('role') === 'button') return 'button';
    if (tag === 'input') {
      if (type === 'checkbox') return 'checkbox';
      if (type === 'radio') return 'radio';
      return 'input';
    }
    if (tag === 'textarea') return 'textarea';
    if (tag === 'select') return 'select';
    if (el.getAttribute('role') === 'navigation' || tag === 'nav') return 'nav';
    return 'other';
  };

  const labelOf = (el) => {
    const aria = el.getAttribute('aria-label');
    if (aria && aria.trim()) return aria.trim();
    if (el.id) {
      const labelled = document.querySelector('label[for="' + CSS.escape(el.id) + '"]');
      if (labelled) return (labelled.textContent || '').trim();
    }
    const wrap = el.closest('label');
    if (wrap) {
      const own = (wrap.textContent || '').trim();
      const inner = (el.value || '') + (el.textContent || '');
      return own.replace(inner, '').trim();
    }
    return '';
  };

  const wanted = document.querySelectorAll(
    'a, button, input, textarea, select, nav, [role="link"], '
    + '[role="button"], [role="navigation"], [role="checkbox"], [role="radio"]'
  );
  const elements = [];
  for (const el of wanted) {
    if (!visible(el)) continue;
    const kind = kindOf(el);
    const text = (el.textContent || '').trim();
    const placeholder = (el.getAttribute('placeholder') || '').trim();
    const label = labelOf(el);
    const name = (el.getAttribute('name') || '').trim();
    const href = (el.getAttribute('href') || '');
    const skip = !text && !placeholder && !label && !name && !href
      && kind !== 'input' && kind !== 'textarea' && kind !== 'select';
    if (skip) continue;
    elements.push({
      kind, text, placeholder, label, name, href,
      selector: stableSelector(el),
      visible: true, enabled: enabled(el),
    });
  }

  // Forms: any form containing at least one interactive child (the pure
  // snapshot keeps a count only; Hermes reasons about elements).
  const forms = document.querySelectorAll('form');
  const formCount = Array.from(forms).filter((f) => f.querySelector('input, button, select, textarea')).length;

  return {
    url: location.href,
    title: document.title,
    text: (document.body && document.body.innerText) || '',
    elements,
    formCount,
  };
}
"""


class PlaywrightInspector:
    """Inspect one page (a Playwright Page) into a compact snapshot."""

    def __init__(self, page):
        self._page = page

    def inspect(self) -> PageSnapshot:
        """Wait for the page to settle and build the current PageSnapshot."""
        try:
            self._page.wait_for_load_state("domcontentloaded", timeout=NAVIGATION_TIMEOUT_MS)
        except Exception as exc:  # pragma: no cover - depends on live browser
            logger.debug(f"load-state wait failed (inspecting anyway): {exc}")
        raw = self._page.evaluate(_INSPECT_JS)
        snapshot = build_page_snapshot(
            url=raw.get("url", ""),
            title=raw.get("title", ""),
            page_text=raw.get("text", ""),
            raw_elements=raw.get("elements", []),
        )
        logger.info(
            f"[BROWSER] inspected {snapshot.url}: {len(snapshot.elements)} interactive elements"
        )
        return snapshot


# ---------------------------------------------------------------------------
# BeautifulSoupInspector — static HTML parsing, no page-side JS
# ---------------------------------------------------------------------------

# The same element universe the Playwright JS walk collects.
_WANTED_TAGS = ("a", "button", "input", "textarea", "select", "nav")
_WANTED_ROLES = ("link", "button", "navigation", "checkbox", "radio")
_SELECTOR_ATTRS = ("data-testid", "data-test", "data-qa", "qa")


class BeautifulSoupInspector:
    """Inspect one page by parsing its HTML with BeautifulSoup.

    Works on either backend's page object: Selenium drivers expose
    ``page_source``/``current_url``, Playwright pages ``content()``/
    ``url`` — both are probed. No JavaScript runs on the page.

    Static markup cannot know computed CSS, so elements are treated as
    visible unless the markup says otherwise (aria-hidden, inline
    ``display:none`` / ``visibility:hidden``, ``disabled``) — the
    SafeExecutor re-verifies live before every action anyway.
    """

    def __init__(self, page):
        self._page = page

    def inspect(self) -> PageSnapshot:
        """Build the current PageSnapshot from the page's HTML."""
        try:
            from bs4 import BeautifulSoup
        except ImportError as exc:  # optional dependency ([browser] extra)
            raise RuntimeError(
                "BeautifulSoup is not installed — install it with: pip install beautifulsoup4"
            ) from exc

        self._wait_for_load()
        soup = BeautifulSoup(_page_html(self._page), "html.parser")
        raw_elements = collect_raw_elements(soup)
        snapshot = build_page_snapshot(
            url=_page_url(self._page),
            title=_page_title(self._page),
            page_text=_page_text(self._page),
            raw_elements=raw_elements,
        )
        logger.info(
            f"[BROWSER] inspected {snapshot.url}: {len(snapshot.elements)} "
            "interactive elements (bs4)"
        )
        return snapshot

    def _wait_for_load(self) -> None:
        """Playwright pages get a load-state wait; Selenium's get() already blocks."""
        try:
            self._page.wait_for_load_state("domcontentloaded", timeout=NAVIGATION_TIMEOUT_MS)
        except Exception as exc:  # no such method / live-browser hiccup
            logger.debug(f"load-state wait skipped: {exc}")


def _page_html(page) -> str:
    """Raw HTML from either backend (Selenium page_source / PW content)."""
    source = getattr(page, "page_source", None)
    if isinstance(source, str) and source:
        return source
    try:
        return page.content() or ""
    except Exception:  # pragma: no cover - live browser
        return ""


def _page_url(page) -> str:
    """Current URL from either backend (``current_url`` / ``url``)."""
    url = getattr(page, "current_url", None) or getattr(page, "url", "")
    return str(url) if url else ""


def _page_title(page) -> str:
    """Title from either backend (property on Selenium, method on Playwright)."""
    title = getattr(page, "title", None)
    if callable(title):
        try:
            return str(title() or "")
        except Exception:  # pragma: no cover - live browser
            return ""
    return str(title or "")


def _page_text(page) -> str:
    """Rendered body text (respects visibility); parsed text as fallback."""
    try:
        text = page.inner_text("body")
        if text:
            return text
    except Exception:
        pass
    soup = None
    try:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(_page_html(page), "html.parser")
    except Exception:
        return ""
    body = soup.find("body")
    return body.get_text(" ", strip=True) if body else ""


def collect_raw_elements(soup) -> list[dict]:
    """Raw element facts from parsed HTML (pure — unit-testable).

    Mirrors the Playwright walk's element universe, kind rules, skip
    rules and stable-selector scheme so either inspector feeds
    ``build_page_snapshot`` the same shape.
    """
    all_elements = soup.find_all(True)
    id_counts = Counter(e.get("id") for e in all_elements if e.get("id"))
    attr_counts = {
        attr: Counter(e.get(attr) for e in all_elements if e.get(attr)) for attr in _SELECTOR_ATTRS
    }
    name_counts = Counter(
        e.get("name")
        for e in all_elements
        if e.name in ("input", "textarea", "select") and e.get("name")
    )
    labels_by_for: dict[str, str] = {}
    for label_el in soup.find_all("label"):
        label_for = label_el.get("for")
        if label_for and label_for not in labels_by_for:
            labels_by_for[label_for] = label_el.get_text(" ", strip=True)

    elements: list[dict] = []
    seen: set[int] = set()
    for element in _candidates(soup):
        node_id = id(element)
        if node_id in seen:
            continue
        seen.add(node_id)
        if not _looks_visible(element):
            continue
        kind = _kind_of(element)
        text = element.get_text(" ", strip=True)
        placeholder = (element.get("placeholder") or "").strip()
        label = _label_of(element, labels_by_for)
        name = (element.get("name") or "").strip()
        href = element.get("href") or ""
        if (
            not text
            and not placeholder
            and not label
            and not name
            and not href
            and kind not in ("input", "textarea", "select")
        ):
            continue
        elements.append(
            {
                "kind": kind,
                "text": text,
                "placeholder": placeholder,
                "label": label,
                "name": name,
                "href": href,
                "selector": _stable_selector(element, id_counts, attr_counts, name_counts),
                "visible": True,
                "enabled": _looks_enabled(element),
            }
        )
    return elements


def _candidates(soup) -> list:
    """Wanted tags + role-bearing elements, in document order."""
    wanted = list(soup.find_all(_WANTED_TAGS))
    for role in _WANTED_ROLES:
        wanted.extend(soup.find_all(attrs={"role": role}))
    return wanted


def _looks_visible(element) -> bool:
    """Markup-level visibility (computed CSS is unknowable without a render)."""
    if element.get("aria-hidden") == "true":
        return False
    style = (element.get("style") or "").replace(" ", "").lower()
    if "display:none" in style or "visibility:hidden" in style:
        return False
    return True


def _looks_enabled(element) -> bool:
    return element.get("disabled") is None and element.get("aria-disabled") != "true"


def _kind_of(element) -> str:
    tag = element.name
    type_attr = (element.get("type") or "").lower()
    role = (element.get("role") or "").lower()
    if tag == "a" or role == "link":
        return "link"
    if tag == "button" or role == "button":
        return "button"
    if tag == "input":
        if type_attr == "checkbox":
            return "checkbox"
        if type_attr == "radio":
            return "radio"
        return "input"
    if tag == "textarea":
        return "textarea"
    if tag == "select":
        return "select"
    if role == "navigation" or tag == "nav":
        return "nav"
    return "other"


def _label_of(element, labels_by_for: dict[str, str]) -> str:
    """aria-label, then label[for=id], then the wrapping label's text."""
    aria = (element.get("aria-label") or "").strip()
    if aria:
        return aria
    element_id = element.get("id")
    if element_id and element_id in labels_by_for:
        return labels_by_for[element_id]
    for parent in element.parents:
        if getattr(parent, "name", None) == "label":
            own = parent.get_text(" ", strip=True)
            inner = element.get_text(" ", strip=True) or (element.get("value") or "")
            return own.replace(inner, "").strip()
    return ""


def _stable_selector(element, id_counts, attr_counts, name_counts) -> str:
    """The same selector scheme the Playwright walk generates."""
    element_id = element.get("id")
    if element_id and id_counts.get(element_id) == 1:
        return f"#{element_id}"
    for attr in _SELECTOR_ATTRS:
        value = element.get(attr)
        if value and attr_counts[attr].get(value) == 1:
            return f'[{attr}="{value}"]'
    if (
        element.name in ("input", "textarea", "select")
        and element.get("name")
        and name_counts.get(element.get("name")) == 1
    ):
        return f'{element.name}[name="{element.get("name")}"]'
    parts: list[str] = []
    node = element
    # Stop before body/html (full documents) or the soup root
    # ("[document]" — html.parser does not synthesize html/body for
    # fragments), exactly like the Playwright walk's BODY/HTML stop.
    while node is not None and getattr(node, "name", None) not in (
        None,
        "body",
        "html",
        "[document]",
    ):
        tag = node.name
        nth = 1
        for sibling in node.previous_siblings:
            if getattr(sibling, "name", None) == tag:
                nth += 1
        parts.insert(0, f"{tag}:nth-of-type({nth})")
        node = node.parent
    return " > ".join(parts)
