"""
skills/browser_awareness/inspector.py

DOM inspection through a real (Playwright) browser page.

Playwright is imported lazily so this module — and the whole capability —
imports cleanly and stays unit-testable on machines without it.

The inspector runs one page-side script that walks the DOM for visible,
interactive elements, computes a stable CSS selector for each, and
returns *raw* facts. The compact, sanitized PageSnapshot is built by the
pure page_snapshot module. Raw HTML never leaves the page.
"""

from __future__ import annotations

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
