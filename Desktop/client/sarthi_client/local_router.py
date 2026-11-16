"""Small deterministic routes owned by the desktop device."""

from __future__ import annotations

import os

from .app_inventory import resolve_application
from .local_hand import LocalDesktopHand

_OPEN_PREFIXES = ("open ", "launch ", "start ", "run ")
_COMPOUND_MARKERS = (" and ", " then ", " after that ", ";", "\n", "\r")
IS_WINDOWS = os.name == "nt"


def route_local_query(query: str) -> dict | None:
    """Execute an unambiguous single app launch locally, else defer to backend.

    Returning ``None`` means this router does not own the request. It does
    not attempt general natural-language interpretation.
    """
    if not IS_WINDOWS:
        return None

    normalized = (query or "").strip()
    lower = normalized.lower()
    prefix = next((candidate for candidate in _OPEN_PREFIXES if lower.startswith(candidate)), None)
    if prefix is None:
        return None
    target = normalized[len(prefix):].strip().rstrip(".?! ")
    if not target or any(marker in f" {target.lower()} " for marker in _COMPOUND_MARKERS):
        return None

    app = resolve_application(target)
    if app is None:
        return None
    name, path = app
    try:
        LocalDesktopHand().open_application(path)
    except (OSError, ValueError) as exc:
        return {
            "success": False,
            "response": f"Could not open {name}: {exc}",
            "data": {"application": name},
            "routing": "desktop_local",
        }

    return {
        "success": True,
        "response": f"Opened {name}.",
        "data": {"application": name, "path": path},
        "routing": "desktop_local",
    }
