"""
ai_chain/browser_automation.py — DOM-aware browser automation (v1.7)

The reusable browser capability behind the AI chain and future Sarthi
chains. It replaces coordinate guessing ("click x=742, y=418 and hope")
with semantic element resolution:

    Live browser
        ↓ Selenium obtains page HTML (driver.page_source)
        ↓ BeautifulSoup parses/analyses the HTML (regex fallback without bs4)
        ↓ Element resolver scores candidates semantically
        ↓ Selenium locates the corresponding live element
        ↓ Click / type / copy / paste
        ↓ Verification

Key design points
-----------------
- **No screen-coordinate guessing for HTML element discovery.** Every
  element is found from the page structure (tag, id, aria-label, name,
  placeholder, title, role, associated label, visible text, data-*)
  through ``resolve_element``. PyAutoGUI is never imported here; it
  remains available to the laptop controller (``control.py``) only as a
  last-resort execution mechanism for genuinely non-DOM desktop UI.
- **BeautifulSoup first.** ``find_candidates`` parses the page HTML with
  BeautifulSoup when installed (primary) and falls back to a raw-HTML
  regex parser otherwise — the same convention ``dom.py`` uses, so the
  module works on machines without ``bs4``.
- **Fresh DOM on every action.** Each ``resolve_element`` call re-reads
  ``driver.page_source``; after navigation, clicks that mutate the page,
  modals, or SPA changes the next action re-inspects the current DOM
  instead of trusting a stale snapshot.
- **Every action is verified.** Copy: the value must be extracted from
  the DOM or land on the clipboard. Paste: the field must contain the
  value afterwards. Navigation: the new URL must be loaded.
- **Chain state.** ``ChainState`` carries ``clipboard``,
  ``extracted_values``, ``current_url`` and ``last_action`` between
  websites, so an extracted value from site A can be pasted into site B
  without depending on the physical clipboard.

Public API
----------
    resolve_element(driver, action, target) -> ResolvedElement
    BrowserAutomation(driver)                 — navigate / click / copy / paste
    run_browser_chain(steps, ...)             — declarative multi-site chains
    ChainState                                — explicit state between steps

Everything below is importable without Selenium or bs4 installed (both
are imported lazily), so the module is safe to import and unit-test
anywhere — the same convention as ``control.py`` and ``dom.py``.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

from utils.logger import get_logger

logger = get_logger(__name__)

# A candidate must beat this score to be selected. Weak matches (a
# generic element that merely shares a class or role word) fall below it
# and are rejected instead of being clicked blindly.
MIN_RESOLVE_SCORE = 40.0

# Bonus when a signal's value equals the whole target phrase.
PHRASE_BONUS = 15.0

# Longest text treated as an extractable "value" from the DOM.
MAX_EXTRACT_CHARS = 500

# Grammar/command words dropped from the target description. Content
# words like "copy", "button", "input" are KEPT — they are the signals.
_STOPWORDS = {
    "a",
    "an",
    "the",
    "and",
    "or",
    "of",
    "for",
    "to",
    "in",
    "on",
    "at",
    "with",
    "from",
    "by",
    "this",
    "that",
    "these",
    "those",
    "please",
    "find",
    "locate",
    "me",
    "my",
    "your",
    "its",
    "it",
    "is",
    "are",
    "was",
    "were",
    "be",
    "as",
    "do",
    "does",
    "into",
    "onto",
    "via",
    "then",
}

# Tags that never carry a UI affordance worth resolving.
_SKIP_TAGS = {"script", "style", "noscript", "template", "head", "title", "meta", "link"}

# HTML void elements (no closing tag) for the no-bs4 regex parser.
_VOID_TAGS = {
    "area",
    "base",
    "br",
    "col",
    "embed",
    "hr",
    "img",
    "input",
    "link",
    "meta",
    "param",
    "source",
    "track",
    "wbr",
}


# ----------------------------------------------------------------------
# Errors
# ----------------------------------------------------------------------


class ResolveError(RuntimeError):
    """No confident element matched the requested target."""


class AmbiguousElementError(ResolveError):
    """Multiple candidates scored equally; refusing to pick blindly."""


# ----------------------------------------------------------------------
# Data models
# ----------------------------------------------------------------------


@dataclass
class ChainState:
    """Explicit state carried between websites in a browser chain."""

    clipboard: str | None = None
    extracted_values: dict[str, str] = field(default_factory=dict)
    current_url: str | None = None
    last_action: str | None = None


@dataclass(frozen=True)
class TargetSpec:
    """A parsed target description: the significant tokens a user meant."""

    text: str
    keywords: tuple[str, ...]

    @property
    def phrase(self) -> str:
        return " ".join(self.keywords)


@dataclass
class ElementCandidate:
    """One element found in the page HTML, with its resolved score."""

    tag: str
    attrs: dict[str, str]
    text: str
    xpath: str
    index: int  # document order among candidates
    semantics: dict[str, Any] = field(default_factory=dict)
    score: float = 0.0
    reasons: list[str] = field(default_factory=list)
    matched: list[tuple[str, str]] = field(default_factory=list)

    def describe(self) -> str:
        """Selector-style description for logs: <button>[aria-label="Copy"]."""
        parts = [f"<{self.tag}>"]
        for label, value in self.matched[:2]:
            parts.append(f'[{label}="{value}"]')
        return "".join(parts)


@dataclass
class ResolvedElement:
    """The winning candidate plus its live Selenium element."""

    element: Any
    candidate: ElementCandidate
    locator: tuple[str, str]  # ("xpath", <expression>)
    candidates: list[ElementCandidate]
    reason: str = ""


@dataclass
class StepResult:
    """Outcome of one declarative chain step."""

    action: str
    ok: bool
    target: str = ""
    url: str = ""
    detail: str = ""
    error: str = ""


@dataclass
class ChainResult:
    """Outcome of a full multi-site browser chain."""

    success: bool
    steps: list[StepResult]
    state: ChainState
    message: str = ""


# ----------------------------------------------------------------------
# HTML parsing (BeautifulSoup primary, regex fallback)
# ----------------------------------------------------------------------


@lru_cache(maxsize=1)
def _bs4_available() -> bool:
    """Whether BeautifulSoup can be imported (cached — imports are slow)."""
    try:
        import bs4  # noqa: F401

        return True
    except ImportError:
        return False


@dataclass
class _ParsedElement:
    """Parser-neutral element: tag, attrs, text and a locator XPath."""

    tag: str
    attrs: dict[str, str]
    text: str
    xpath: str


def _norm(value: Any) -> str:
    """Lowercase, collapse whitespace (matching/normalisation helper)."""
    return " ".join(str(value or "").split()).lower()


def _norm_text(value: Any) -> str:
    """Collapse whitespace without lowercasing (display text)."""
    return " ".join(str(value or "").split())


def parse_target(text: str) -> TargetSpec:
    """Split a free-text target ("Copy button") into significant keywords."""
    raw = _norm(text)
    words = [w for w in raw.split() if len(w) >= 2 and w not in _STOPWORDS]
    return TargetSpec(text=raw, keywords=tuple(words))


def _parse_elements(html: str) -> tuple[list[_ParsedElement], dict[str, str]]:
    """(elements, label_map) — bs4 when installed, regex fallback otherwise."""
    if _bs4_available():
        return _parse_elements_bs4(html or "")
    return _parse_elements_regex(html or "")


def _parse_elements_bs4(html: str) -> tuple[list[_ParsedElement], dict[str, str]]:
    """BeautifulSoup parser: real HTML — nested tags, unquoted attrs, no
    false hits from markup-shaped strings inside inline scripts."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")

    label_map: dict[str, str] = {}
    for label in soup.find_all("label"):
        text = _norm_text(label.get_text(" ", strip=True))
        for_id = label.get("for")
        if for_id:
            label_map[str(for_id)] = text
        inner = label.find(["input", "textarea", "select"])
        if inner is not None and inner.get("id"):
            label_map.setdefault(str(inner["id"]), text)

    elements: list[_ParsedElement] = []
    for tag in soup.find_all(True):
        name = (tag.name or "").lower()
        if name in _SKIP_TAGS:
            continue
        attrs: dict[str, str] = {}
        for key, value in tag.attrs.items():
            if value is None:
                continue
            if isinstance(value, list):  # multi-valued attributes (class)
                value = " ".join(str(v) for v in value)
            attrs[str(key).lower()] = str(value).strip()
        elements.append(
            _ParsedElement(
                tag=name,
                attrs=attrs,
                text=_norm_text(tag.get_text(" ", strip=True)),
                xpath=_xpath_for(tag),
            )
        )
    return elements, label_map


