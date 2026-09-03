"""
ai_chain/calibration.py

Site catalogue + calibration handling.

Ships default specifications for the supported AI websites and lets the
user override anything (window fractions, timings, downloads folder)
through a per-machine calibration.json — written by `calibrate.py`.

calibration.json is NOT committed (see .gitignore). When missing, the
built-in defaults are used, so the module works out of the box — just
less precisely until calibrated.

Resolved site specs also honour AI_CHAIN_* environment variables, so
a URL or timing can be changed without touching files.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from .models import SiteSpec

PACKAGE_DIR = Path(__file__).resolve().parent

# Built-in catalogue of AI websites the driver knows how to operate.
DEFAULT_SITES: dict[str, SiteSpec] = {
    "chatgpt": SiteSpec(
        key="chatgpt",
        label="ChatGPT",
        url="https://chatgpt.com/",
        title_keyword="ChatGPT",
        composer=(0.5, 0.94),
        read_point=(0.5, 0.3),
        footer_markers=("ChatGPT can make mistakes",),
    ),
    "gemini": SiteSpec(
        key="gemini",
        label="Gemini",
        url="https://gemini.google.com/app",
        title_keyword="Gemini",
        composer=(0.5, 0.955),
        read_point=(0.5, 0.3),
        image_capable=True,
        # Rough guess for the download row of the newest image: just above
        # the composer, slightly right of centre. Calibrate for exactness.
        image_download_point=None,
        max_wait=240.0,
        footer_markers=(
            "Gemini may display inaccurate info",
            "This is an experimental feature",
        ),
    ),
}

# Aliases the user might say when naming an AI.
SITE_ALIASES: dict[str, str] = {
    "chatgpt": "chatgpt",
    "chat gpt": "chatgpt",
    "gpt": "chatgpt",
    "openai": "chatgpt",
    "open ai chat": "chatgpt",
    "gemini": "gemini",
    "google gemini": "gemini",
}

DEFAULT_DOWNLOADS_DIR = "~/Downloads"

# User-editable overrides (created by calibrate.py on first run).
CALIBRATION_FILE = PACKAGE_DIR / "calibration.json"

# Example shipped with the repo (never rewritten by the module).
EXAMPLE_CALIBRATION = PACKAGE_DIR / "calibration.example.json"

_CALIBRATION_CACHE: dict | None = None


def resolve_site(name: str) -> SiteSpec:
    """Resolve a user-provided AI name/alias into its canonical SiteSpec."""
    cleaned = " ".join((name or "").strip().lower().split())
    key = SITE_ALIASES.get(cleaned)
    if key is None:
        known = ", ".join(sorted(DEFAULT_SITES))
        raise ValueError(f"Unknown AI '{name}'. Known AIs: {known}")
    return get_site(key)


def get_site(key: str) -> SiteSpec:
    """Return a site spec with calibration + env overrides applied."""
    base = DEFAULT_SITES[key]
    overrides = _load_calibration().get("sites", {}).get(key, {})
    return _apply_overrides(base, overrides)


def get_downloads_dir() -> Path:
    """Where the browser saves downloaded files (images we then harvest)."""
    cal = _load_calibration()
    raw = cal.get("downloads_dir") or os.getenv("AI_CHAIN_DOWNLOADS_DIR") or DEFAULT_DOWNLOADS_DIR
    path = Path(raw).expanduser()
    if not path.exists():
        profile = os.environ.get("USERPROFILE")
        if profile:
            path = Path(profile) / "Downloads"
    return path


def save_calibration(overrides: dict) -> None:
    """Persist calibration overrides to calibration.json (user-local)."""
    payload = _load_calibration()
    sites = payload.setdefault("sites", {})
    for key, values in overrides.items():
        sites[key] = {**sites.get(key, {}), **values}
    CALIBRATION_FILE.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    global _CALIBRATION_CACHE
    _CALIBRATION_CACHE = payload


# ----------------------------------------------------------------------
# Internal helpers
# ----------------------------------------------------------------------


def _load_calibration() -> dict:
    global _CALIBRATION_CACHE
    if _CALIBRATION_CACHE is not None:
        return _CALIBRATION_CACHE

    payload: dict = {"downloads_dir": DEFAULT_DOWNLOADS_DIR, "sites": {}}
    source = CALIBRATION_FILE if CALIBRATION_FILE.exists() else EXAMPLE_CALIBRATION
    if source.exists():
        try:
            payload = json.loads(source.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            payload = {"downloads_dir": DEFAULT_DOWNLOADS_DIR, "sites": {}}
    _CALIBRATION_CACHE = payload
    return payload


def _apply_overrides(spec: SiteSpec, overrides: dict) -> SiteSpec:
    """Merge calibration/env overrides onto a base spec."""
    data = overrides.copy()
    # Env overrides win over calibration for a few knobs.
    env = {
        "url": os.getenv(f"AI_CHAIN_{spec.key.upper()}_URL"),
        "page_load_wait": os.getenv(f"AI_CHAIN_{spec.key.upper()}_LOAD_WAIT"),
        "max_wait": os.getenv(f"AI_CHAIN_{spec.key.upper()}_MAX_WAIT"),
    }
    for field, value in env.items():
        if value:
            data[field] = float(value) if field in ("page_load_wait", "max_wait") else value

    if not data:
        return spec

    kwargs = dict(
        key=spec.key,
        label=spec.label,
        url=str(data.get("url", spec.url)),
        title_keyword=str(data.get("title_keyword", spec.title_keyword)),
        composer=_to_point(data.get("composer", spec.composer)),
        read_point=_to_point(data.get("read_point", spec.read_point)),
        image_capable=bool(data.get("image_capable", spec.image_capable)),
        image_download_point=_to_point(
            data.get("image_download_point", spec.image_download_point), optional=True
        ),
        page_load_wait=float(data.get("page_load_wait", spec.page_load_wait)),
        poll_interval=float(data.get("poll_interval", spec.poll_interval)),
        max_wait=float(data.get("max_wait", spec.max_wait)),
        stable_polls=int(data.get("stable_polls", spec.stable_polls)),
        footer_markers=tuple(data.get("footer_markers", spec.footer_markers)),
    )
    return SiteSpec(**kwargs)


def _to_point(value, optional: bool = False):
    """Normalise [x, y] / "x,y" lists into a float pair (or None)."""
    if value in (None, "", [None, None], (None, None)):
        return None if optional else value
    if isinstance(value, str):
        value = value.split(",")
    try:
        return (float(value[0]), float(value[1]))
    except (TypeError, ValueError, IndexError):
        return None if optional else value
