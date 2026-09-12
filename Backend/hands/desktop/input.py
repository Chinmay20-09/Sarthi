"""Keyboard, mouse, and clipboard backends for the Desktop hand.

pyautogui (input) and pyperclip (clipboard) are the optional
``automation`` extra — the same stack the ai_chain module already uses.
Every import degrades gracefully; the hand reports unavailability as a
structured failure instead of pretending success.
"""

from __future__ import annotations

import logging
import time

logger = logging.getLogger(__name__)

__all__ = [
    "type_text",
    "press_key",
    "hotkey",
    "move_mouse",
    "click",
    "copy_to_clipboard",
    "read_clipboard",
    "paste",
]


def _pyautogui():
    """Import pyautogui lazily; raise a descriptive error when absent."""
    try:
        import pyautogui
    except ImportError as e:
        raise RuntimeError(
            "pyautogui is not installed — install the automation extra: pip install -e '.[automation]'"
        ) from e
    return pyautogui


def _pyperclip():
    """Import pyperclip lazily; raise a descriptive error when absent."""
    try:
        import pyperclip
    except ImportError as e:
        raise RuntimeError(
            "pyperclip is not installed — install the automation extra: pip install -e '.[automation]'"
        ) from e
    return pyperclip


# ---------------------------------------------------------------------------
# Keyboard
# ---------------------------------------------------------------------------


def type_text(text: str, interval: float = 0.0) -> None:
    """Type text into the foreground window."""
    pyautogui = _pyautogui()
    pyautogui.typewrite(text, interval=interval)


def press_key(key: str) -> None:
    """Press a single key (e.g. \"enter\", \"esc\", \"f5\")."""
    pyautogui = _pyautogui()
    pyautogui.press(key)


def hotkey(keys: list[str], interval: float = 0.1) -> None:
    """Press a key combination (e.g. [\"ctrl\", \"c\"])."""
    pyautogui = _pyautogui()
    pyautogui.hotkey(*keys, interval=interval)


# ---------------------------------------------------------------------------
# Mouse
# ---------------------------------------------------------------------------


def move_mouse(x: int, y: int, duration: float = 0.2) -> None:
    """Move the mouse to absolute pixel coordinates."""
    pyautogui = _pyautogui()
    pyautogui.moveTo(x, y, duration=duration)


def click(x: int, y: int) -> None:
    """Left-click at absolute pixel coordinates."""
    pyautogui = _pyautogui()
    pyautogui.click(x=x, y=y)


# ---------------------------------------------------------------------------
# Clipboard
# ---------------------------------------------------------------------------


def copy_to_clipboard(text: str) -> None:
    """Place text on the system clipboard."""
    pyperclip = _pyperclip()
    pyperclip.copy(text)


def read_clipboard() -> str:
    """Read the current clipboard text (empty string for non-text content)."""
    pyperclip = _pyperclip()
    return pyperclip.paste() or ""


def paste() -> None:
    """Paste clipboard content into the foreground window (Ctrl+V)."""
    pyautogui = _pyautogui()
    pyautogui.hotkey("ctrl", "v", interval=0.05)
    time.sleep(0.05)