def _parse_elements_regex(html: str) -> tuple[list[_ParsedElement], dict[str, str]]:
    """No-bs4 fallback: raw-HTML regex (the ``dom.py`` convention).

    Flat markup parses faithfully; deeply nested same-tag trees and
    markup-shaped strings inside scripts are best-effort only — which is
    exactly why BeautifulSoup is the primary parser.
    """
    label_map: dict[str, str] = {}
    for match in re.finditer(r"<label\b([^>]*)>(.*?)</label\s*>", html, re.DOTALL | re.IGNORECASE):
        label_attrs = _parse_attrs(match.group(1))
        body = re.sub(r"<[^>]+>", " ", match.group(2))
        for_id = label_attrs.get("for", "")
        if for_id:
            label_map[for_id] = _norm_text(body)

    elements: list[_ParsedElement] = []
    counts: dict[str, int] = {}
    pattern = re.compile(
        r"<(?P<tag>[a-zA-Z][\w-]*)(?P<attrs>[^<>]*)>"
        r"(?:(?P<body>.*?)</(?P=tag)\s*>)?",
        re.DOTALL | re.IGNORECASE,
    )
    for match in pattern.finditer(html):
        tag = match.group("tag").lower()
        if tag in _SKIP_TAGS:
            continue
        attrs = _parse_attrs(match.group("attrs"))
        body = match.group("body") or ""
        if tag in _VOID_TAGS or match.group("attrs").rstrip().endswith("/"):
            text = ""
        else:
            text = _norm_text(re.sub(r"<[^>]+>", " ", body))
        counts[tag] = counts.get(tag, 0) + 1
        elements.append(
            _ParsedElement(tag=tag, attrs=attrs, text=text, xpath=f"(//{tag})[{counts[tag]}]")
        )
    return elements, label_map


