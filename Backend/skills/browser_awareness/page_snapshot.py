"""
skills/browser_awareness/page_snapshot.py

Pure snapshot construction — no browser, no automation imports.

The inspector gathers *raw* page facts (URL, title, visible text, raw
elements). This module turns them into a compact PageSnapshot:

    * caps the number of elements and the amount of page text,
    * drops hidden / inert elements,
    * builds the readable "PAGE ..." block that Hermes receives.

Keeping this pure means every cap, filter and render rule is unit-testable
without a browser, and no full HTML/DOM ever leaves this module.
"""

from __future__ import annotations

import re

from .schemas import ElementInfo, PageSnapshot

# Caps — keep the model payload small and fast (local CPU Ollama).
MAX_ELEMENTS = 40
MAX_TEXT_CHARS = 2500
MAX_TEXT_LINES = 60
MAX_ELEMENT_TEXT_CHARS = 80

# Credential-ish / sensitive values that must never be echoed to Hermes.
_SENSITIVE_NAME_HINTS = ("password", "passwd", "secret", "token", "apikey", "api_key", "pin")


def build_page_snapshot(
    url: str,
    title: str,
    page_text: str,
    raw_elements: list[dict],
    max_elements: int = MAX_ELEMENTS,
    max_text_chars: int = MAX_TEXT_CHARS,
) -> PageSnapshot:
    """Build a compact, sanitized PageSnapshot from raw page facts.

    Args:
        url / title: page identity.
        page_text: visible body text (already stripped of HTML).
        raw_elements: list of dicts from the inspector with keys
            kind, text, placeholder, label, name, href, selector,
            visible, enabled, value_hint.
    """
    text, text_truncated = _compact_text(page_text or "", max_text_chars)

    elements: list[ElementInfo] = []
    seen_selectors: set[str] = set()
    for index, raw in enumerate(raw_elements or []):
        if len(elements) >= max_elements:
            break
        element = _clean_element(index, raw, seen_selectors)
        if element is None:
            continue
        elements.append(element)

    return PageSnapshot(
        url=url or "",
        title=title or "",
        text=text,
        elements=elements,
        text_truncated=text_truncated,
        elements_truncated=len(raw_elements or []) > len(elements),
    )


def snapshot_for_hermes(snapshot: PageSnapshot) -> str:
    """Render a PageSnapshot as the compact text block sent to Hermes."""
    lines = [
        "PAGE",
        f"URL: {snapshot.url}",
        f"TITLE: {snapshot.title}",
        "TEXT:",
        snapshot.text or "(no visible text)",
    ]
    lines.append("")
    lines.append("INTERACTIVE ELEMENTS:")
    if not snapshot.elements:
        lines.append("(none found)")
    for element in snapshot.elements:
        bits = [f"[{element.kind}]", f"id={element.id}"]
        if element.text:
            bits.append(f'text="{element.text}"')
        if element.placeholder:
            bits.append(f'placeholder="{element.placeholder}"')
        if element.label:
            bits.append(f'label="{element.label}"')
        if element.name:
            bits.append(f"name={element.name}")
        if element.href:
            bits.append(f"href={element.href}")
        lines.append(" ".join(bits))
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _compact_text(text: str, max_chars: int) -> tuple[str, bool]:
    """Normalize whitespace and cap visible page text (keep it readable)."""
    compact = "\n".join(line.strip() for line in text.splitlines() if line.strip())
    truncated = len(compact) > max_chars
    if truncated:
        compact = compact[:max_chars].rstrip() + "\n…"
    # Collapse any remaining whitespace runs and trim to a sane line count.
    lines = [re.sub(r"\s+", " ", line)[:200].strip() for line in compact.splitlines()]
    lines = [line for line in lines if line][:MAX_TEXT_LINES]
    result = "\n".join(lines)
    return result, truncated or (len(compact.splitlines()) > MAX_TEXT_LINES)


def _clean_element(index: int, raw: dict, seen_selectors: set[str]) -> ElementInfo | None:
    """Validate one raw element dict and return an ElementInfo (or None)."""
    if not isinstance(raw, dict):
        return None
    kind = str(raw.get("kind") or "other")
    selector = str(raw.get("selector") or "").strip()
    visible = bool(raw.get("visible", True))
    enabled = bool(raw.get("enabled", True))

    # Hidden and inert elements never reach Hermes.
    if not visible or not enabled:
        return None
    if not selector:
        return None
    # De-duplicate selectors (same element listed twice).
    if selector in seen_selectors:
        return None
    seen_selectors.add(selector)

    text = _snippet(raw.get("text"))
    placeholder = _snippet(raw.get("placeholder"))
    label = _snippet(raw.get("label"))
    name = str(raw.get("name") or "").strip()

    # A password-looking field must never leak its *value* (raw values are
    # never collected anyway — this guards against a future addition).
    sensitive = any(hint in (name + label + placeholder).lower() for hint in _SENSITIVE_NAME_HINTS)
    if sensitive:
        text = ""
        placeholder = placeholder[:4] + "…" if placeholder else ""

    return ElementInfo(
        id=f"el_{index + 1}",
        kind=kind
        if kind in ("link", "button", "input", "textarea", "select", "checkbox", "radio", "nav")
        else "other",
        text=text,
        placeholder=placeholder,
        label=label,
        name=name,
        href=str(raw.get("href") or "").strip(),
        selector=selector,
        visible=True,
        enabled=True,
    )


def _snippet(value) -> str:
    """Short, single-line text for element labels (never raw HTML)."""
    if not value:
        return ""
    text = re.sub(r"<[^>]+>", "", str(value))
    text = re.sub(r"\s+", " ", text).strip()
    return text[:MAX_ELEMENT_TEXT_CHARS]
