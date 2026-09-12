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
        login_markers=(
            "Log in",
            "Sign up",
            "Continue with",
            "Email address",
        ),
        landing_markers=(
            "New chat",
            "What can I help with",
            "Start with a prompt",
        ),
        loading_markers=("Stop generating", "Thinking", "Generating"),
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
        login_markers=(
            "Sign in",
            "to continue to Gemini",
            "Use Gemini",
            "Continue to Gemini",
        ),
        landing_markers=(
            "New chat",
            "How can I help",
            "Welcome to Gemini",
            "Ask Gemini",
        ),
        loading_markers=("Stop", "Generating", "Creating"),
    ),
    "claude": SiteSpec(
        key="claude",
        label="Claude",
        url="https://claude.ai/new",
        title_keyword="Claude",
        composer=(0.5, 0.94),
        read_point=(0.5, 0.3),
        footer_markers=("Claude can make mistakes. Please double-check responses",),
        login_markers=(
            "Log in",
            "Sign in",
            "Continue with",
            "Email address",
            "Work email",
        ),
        landing_markers=(
            "What would you like help with",
            "Start a new conversation",
            "New conversation",
        ),
        loading_markers=("Stop", "Thinking", "Generating"),
    ),
    "perplexity": SiteSpec(
        key="perplexity",
        label="Perplexity",
        url="https://www.perplexity.ai/",
        title_keyword="Perplexity",
        composer=(0.5, 0.95),
        read_point=(0.5, 0.3),
        footer_markers=(
            "Ask follow-up",
            "Follow-up",
            "Sources",
        ),
        login_markers=(
            "Log in",
            "Sign up",
            "Continue with",
            "Get started",
        ),
        landing_markers=(
            "What do you want to know",
            "Ask anything",
            "New Thread",
        ),
        loading_markers=("Stop generating", "Searching", "Thinking"),
    ),
    "grok": SiteSpec(
        key="grok",
        label="Grok",
        url="https://grok.com/",
        title_keyword="Grok",
        composer=(0.5, 0.95),
        read_point=(0.5, 0.3),
        image_capable=True,
        image_download_point=None,
        footer_markers=("Grok can make mistakes",),
        login_markers=(
            "Log in",
            "Sign up",
            "Continue with",
        ),
        landing_markers=(
            "What do you want to know",
            "Ask Grok anything",
            "New chat",
        ),
        loading_markers=("Stop generating", "Thinking", "Generating"),
    ),
    "deepseek": SiteSpec(
        key="deepseek",
        label="DeepSeek",
        url="https://chat.deepseek.com/",
        title_keyword="DeepSeek",
        composer=(0.5, 0.95),
        read_point=(0.5, 0.3),
        footer_markers=(
            "DeepSeek can make mistakes",
            "Content is for reference only",
        ),
        login_markers=(
            "Log in",
            "Sign in",
            "Register",
        ),
        landing_markers=(
            "What can I help you with",
            "New chat",
        ),
        loading_markers=("Stop responding", "Thinking"),
    ),
    "copilot": SiteSpec(
        key="copilot",
        label="Copilot",
        url="https://copilot.microsoft.com/",
        title_keyword="Copilot",
        composer=(0.5, 0.95),
        read_point=(0.5, 0.3),
        image_capable=True,
        image_download_point=None,
        footer_markers=("Copilot can make mistakes",),
        login_markers=(
            "Sign in",
            "Log in",
            "Microsoft account",
            "Continue with",
        ),
        landing_markers=(
            "What do you want to do",
            "Ask me anything",
            "New chat",
        ),
        loading_markers=("Stop generating", "Thinking", "Generating"),
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
    "claude": "claude",
    "claude ai": "claude",
    "anthropic": "claude",
    "perplexity": "perplexity",
    "grok": "grok",
    "x ai": "grok",
    "deepseek": "deepseek",
    "copilot": "copilot",
    "bing ai": "copilot",
}

DEFAULT_DOWNLOADS_DIR = "~/Downloads"

# Dedicated browser profile the robot drives (v1.5). Persistent, so the
# user logs in to each AI site ONCE and every later run is already
# authenticated — and because the profile dir is explicit, Chrome honours
# the remote-debugging flag, which is what makes v1.5 DOM locating work.
# Some machines silently refuse the debug flag on the default profile, so
# the robot never relies on the user's own browser window.
DEFAULT_PROFILE_DIR = PACKAGE_DIR / ".chrome-profile"
PROFILE_DIR_ENV = "AI_CHAIN_PROFILE_DIR"
PROFILE_SWITCH_ENV = "AI_CHAIN_AUTOMATION_PROFILE"


def get_automation_profile_dir() -> Path:
    """Where the robot's Chrome profile lives (env-overridable)."""
    raw = os.getenv(PROFILE_DIR_ENV, "").strip()
    return Path(raw).expanduser() if raw else DEFAULT_PROFILE_DIR


def automation_profile_enabled() -> bool:
    """Master switch: AI_CHAIN_AUTOMATION_PROFILE=0 uses the default browser."""
    return os.getenv(PROFILE_SWITCH_ENV, "").strip() != "0"


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
        login_markers=tuple(data.get("login_markers", spec.login_markers)),
        landing_markers=tuple(data.get("landing_markers", spec.landing_markers)),
        loading_markers=tuple(data.get("loading_markers", spec.loading_markers)),
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