def _parse_attrs(raw: str) -> dict[str, str]:
    """Attribute list ``name="v" name='v' name=v`` -> {name: value}."""
    attrs: dict[str, str] = {}
    for match in re.finditer(r"""([\w:-]+)\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+))""", raw or ""):
        value = match.group(2)
        if value is None:
            value = match.group(3)
        if value is None:
            value = match.group(4) or ""
        attrs[match.group(1).lower()] = value
    return attrs


def _xpath_for(tag: Any) -> str:
    """Absolute XPath for a bs4 Tag, valid against the same snapshot:
    /html/body/div[2]/button[1]. The document root (name == "[document]")
    is not part of the path; same-tag siblings are always indexed so the
    path is unique."""
    parts: list[str] = []
    node = tag
    while node is not None and getattr(node, "name", None) and node.name != "[document]":
        parent = node.parent
        name = node.name
        if parent is not None:
            siblings = [c for c in parent.children if getattr(c, "name", None) == name]
            index = siblings.index(node) + 1 if siblings else 1
        else:
            index = 1
        parts.append(f"{name}[{index}]")
        node = parent
    return "/" + "/".join(reversed(parts))


# ----------------------------------------------------------------------
# Candidate extraction + scoring (pure, unit-testable)
# ----------------------------------------------------------------------


def _is_hidden_element(el: _ParsedElement) -> bool:
    if el.attrs.get("hidden") is not None:
        return True
    if _norm(el.attrs.get("aria-hidden")) in ("true", "1"):
        return True
    if el.tag == "input" and _norm(el.attrs.get("type")) == "hidden":
        return True
    style = _norm(el.attrs.get("style"))
    if re.search(r"display\s*:\s*none", style) or re.search(r"visibility\s*:\s*hidden", style):
        return True
    return False


def _is_clickable_element(el: _ParsedElement) -> bool:
    if el.tag in ("button", "a", "summary", "select"):
        return True
    if el.tag == "input" and _norm(el.attrs.get("type")) not in ("hidden",):
        return True
    if _norm(el.attrs.get("role")) in ("button", "link", "menuitem", "tab"):
        return True
    if "onclick" in el.attrs:
        return True
    if _norm(el.attrs.get("contenteditable")) == "true":
        return True
    return False


def _is_typeable_element(el: _ParsedElement) -> bool:
    if el.tag in ("input", "textarea"):
        return True
    if _norm(el.attrs.get("contenteditable")) == "true":
        return True
    if "textbox" in _norm(el.attrs.get("role")):
        return True
    return False


def _is_value_bearing_element(el: _ParsedElement) -> bool:
    if el.tag in ("input", "textarea", "select"):
        return True
    if el.tag in ("code", "pre", "output"):
        return True
    if any(k.startswith("data-") and str(v).strip() for k, v in el.attrs.items()):
        return True
    if el.attrs.get("value", "").strip():
        return True
    return False


def find_candidates(html: str, action: str, target: str | TargetSpec) -> list[ElementCandidate]:
    """All candidate elements for ``action`` in the page HTML.

    ``action`` is one of ``"click"`` (or ``"copy"``), ``"type"`` (or
    ``"paste"``) or ``"value"`` — it decides which elements are
    eligible. Candidates are in document order; scoring happens in
    ``score_candidates``.
    """
    elements, label_map = _parse_elements(html)
    candidates: list[ElementCandidate] = []
    for element in elements:
        if _is_hidden_element(element):
            continue
        if action in ("click", "copy") and not _is_clickable_element(element):
            continue
        if action in ("type", "paste") and not _is_typeable_element(element):
            continue
        if action == "value" and not _is_value_bearing_element(element):
            continue
        candidates.append(_build_candidate(element, label_map, len(candidates) + 1))
    return candidates


