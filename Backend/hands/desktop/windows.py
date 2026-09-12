"""Windows window enumeration helpers for the Desktop hand.

Thin wrappers around the Win32 API (via pywin32, an optional dependency)
for reading window state. Kept separate from ``processes.py`` so future
``WINDOW_CONTROL`` actions (focus/minimize/maximize/close) have a clear
home without growing the process module.

Every function degrades gracefully: without pywin32 they return empty
results, and the hand reports that as a structured failure — it never
pretends success.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

__all__ = ["list_windows", "get_active_window"]


def list_windows(limit: int = 50) -> list[dict]:
    """Visible top-level windows (hwnd, title). Empty without pywin32."""
    try:
        import win32gui
    except ImportError:
        logger.debug("[Desktop] pywin32 not installed — window listing unavailable")
        return []

    out: list[dict] = []
    done = False

    def _collect(hwnd: int, _param: None) -> None:
        nonlocal done
        if done or not win32gui.IsWindowVisible(hwnd):
            return
        title = win32gui.GetWindowText(hwnd)
        if title:
            out.append({"hwnd": hwnd, "title": title})
            if len(out) >= limit:
                done = True

    try:
        win32gui.EnumWindows(_collect, None)
    except Exception as e:  # win32gui raises its own error types
        logger.debug(f"[Desktop] window enumeration failed: {e}")
    return out


def get_active_window() -> dict | None:
    """Foreground window (hwnd, title), or None when unavailable."""
    try:
        import win32gui
    except ImportError:
        logger.debug("[Desktop] pywin32 not installed — active window unavailable")
        return None
    try:
        hwnd = win32gui.GetForegroundWindow()
    except Exception as e:
        logger.debug(f"[Desktop] GetForegroundWindow failed: {e}")
        return None
    if not hwnd:
        return None
    title = win32gui.GetWindowText(hwnd)
    return {"hwnd": hwnd, "title": title}
