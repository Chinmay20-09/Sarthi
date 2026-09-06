"""
ai_chain/registry.py

Browser-awareness registry: per-site knowledge of *actions* the robot can
perform on an AI website — today: how to copy the assistant's reply.

Why this exists
---------------
The old way of reading a reply is Ctrl+A / Ctrl+C on the whole page and
then extracting the text after the sent prompt. That grabs the entire
website (menus, sidebars, buttons) on every poll — many redundant
whole-page copies per run — and the extraction only works because the
prompt happens to be on the page.

Modern AI UIs (ChatGPT, Gemini, ...) put a small **Copy** button on every
assistant message that puts exactly that message on the clipboard. The
registry records, per site, how to use that affordance:

    {"method": "button", "label": "Copy", "point": [0.88, 0.87]}

- ``label`` is the *semantic* identifier of the affordance ("Copy") —
  what a future vision/OCR locator would search for, and what a human
  reading the registry expects to see.
- ``point`` is the *current* locator: the window-fraction click point of
  that button, because the coordinate-based robot has no OCR. Defaults
  are estimates (like every other point in this module); recording the
  real spot with calibrate.py makes the copy reliable.

Like ``calibration.py``, the registry ships built-in defaults, lets the
user override anything through the same git-ignored ``calibration.json``
(``actions`` section, plus ``sites.<key>.copy_point`` recorded by
``calibrate.py``), and honours ``AI_CHAIN_*`` environment variables.
When a site has no registered button copy, the driver falls back to the
Ctrl+A/Ctrl+C page copy, so nothing breaks for unregistered sites.

The registry is pure data + resolution — no automation imports, safe to
unit-test anywhere.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from .calibration import _load_calibration

# Default window-fraction click point for the Copy button of the last
# assistant message. Both sites put it at the bottom-right of the newest
# message, just above the composer. These are ESTIMATES — record the
# exact spot per monitor with:
#   python -m skills.automation_engine.ai_chain.calibrate \
#       --site chatgpt --point copy_point --record
DEFAULT_COPY_POINTS: dict[str, tuple[float, float]] = {
    "chatgpt": (0.88, 0.87),
    "gemini": (0.86, 0.85),
    "claude": (0.87, 0.87),
    "perplexity": (0.85, 0.86),
    "grok": (0.87, 0.86),
    "deepseek": (0.87, 0.87),
    "copilot": (0.86, 0.86),
}

# Fallback scan region (window fractions: x0, y0, x1, y1) around the last
# assistant message. When the registered point misses, the driver clicks a
# small grid inside this box — the Copy button lives at the bottom-right
# of the newest message, so the region spans the right side of the chat,
# from just above the composer upward over typical message heights.
DEFAULT_SCAN_REGIONS: dict[str, tuple[float, float, float, float]] = {
    "chatgpt": (0.60, 0.72, 0.96, 0.92),
    "gemini": (0.60, 0.73, 0.96, 0.93),
    "claude": (0.60, 0.72, 0.96, 0.92),
    "perplexity": (0.60, 0.72, 0.96, 0.92),
    "grok": (0.60, 0.72, 0.96, 0.92),
    "deepseek": (0.60, 0.72, 0.96, 0.92),
    "copilot": (0.60, 0.72, 0.96, 0.92),
}

# Total button-click attempts (registered point + scan candidates) before
# the driver gives up and falls back to the Ctrl+A/Ctrl+C page copy.
DEFAULT_COPY_RETRIES = 9  # 1 registered point + an 4x2 scan grid

# Grid density for the scan (columns x rows inside the scan region).
SCAN_STEPS_X = 4
SCAN_STEPS_Y = 2


@dataclass(frozen=True)
class CopyAffordance:
    """How to copy the assistant's reply on one site.

    Attributes:
        method: "button" (click the message's Copy button) or "keyboard"
            (Ctrl+A/Ctrl+C page copy). Anything other than "button"
            means the driver uses the keyboard fallback.
        label: Semantic label of the button ("Copy", "Copy response",
            localized text, ...). Not yet searched visually — it names
            the affordance for humans and for future vision locators.
        point: Window-fraction (fx, fy) of the button, or None to
            auto-estimate from the composer position.
        scan_region: Window-fraction box (x0, y0, x1, y1) to scan for
            the button when ``point`` misses, or None to derive a box
            around the point.
        retries: Total button-click attempts (point + scan candidates)
            before falling back to the page copy.
    """

    method: str = "button"
    label: str = "Copy"
    point: tuple[float, float] | None = None
    scan_region: tuple[float, float, float, float] | None = None
    retries: int = DEFAULT_COPY_RETRIES

    @property
    def uses_button(self) -> bool:
        return self.method == "button"


@dataclass(frozen=True)
class SiteActions:
    """All registered actions for one AI website."""

    key: str
    copy: CopyAffordance


_COPY_SITE_KEYS = sorted(set(DEFAULT_COPY_POINTS) | set(DEFAULT_SCAN_REGIONS))


# Built-in registry: every site the driver knows how to operate, and how
# to copy a reply on it. A site absent here simply uses the keyboard
# fallback (Ctrl+A/Ctrl+C of the page).
DEFAULT_ACTIONS: dict[str, SiteActions] = {
    key: SiteActions(
        key=key,
        copy=CopyAffordance(
            method="button",
            label="Copy",
            point=DEFAULT_COPY_POINTS.get(key) or (0.88, 0.87),
            scan_region=DEFAULT_SCAN_REGIONS.get(key),
        ),
    )
    for key in _COPY_SITE_KEYS
}

_ACTIONS_CACHE: dict[str, SiteActions] | None = None


def get_actions(site_key: str) -> SiteActions:
    """Return a site's actions with calibration + env overrides applied.

    Unknown sites return a keyboard-copy SiteActions (safe default) so
    callers never have to special-case missing registry entries.
    """
    global _ACTIONS_CACHE
    if _ACTIONS_CACHE is not None:
        return _ACTIONS_CACHE.get(site_key, _keyboard_only(site_key))

    cache: dict[str, SiteActions] = {}
    cal = _load_calibration()
    action_overrides: dict = cal.get("actions", {}) or {}

    for key, actions in DEFAULT_ACTIONS.items():
        cache[key] = SiteActions(key=key, copy=_resolve_copy(key, actions.copy, action_overrides))

    # Sites that exist in the calibration but not in the built-in
    # catalogue still get their recorded actions honoured.
    for key, values in action_overrides.items():
        if key not in cache:
            cache[key] = SiteActions(
                key=key, copy=_resolve_copy(key, CopyAffordance(), {key: values})
            )

    _ACTIONS_CACHE = cache
    return cache.get(site_key, _keyboard_only(site_key))


def uses_button_copy(site_key: str) -> bool:
    """True when the site has a registered Copy button the driver may click."""
    return get_actions(site_key).copy.uses_button


def get_copy_point(site_key: str) -> tuple[float, float] | None:
    """Window-fraction point of the site's Copy button (None = estimate later)."""
    return get_actions(site_key).copy.point


def copy_retries(site_key: str) -> int:
    """Total button-click attempts before the driver falls back to page copy."""
    return get_actions(site_key).copy.retries


def get_scan_region(site_key: str) -> tuple[float, float, float, float] | None:
    """Window-fraction box to scan for the Copy button (None = derive)."""
    return get_actions(site_key).copy.scan_region


def copy_scan_candidates(site_key: str) -> list[tuple[float, float]]:
    """Ordered Copy-button click candidates for a site (window fractions).

    The registered point comes first, then a grid across the scan region
    sorted by distance from it — nearest cells tried first. The grid is
    limited by the affordance's ``retries`` budget, so an uncalibrated
    point degrades to a short scan instead of the whole-page copy.
    Returns [] for sites without a registered Copy button.
    """
    actions = get_actions(site_key)
    copy = actions.copy
    if not copy.uses_button:
        return []

    point = copy.point
    region = copy.scan_region or _region_around(point)
    candidates = []
    if point is not None:
        candidates.append(point)

    if region is not None:
        x0, y0, x1, y1 = _clamp_region(region)
        cells = [
            (x, y) for y in _linspace(y0, y1, SCAN_STEPS_Y) for x in _linspace(x0, x1, SCAN_STEPS_X)
        ]
        # Nearest cells first (the button sits near the recorded spot).
        cells.sort(key=lambda c: _dist(c, point) if point is not None else 0.0)
        candidates.extend(cells)

    budget = max(1, copy.retries)
    return candidates[:budget]


@dataclass(frozen=True)
class DomMatcher:
    """One regex rule that finds an affordance in the page HTML (v1.5).

    Unlike the coordinate-based ``CopyAffordance`` above (click a point,
    verify by clipboard), a DOM matcher describes *what to look for in
    the markup*: an element whose tag is ``tag`` ('' = any tag) carrying
    attribute ``attribute`` ('' = any) whose value matches
    ``value_pattern`` (regex, case-insensitive).

    Attributes:
        action: "copy" | "composer" | "download" — what the affordance
            does, so the driver knows which matcher list to consult.
        tag: Element tag to restrict the search to ("button", "textarea",
            "div", ...). Empty string searches every element.
        attribute: Attribute name whose value is regex-matched
            ("aria-label", "id", "data-testid", "placeholder", ...).
        value_pattern: Case-insensitive regex over the attribute value.
    """

    action: str
    tag: str = "button"
    attribute: str = "aria-label"
    value_pattern: str = r"copy"


@dataclass(frozen=True)
class DomProfile:
    """Per-site DOM locators: how to find the affordances in the HTML."""

    copy: tuple[DomMatcher, ...] = ()
    composer: tuple[DomMatcher, ...] = ()
    download: tuple[DomMatcher, ...] = ()

    def matchers_for(self, action: str) -> tuple[DomMatcher, ...]:
        """Matchers for one action (empty when the action is unregistered)."""
        return getattr(self, action, ()) or ()


# Built-in DOM profiles. Matchers are tried in order — the first regex
# that hits the page HTML wins. Keep the first entry the most specific
# (exact-word ``^copy$`` beats loose ``copy`` so "Copy code" buttons on
# code blocks never steal the reply's Copy button).
DEFAULT_DOM_PROFILES: dict[str, DomProfile] = {
    "chatgpt": DomProfile(
        copy=(
            DomMatcher("copy", "button", "aria-label", r"^copy$"),
            DomMatcher("copy", "button", "data-testid", r"copy"),
            DomMatcher("copy", "div", "data-testid", r"copy"),
        ),
        composer=(
            DomMatcher("composer", "", "id", r"prompt-textarea"),
            DomMatcher("composer", "textarea", "aria-label", r"ask anything|type a message"),
            DomMatcher("composer", "div", "contenteditable", r"true"),
        ),
    ),
    "gemini": DomProfile(
        copy=(
            DomMatcher("copy", "button", "aria-label", r"^copy$"),
            DomMatcher("copy", "button", "data-test-id", r"copy"),
        ),
        composer=(
            DomMatcher("composer", "div", "aria-label", r"enter a prompt here|ask gemini"),
            DomMatcher(
                "composer", "rich-textarea", "aria-label", r"enter a prompt here|ask gemini"
            ),
            DomMatcher(
                "composer", "rich-textarea", "data-placeholder", r"enter a prompt here|ask gemini"
            ),
            DomMatcher("composer", "div", "data-placeholder", r"enter a prompt here|ask gemini"),
            DomMatcher("composer", "div", "contenteditable", r"true"),
        ),
        download=(
            DomMatcher("download", "button", "aria-label", r"^download$"),
            DomMatcher("download", "div", "data-test-id", r"download"),
        ),
    ),
    # Claude.ai — ProseMirror contenteditable composer; Copy lives in the
    # hover action row of the newest message.
    "claude": DomProfile(
        copy=(
            DomMatcher("copy", "button", "aria-label", r"^copy$"),
            DomMatcher("copy", "div", "aria-label", r"^copy$"),
        ),
        composer=(
            DomMatcher(
                "composer", "div", "aria-label", r"message claude|what would you like help with"
            ),
            DomMatcher("composer", "div", "contenteditable", r"true"),
            DomMatcher("composer", "textarea", "placeholder", r"message claude"),
        ),
    ),
    # Perplexity.ai — a plain textarea that says "Ask anything...".
    "perplexity": DomProfile(
        copy=(
            DomMatcher("copy", "button", "aria-label", r"^copy$"),
            DomMatcher("copy", "button", "data-testid", r"copy"),
            DomMatcher("copy", "div", "data-testid", r"copy"),
        ),
        composer=(
            DomMatcher("composer", "textarea", "placeholder", r"ask anything"),
            DomMatcher("composer", "textarea", "aria-label", r"ask anything|search"),
            DomMatcher("composer", "div", "contenteditable", r"true"),
        ),
    ),
    # Grok (x.ai — grok.com) — image-capable; image gen has a Download affordance.
    "grok": DomProfile(
        copy=(
            DomMatcher("copy", "button", "aria-label", r"^copy$"),
            DomMatcher("copy", "button", "data-testid", r"copy"),
        ),
        composer=(
            DomMatcher("composer", "textarea", "placeholder", r"ask anything|ask grok"),
            DomMatcher("composer", "textarea", "aria-label", r"message grok"),
            DomMatcher("composer", "div", "contenteditable", r"true"),
        ),
        download=(
            DomMatcher("download", "button", "aria-label", r"^download$"),
            DomMatcher("download", "div", "aria-label", r"^download$"),
        ),
    ),
    # DeepSeek — the composer has the stable id chat-input.
    "deepseek": DomProfile(
        copy=(
            DomMatcher("copy", "button", "aria-label", r"^copy$"),
            DomMatcher("copy", "div", "title", r"^copy$"),
            DomMatcher("copy", "span", "title", r"^copy$"),
        ),
        composer=(
            DomMatcher("composer", "textarea", "id", r"chat-input"),
            DomMatcher("composer", "textarea", "placeholder", r"message deepseek|send a message"),
            DomMatcher("composer", "div", "contenteditable", r"true"),
        ),
    ),
    # Microsoft Copilot — textarea#user-input; Image Creator supports images.
    "copilot": DomProfile(
        copy=(
            DomMatcher("copy", "button", "aria-label", r"copy"),
            DomMatcher("copy", "div", "title", r"copy"),
        ),
        composer=(
            DomMatcher("composer", "textarea", "id", r"user-input|userInput"),
            DomMatcher("composer", "textarea", "placeholder", r"ask me anything"),
            DomMatcher("composer", "div", "contenteditable", r"true"),
        ),
        download=(
            DomMatcher("download", "button", "aria-label", r"^download$"),
            DomMatcher("download", "div", "aria-label", r"^download$"),
        ),
    ),
}

_DOM_CACHE: dict[str, DomProfile] | None = None


def get_dom_profile(site_key: str) -> DomProfile:
    """A site's DOM matchers with calibration overrides applied."""
    global _DOM_CACHE
    if _DOM_CACHE is None:
        _DOM_CACHE = _resolve_dom_profiles()
    return _DOM_CACHE.get(site_key, DomProfile())


def get_dom_matchers(site_key: str, action: str) -> tuple[DomMatcher, ...]:
    """Regex matchers for one affordance on one site (empty = not registered)."""
    return get_dom_profile(site_key).matchers_for(action)


def dom_action_enabled(site_key: str, action: str) -> bool:
    """
    True when DOM locating may be tried for this site+action.

    Off when the master switch (``AI_CHAIN_DOM=0``) is off, or the
    per-action kill switch ``AI_CHAIN_<SITE>_DOM_<ACTION>=0`` is set.
    """
    from .dom import dom_enabled

    if not dom_enabled():
        return False
    raw = os.getenv(f"AI_CHAIN_{site_key.upper()}_DOM_{action.upper()}", "").strip().lower()
    return raw != "0"


def reset_cache() -> None:
    """Drop the resolved-cache (used by tests / after editing calibration)."""
    global _ACTIONS_CACHE, _DOM_CACHE
    _ACTIONS_CACHE = None
    _DOM_CACHE = None


# ----------------------------------------------------------------------
# DOM profile override resolution
# ----------------------------------------------------------------------


def _resolve_dom_profiles() -> dict[str, DomProfile]:
    """Build every site's DomProfile with calibration overrides merged."""
    cal = _load_calibration()
    action_overrides: dict = cal.get("actions", {}) or {}
    profiles: dict[str, DomProfile] = {}
    for key, base in DEFAULT_DOM_PROFILES.items():
        profiles[key] = _resolve_dom_profile(key, base, action_overrides)
    # Calibration-only sites still get their dom entries honoured.
    for key, values in action_overrides.items():
        dom_override = (values or {}).get("dom")
        if isinstance(dom_override, dict) and dom_override and key not in profiles:
            profiles[key] = _resolve_dom_profile(key, DomProfile(), action_overrides)
    return profiles


def _resolve_dom_profile(site_key: str, base: DomProfile, action_overrides: dict) -> DomProfile:
    """Merge a calibration ``actions.<key>.dom`` section onto the base profile.

    Shape:
        {"actions": {"chatgpt": {"dom": {
            "copy": [
                {"tag": "button", "attribute": "aria-label", "value_pattern": "^copy$"}
            ]
        }}}}
    """
    dom_override = (action_overrides.get(site_key) or {}).get("dom") or {}
    if not isinstance(dom_override, dict) or not dom_override:
        return base
    fields: dict[str, tuple[DomMatcher, ...]] = {}
    for action in ("copy", "composer", "download"):
        entries = dom_override.get(action)
        if entries is None:
            fields[action] = base.matchers_for(action)
            continue
        fields[action] = tuple(
            DomMatcher(
                action=action,
                tag=str(entry.get("tag", "button")),
                attribute=str(entry.get("attribute", "aria-label")),
                value_pattern=str(entry.get("value_pattern", "copy")),
            )
            for entry in entries
            if isinstance(entry, dict)
        )
    return DomProfile(**fields)


def _resolve_copy(site_key: str, base: CopyAffordance, action_overrides: dict) -> CopyAffordance:
    """Merge calibration/actions + sites.<key>.copy_point + env overrides."""
    data: dict[str, Any] = {}

    cal = _load_calibration()
    # 1. Full affordance override: {"actions": {"chatgpt": {"copy": {...}}}}
    copy_override = (action_overrides.get(site_key) or {}).get("copy") or {}
    if isinstance(copy_override, dict):
        data.update(copy_override)

    # 2. Point recorded by calibrate.py: {"sites": {"chatgpt": {"copy_point": [x, y]}}}
    cal_sites = cal.get("sites", {}) or {}
    cal_copy_point = (cal_sites.get(site_key) or {}).get("copy_point")
    if cal_copy_point is not None:
        data["point"] = cal_copy_point

    # 3. Environment overrides: AI_CHAIN_<SITE>_COPY_POINT / _COPY_SCAN_REGION
    env_point = os.getenv(f"AI_CHAIN_{site_key.upper()}_COPY_POINT")
    if env_point:
        data["point"] = env_point
    env_region = os.getenv(f"AI_CHAIN_{site_key.upper()}_COPY_SCAN_REGION")
    if env_region:
        data["scan_region"] = env_region

    if not data:
        return base

    return CopyAffordance(
        method=str(data.get("method", base.method)).strip().lower() or base.method,
        label=str(data.get("label", base.label)).strip() or base.label,
        point=_to_point(data.get("point", base.point)),
        scan_region=_to_region(data.get("scan_region", base.scan_region)),
        retries=int(data.get("retries", base.retries)),
    )


def _keyboard_only(site_key: str) -> SiteActions:
    """Safe default: no registered button — the driver uses Ctrl+A/Ctrl+C."""
    return SiteActions(key=site_key, copy=CopyAffordance(method="keyboard", label="", point=None))


def _to_point(value) -> tuple[float, float] | None:
    """Normalise [x, y] / "x,y" into a float pair (or None)."""
    if value in (None, "", [None, None], (None, None)):
        return None
    if isinstance(value, str):
        value = value.split(",")
    try:
        return (float(value[0]), float(value[1]))
    except (TypeError, ValueError, IndexError):
        return None


def _to_region(value) -> tuple[float, float, float, float] | None:
    """Normalise [x0, y0, x1, y1] / "x0,y0,x1,y1" into a box (or None)."""
    if value in (None, "", [None, None, None, None], (None, None, None, None)):
        return None
    if isinstance(value, str):
        value = value.split(",")
    try:
        x0, y0, x1, y1 = (float(v) for v in value[:4])
    except (TypeError, ValueError, IndexError):
        return None
    return _clamp_region((x0, y0, x1, y1))


def _region_around(point: tuple[float, float] | None) -> tuple[float, float, float, float] | None:
    """Default scan box when no region is registered: a box around the point."""
    if point is None:
        return None
    px, py = point
    return _clamp_region((px - 0.12, py - 0.12, px + 0.12, py + 0.12))


def _clamp_region(region: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
    """Clamp a scan box to valid window fractions, x0<x1 and y0<y1."""
    x0, y0, x1, y1 = region
    x0, x1 = min(x0, x1), max(x0, x1)
    y0, y1 = min(y0, y1), max(y0, y1)
    return (
        max(0.0, min(1.0, x0)),
        max(0.0, min(1.0, y0)),
        max(0.0, min(1.0, x1)),
        max(0.0, min(1.0, y1)),
    )


def _linspace(start: float, end: float, steps: int) -> list[float]:
    """Evenly spaced values from start to end inclusive (steps >= 2)."""
    if steps < 2:
        return [start]
    step = (end - start) / (steps - 1)
    return [start + step * i for i in range(steps)]


def _dist(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Euclidean distance between two fraction points."""
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5