def _build_candidate(el: _ParsedElement, label_map: dict[str, str], index: int) -> ElementCandidate:
    semantics: dict[str, Any] = {
        "tag": el.tag,
        "id": el.attrs.get("id", ""),
        "name": el.attrs.get("name", ""),
        "aria_label": el.attrs.get("aria-label", ""),
        "title": el.attrs.get("title", ""),
        "placeholder": el.attrs.get("placeholder", ""),
        "role": el.attrs.get("role", ""),
        "type": el.attrs.get("type", ""),
        "value": el.attrs.get("value", ""),
        "contenteditable": el.attrs.get("contenteditable", ""),
        "class": el.attrs.get("class", ""),
        "data_attrs": {k: v for k, v in el.attrs.items() if k.startswith("data-")},
        "associated_label": label_map.get(el.attrs.get("id", ""), ""),
        "text": el.text,
    }
    return ElementCandidate(
        tag=el.tag,
        attrs=el.attrs,
        text=el.text,
        xpath=el.xpath,
        index=index,
        semantics=semantics,
    )


def score_candidates(
    candidates: list[ElementCandidate], target: str | TargetSpec, action: str
) -> list[ElementCandidate]:
    """Score every candidate and return them best-first.

    Signals are weighted by the documented priority: exact id, stable
    attributes, aria-label, name, data-*, role, associated label, exact
    visible text, partial visible text, placeholder/title, class. Exact
    matches beat loose ones; ties keep document order.
    """
    spec = parse_target(target) if isinstance(target, str) else target
    for candidate in candidates:
        _score_one(candidate, spec, action)
    return sorted(candidates, key=lambda c: (-c.score, c.index))


def _match(value: str, spec: TargetSpec) -> tuple[bool, int]:
    """(exact phrase match, count of keyword hits) for one signal value."""
    v = _norm(value)
    if not v:
        return False, 0
    exact = v == spec.phrase
    hits = sum(1 for keyword in spec.keywords if keyword and keyword in v)
    return exact, hits


def _score_one(c: ElementCandidate, spec: TargetSpec, action: str) -> None:
    score = 0.0
    reasons: list[str] = []
    matched: list[tuple[str, str]] = []
    s = c.semantics

    def add(label: str, attr_value: Any, exact_weight: float, contains_weight: float) -> None:
        nonlocal score
        exact, hits = _match(attr_value, spec)
        if exact:
            score += exact_weight + PHRASE_BONUS
            reasons.append(f"{label} exact")
            matched.append((label, _norm_text(attr_value)))
        elif hits:
            score += contains_weight * hits
            reasons.append(f"{label} contains {hits} keyword(s)")
            matched.append((label, _norm_text(attr_value)))

    add("id", s["id"], 100, 45)
    add("name", s["name"], 80, 35)
    add("aria-label", s["aria_label"], 90, 40)
    for key, value in s["data_attrs"].items():
        add(f"data-{key}", value, 70, 30)
    add("role", s["role"], 25, 10)
    add("associated label", s["associated_label"], 75, 30)
    add("title", s["title"], 60, 25)
    add("placeholder", s["placeholder"], 85, 32)
    add("visible text", s["text"], 95, 38)
    add("class", s["class"], 15, 6)
    add("type", s["type"], 20, 8)

    # The target literally names the element type ("textarea").
    if s["tag"] in spec.keywords:
        score += 50
        reasons.append(f"tag <{s['tag']}> named in target")
    # The target asks for a contenteditable element.
    if "contenteditable" in spec.keywords and (
        _norm(s["contenteditable"]) == "true" or "contenteditable" in c.attrs
    ):
        score += 50
        reasons.append("contenteditable element")

    # Action fit bonuses.
    if action in ("click", "copy"):
        if s["tag"] in ("button", "a") or s["role"] in ("button", "link"):
            score += 12
            reasons.append("clickable element")
    elif action in ("type", "paste"):
        if (
            s["tag"] in ("input", "textarea")
            or _norm(s["contenteditable"]) == "true"
            or "textbox" in s["role"]
        ):
            score += 12
            reasons.append("typeable element")

    c.score = score
    c.reasons = reasons
    c.matched = matched


def to_locator(candidate: ElementCandidate) -> tuple[str, str]:
    """A Selenium-compatible locator for the live element.

    A unique id wins (stable against DOM shifts); otherwise the exact
    XPath computed from the snapshot is used — unique by construction.
    """
    element_id = candidate.semantics.get("id", "")
    if element_id and '"' not in element_id and "'" not in element_id:
        return ("xpath", f'//*[@id="{element_id}"]')
    return ("xpath", candidate.xpath)


# ----------------------------------------------------------------------
# Resolver (driver-aware)
# ----------------------------------------------------------------------


def _page_source(driver: Any) -> str:
    try:
        return driver.page_source or ""
    except Exception as exc:  # pragma: no cover - live browser
        logger.warning(f"[BROWSER] Could not read page_source: {exc}")
        return ""


def _current_url(driver: Any) -> str:
    try:
        return driver.current_url or ""
    except Exception:  # pragma: no cover - live browser
        return ""


def _find_live(driver: Any, locator: tuple[str, str]):
    try:
        return driver.find_element(*locator)
    except Exception:
        return None


def _log_failure(
    target: str, action: str, ranked: list[ElementCandidate], html: str, driver: Any
) -> None:
    """Log everything an operator needs when resolution fails."""
    logger.warning(
        "[BROWSER] Resolution failed: target=%r action=%s url=%s "
        "candidates=%d selectors_attempted=%s dom_head=%r",
        target,
        action,
        _current_url(driver),
        len(ranked),
        [c.describe() for c in ranked[:5]],
        (html or "")[:300],
    )


def resolve_element(
    driver: Any,
    action: str = "click",
    target: str = "copy button",
    *,
    strict: bool = True,
    html: str | None = None,
    _retried: bool = False,
) -> ResolvedElement:
    """Resolve ``target`` on the CURRENT page and return the live element.

    Pipeline: read ``driver.page_source`` → parse with BeautifulSoup
    (regex fallback) → score candidates by semantic relevance → pick the
    strongest → produce a Selenium XPath → verify the live element
    exists → return it. Raises ``ResolveError`` (or
    ``AmbiguousElementError`` when ``strict``) instead of guessing.

    Args:
        driver: a Selenium webdriver (or duck-typed stand-in).
        action: "click"/"copy", "type"/"paste", or "value".
        target: free-text description ("Copy button", "input for username").
        strict: reject equal-scoring ties instead of picking the first.
        html: inspect this HTML instead of the live page (tests).
    """
    spec = parse_target(target)
    source = html if html is not None else _page_source(driver)
    logger.info(f"[BROWSER] Resolving target: {target!r} (action={action})")

    if not (source or "").strip():
        raise ResolveError(f"[BROWSER] Page has no HTML to inspect (url={_current_url(driver)!r})")

    candidates = find_candidates(source, action, spec)
    ranked = score_candidates(candidates, spec, action)
    logger.info(f"[BROWSER] Candidates found: {len(ranked)}")

    if not ranked or ranked[0].score < MIN_RESOLVE_SCORE:
        _log_failure(target, action, ranked, source, driver)
        raise ResolveError(
            f"[BROWSER] No confident match for {target!r} (action={action}) "
            "on the current page — see the log for candidates and DOM info."
        )

    winner = ranked[0]
    if strict and len(ranked) > 1 and ranked[1].score == winner.score:
        raise AmbiguousElementError(
            f"[BROWSER] Ambiguous match for {target!r}: "
            f"{winner.describe()} and {ranked[1].describe()} score equally "
            f"({winner.score:.0f}) — refusing to pick blindly."
        )

    locator = to_locator(winner)
    element = _find_live(driver, locator)
    if element is None and html is None and not _retried:
        # The page may have changed between the snapshot and the lookup
        # (AJAX/SPA/modal) — re-inspect the live DOM once.
        logger.info("[BROWSER] Live element not found — DOM may have changed; re-snapshotting")
        return resolve_element(driver, action, target, strict=strict, _retried=True)
    if element is None:
        raise ResolveError(
            f"[BROWSER] Resolved {winner.describe()} in the HTML but no live "
            f"element matched {locator[1]!r} — the page changed between reads."
        )

    logger.info(
        f"[BROWSER] Selected: {winner.describe()} (score {winner.score:.0f}, locator {locator[1]})"
    )
    return ResolvedElement(
        element=element,
        candidate=winner,
        locator=locator,
        candidates=ranked,
        reason="; ".join(winner.reasons),
    )


# ----------------------------------------------------------------------
# BrowserAutomation — verified high-level actions
# ----------------------------------------------------------------------


_READ_CLIPBOARD_JS = """
const done = arguments[arguments.length - 1];
if (navigator.clipboard && navigator.clipboard.readText) {
  navigator.clipboard.readText().then(t => done(t)).catch(() => done(null));
} else {
  done(null);
}
"""

_JS_SET_VALUE = """
const el = arguments[0]; const value = arguments[1];
if (el.tagName === 'TEXTAREA' || el.tagName === 'INPUT') {
  el.value = value;
  el.dispatchEvent(new Event('input', {bubbles: true}));
  el.dispatchEvent(new Event('change', {bubbles: true}));
  return el.value;
}
el.focus();
document.execCommand('selectAll', false, null);
document.execCommand('insertText', false, value);
return el.innerText || el.textContent || '';
"""


class BrowserAutomation:
    """High-level, verified browser actions over a Selenium driver.

    Every action resolves its target from the live DOM, performs the
    interaction through Selenium (never screen coordinates), and
    verifies the result before reporting success. Chain state
    (``ChainState``) is maintained so values can flow between websites.
    """

    def __init__(self, driver: Any, state: ChainState | None = None, owns_driver: bool = False):
        self.driver = driver
        self.state = state or ChainState()
        self.owns_driver = owns_driver

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

    def navigate(self, url: str, wait: float = 1.0) -> str:
        """Load ``url``, wait for the DOM, verify the new URL, log it."""
        logger.info(f"[BROWSER] Loading {url}")
        try:
            self.driver.get(url)
        except Exception as exc:
            raise RuntimeError(f"[BROWSER] Navigation to {url} failed: {exc}") from exc
        if wait and wait > 0:
            time.sleep(wait)
        ready = self.wait_ready()
        self.state.current_url = _current_url(self.driver)
        self.state.last_action = "navigate"
        logger.info(f"[BROWSER] DOM loaded — {self.state.current_url}")
        if not self.state.current_url:
            raise RuntimeError(
                f"[BROWSER] Navigation not verified: no URL after loading {url} "
                f"(readyState={'complete' if ready else 'not complete'})"
            )
        return self.state.current_url

    def wait_ready(self, timeout: float = 15.0) -> bool:
        """Wait until ``document.readyState == 'complete'`` (best effort)."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                if self.driver.execute_script("return document.readyState") == "complete":
                    return True
            except Exception:
                pass
            time.sleep(0.2)
        logger.warning("[BROWSER] Page did not reach readyState=complete in time")
        return False

    # ------------------------------------------------------------------
    # Resolution + generic actions
    # ------------------------------------------------------------------

    def resolve(self, action: str, target: str, **kwargs: Any) -> ResolvedElement:
        """Resolve ``target`` on the current live DOM."""
        return resolve_element(self.driver, action, target, **kwargs)

    def click(self, target: str, expected=None) -> ResolvedElement:
        """Resolve and click ``target``; optionally verify an expected state.

        ``expected`` is a zero-arg callable returning a truthy value once
        the click took effect (checked for up to 5s). Default verification
        is the element's existence (the resolver guarantees it).
        """
        resolved = self.resolve("click", target)
        logger.info(f"[BROWSER] Clicking element: {resolved.locator[1]}")
        resolved.element.click()
        self.state.last_action = "click"
        if expected is not None:
            ok = self._wait_for(expected, timeout=5.0)
            if not ok:
                raise RuntimeError(
                    f"[BROWSER] Click on {target!r} not verified — expected state never appeared"
                )
            logger.info("[BROWSER] Click operation verified")
        return resolved

    # ------------------------------------------------------------------
    # Copy (DOM extraction first, clipboard workflow supported)
    # ------------------------------------------------------------------

    def copy(self, target: str, key: str | None = None, use_clipboard: bool = False) -> str:
        """Copy/extract a value from the current page into chain state.

        Prefers extracting the value directly from the DOM (the site
        exposes it — no clipboard needed). When the user explicitly asks
        for a clipboard copy, or no DOM value exists, resolves the Copy
        button semantically, clicks it, and reads the clipboard. The
        result is verified non-empty before it is stored.
        """
        logger.info(f"[BROWSER] Copy request: {target!r}")
        value = ""
        if not use_clipboard:
            value = self.extract_value(target)
            if value:
                logger.info("[BROWSER] Value extracted directly from DOM — clipboard not needed")
        if not value:
            try:
                resolved = self.resolve("click", target)  # the semantic Copy button
            except ResolveError as exc:
                raise RuntimeError(
                    f"[BROWSER] Copy not verified for {target!r}: no Copy button or "
                    "value found on the page."
                ) from exc
            logger.info(f"[BROWSER] Clicking element: {resolved.locator[1]}")
            resolved.element.click()
            value = self.read_clipboard()
            if not value:
                # Some UIs render the copied value after the click — the
                # DOM changed, so re-inspect instead of giving up.
                logger.info("[BROWSER] Clipboard empty after click — re-snapshotting the DOM")
                value = self.extract_value(target)
        if not value:
            raise RuntimeError(
                f"[BROWSER] Copy not verified for {target!r}: the clipboard is empty "
                "and no value was found in the DOM."
            )
        self._store(value, key)
        logger.info("[BROWSER] Copy operation verified — stored value in chain state")
        return value

    def extract_value(self, target: str) -> str:
        """Best-effort DOM value extraction for ``target`` ("" when none)."""
        try:
            resolved = self.resolve("value", target, strict=False)
        except ResolveError:
            return ""
        return self._element_value(resolved.element)

    # ------------------------------------------------------------------
    # Paste (semantic target, verified result)
    # ------------------------------------------------------------------

    def paste(self, target: str, value: str) -> bool:
        """Type/paste ``value`` into the element matching ``target``.

        Resolves the input/textarea/contenteditable semantically, focuses
        it, clears it, inserts the value and verifies the field now
        contains it. On verification failure a JS insertion (input event)
        is retried before failing.
        """
        value = (value or "").strip()
        if not value:
            raise RuntimeError("[BROWSER] Paste aborted: no value to paste")
        resolved = self.resolve("type", target)
        element = resolved.element
        logger.info(f"[BROWSER] Pasting {len(value)} chars into {resolved.locator[1]}")
        self._focus(element)
        self._clear(element)
        self._insert(element, value)
        if not self._verify_field(element, value):
            logger.info("[BROWSER] Paste verification failed — retrying with JS insertion")
            self._insert_js(element, value)
        if not self._verify_field(element, value):
            raise RuntimeError(
                f"[BROWSER] Paste not verified into {target!r}: the field does not "
                "contain the pasted value."
            )
        self.state.last_action = "paste"
        logger.info("[BROWSER] Paste operation verified")
        return True

    # ------------------------------------------------------------------
    # Clipboard
    # ------------------------------------------------------------------

    def read_clipboard(self) -> str:
        """Read the browser clipboard (best effort — may return "")."""
        try:
            result = self.driver.execute_async_script(_READ_CLIPBOARD_JS)
        except Exception as exc:  # pragma: no cover - live browser
            logger.warning(f"[BROWSER] Clipboard read failed: {exc}")
            return ""
        value = (result or "").strip()
        if value:
            logger.info(f"[BROWSER] Clipboard read: {len(value)} chars")
        else:
            logger.info("[BROWSER] Clipboard read returned empty")
        return value

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _store(self, value: str, key: str | None) -> None:
        self.state.clipboard = value
        if key:
            self.state.extracted_values[key] = value
        self.state.last_action = "copy"

    def _element_value(self, element: Any) -> str:
        """The value an element carries (input value, data attr, short text)."""
        try:
            tag = (getattr(element, "tag_name", "") or "").lower()
            if tag in ("input", "textarea", "select"):
                raw = element.get_attribute("value")
                if raw is not None and str(raw).strip():
                    return str(raw).strip()
            for attr in ("data-value", "value"):
                raw = element.get_attribute(attr)
                if raw and str(raw).strip():
                    return str(raw).strip()
            text = getattr(element, "text", None) or ""
            if text.strip() and len(text.strip()) <= MAX_EXTRACT_CHARS:
                return text.strip()
        except Exception:
            pass
        return ""

    def _focus(self, element: Any) -> None:
        try:
            element.click()
        except Exception:
            pass

    def _clear(self, element: Any) -> None:
        try:
            tag = (getattr(element, "tag_name", "") or "").lower()
            if tag in ("input", "textarea"):
                element.clear()
            else:
                from selenium.webdriver.common.keys import Keys

                element.send_keys(Keys.CONTROL, "a")
                element.send_keys(Keys.DELETE)
        except Exception:
            pass

    def _insert(self, element: Any, value: str) -> None:
        element.send_keys(value)

    def _insert_js(self, element: Any, value: str) -> Any:
        try:
            return self.driver.execute_script(_JS_SET_VALUE, element, value)
        except Exception as exc:  # pragma: no cover - live browser
            logger.warning(f"[BROWSER] JS insertion failed: {exc}")
            return None

    def _field_content(self, element: Any) -> str:
        try:
            tag = (getattr(element, "tag_name", "") or "").lower()
            if tag in ("input", "textarea", "select"):
                raw = element.get_attribute("value")
                if raw is not None:
                    return str(raw)
            return getattr(element, "text", "") or ""
        except Exception:
            return ""

    def _verify_field(self, element: Any, value: str) -> bool:
        current = self._field_content(element)
        return bool(current) and value in current

    def _wait_for(self, condition, timeout: float) -> bool:
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                if condition():
                    return True
            except Exception:
                pass
            time.sleep(0.2)
        return False

    def close(self) -> None:
        """Release the driver. An attached automation Chrome is never quit."""
        if self.owns_driver:
            try:
                self.driver.quit()
            except Exception:  # pragma: no cover - live browser
                pass
        self.state.last_action = "close"


# ----------------------------------------------------------------------
# Driver acquisition
# ----------------------------------------------------------------------


def create_driver(attach: bool = True) -> tuple[Any, bool]:
    """A Selenium driver plus whether this process owns it.

    ``attach=True`` (default) attaches to the already-running automation
    Chrome via ``debuggerAddress`` — the robot's persistent-profile
    browser launched by ``control.py`` — and the caller does NOT own it
    (closing must never kill the browser the AI chain depends on). When
    the attach fails (no debug port), a fresh Chrome is launched via
    Selenium Manager as a fallback, and the caller owns that one.
    """
    from selenium import webdriver

    if attach:
        try:
            from .dom import cdp_url
            from .selenium_dom import debugger_address

            options = webdriver.ChromeOptions()
            options.add_experimental_option("debuggerAddress", debugger_address(cdp_url()))
            driver = webdriver.Chrome(options=options)
            logger.info(f"[BROWSER] attached to automation Chrome at {cdp_url()}")
            return driver, False
        except Exception as exc:
            logger.warning(
                f"[BROWSER] attach to the automation Chrome failed ({exc}) — launching a fresh one"
            )
    logger.info("[BROWSER] launching a fresh Chrome (Selenium Manager)")
    return webdriver.Chrome(), True


# ----------------------------------------------------------------------
# Chain executor
# ----------------------------------------------------------------------


def _resolve_value(value: Any, state: ChainState) -> str:
    """Step ``value`` -> text: literal, ``$key`` (chain state), or clipboard."""
    if isinstance(value, str):
        text = value.strip()
        if text.startswith("$"):
            key = text[1:]
            return state.extracted_values.get(key) or state.clipboard or ""
        return text
    return state.clipboard or ""


def run_browser_chain(
    steps: list[dict[str, Any]],
    automation: BrowserAutomation | None = None,
    driver: Any = None,
    *,
    close: bool = True,
) -> ChainResult:
    """Execute a declarative multi-site browser chain with explicit state.

    ``steps`` is a list of dicts; supported actions:

        {"action": "open", "url": "https://a.example.com", "wait": 1.0}
        {"action": "copy", "target": "Copy", "key": "value"}   # DOM-first, clipboard fallback
        {"action": "copy", "target": "Copy", "key": "value", "use_clipboard": true}
        {"action": "paste", "target": "Paste value here", "value": "$value"}  # $key from state
        {"action": "click", "target": "..."}

    Values extracted by ``copy`` are stored in ``ChainState`` (under
    ``key`` and ``clipboard``) so the next website's ``paste`` can use
    ``"$key"`` without touching the physical clipboard. The chain stops
    at the first failed step; the partial state and per-step results are
    returned in ``ChainResult``.

    Pass ``automation`` or ``driver`` to drive an existing session;
    otherwise one is created (attaching to the automation Chrome). All
    browser interaction goes through the DOM resolver — no coordinate
    guessing.
    """
    owned = automation is None
    if automation is None:
        if driver is not None:
            automation = BrowserAutomation(driver)
        else:
            driver, owns = create_driver()
            automation = BrowserAutomation(driver, owns_driver=owns)

    results: list[StepResult] = []
    try:
        for step in steps:
            action = (step.get("action") or "").lower()
            if action in ("open", "navigate"):
                url = str(step.get("url", ""))
                if not url:
                    results.append(StepResult(action, ok=False, error="missing url"))
                    break
                try:
                    automation.navigate(url, float(step.get("wait", 1.0)))
                    results.append(StepResult(action, ok=True, url=url, detail=f"loaded {url}"))
                except Exception as exc:
                    results.append(StepResult(action, ok=False, url=url, error=str(exc)))
                    break
            elif action in ("copy", "extract"):
                target = str(step.get("target", "Copy"))
                key = step.get("key")
                try:
                    value = automation.copy(
                        target, key=key, use_clipboard=bool(step.get("use_clipboard", False))
                    )
                    results.append(
                        StepResult(
                            action, ok=True, target=target, detail=f"copied {len(value)} chars"
                        )
                    )
                except Exception as exc:
                    results.append(StepResult(action, ok=False, target=target, error=str(exc)))
                    break
            elif action in ("paste", "type"):
                target = str(step.get("target", ""))
                value = _resolve_value(step.get("value"), automation.state)
                try:
                    automation.paste(target, value)
                    results.append(
                        StepResult(
                            action, ok=True, target=target, detail=f"pasted {len(value)} chars"
                        )
                    )
                except Exception as exc:
                    results.append(StepResult(action, ok=False, target=target, error=str(exc)))
                    break
            elif action == "click":
                target = str(step.get("target", ""))
                try:
                    automation.click(target)
                    results.append(StepResult(action, ok=True, target=target, detail="clicked"))
                except Exception as exc:
                    results.append(StepResult(action, ok=False, target=target, error=str(exc)))
                    break
            else:
                results.append(StepResult(action, ok=False, error=f"unknown action {action!r}"))
                break
    finally:
        if owned and close:
            automation.close()

    success = all(r.ok for r in results)
    message = (
        "Browser chain completed."
        if success
        else (
            f"Browser chain stopped at step {len(results)}: "
            f"{results[-1].action} — {results[-1].error}"
        )
    )
    logger.info(f"[BROWSER] {message}")
    return ChainResult(success=success, steps=results, state=automation.state, message=message)
