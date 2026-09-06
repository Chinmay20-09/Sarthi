"""
ai_chain/control.py

Laptop-control primitives (the "robot hand") for the AI chain.

Wraps the desktop automation stack so the rest of the module never
imports it directly:

    PyAutoGUI  — mouse movement / clicks / hotkeys (built-in failsafe:
                 slam the mouse into a screen corner to abort)
    keyboard   — global abort hotkey (Ctrl+Alt+X)
    pyperclip  — clipboard paste/read (robust Unicode text entry)
    pywin32    — find & activate the browser window so keystrokes land
                 in the right place

Every heavy dependency is imported lazily inside methods so that this
module (and the whole ai_chain package) can be imported and unit-tested
on machines that do not have the automation stack installed.

All screen coordinates are converted from *window fractions* (0..1)
against the live browser window rectangle.
"""

from __future__ import annotations

import os
import subprocess
import time
import urllib.request
from pathlib import Path
from typing import Any

from utils.logger import get_logger

from .calibration import automation_profile_enabled, get_automation_profile_dir
from .dom import cdp_port, cdp_url

logger = get_logger(__name__)

# How long open_site waits for the browser window to appear. Browsers can
# take several seconds to cold-start and the site title only appears once
# the page loads, so the window search must be much more generous than
# the page-load wait. Polling returns as soon as the window is found.
WINDOW_FIND_TIMEOUT = 30.0

# Common Chrome/Edge installs (Edge speaks the same DevTools protocol).
_BROWSER_CANDIDATES = (
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
)


def find_chrome_exe() -> str | None:
    """A Chromium-family executable for the automation profile.

    ``AI_CHAIN_CHROME_PATH`` wins when set; otherwise the usual Windows
    install paths are probed (Chrome first, Edge as a fallback).
    """
    override = os.getenv("AI_CHAIN_CHROME_PATH", "").strip()
    if override and Path(override).exists():
        return override
    for candidate in _BROWSER_CANDIDATES:
        path = Path(os.path.expandvars(candidate))
        if path.exists():
            return str(path)
    return None


def _chrome_launch_command(chrome: str, url: str, port: int, profile_dir: Path) -> list[str]:
    """The automation Chrome command line (pure — unit-testable).

    ``--user-data-dir`` must be explicit: some Chrome installs silently
    ignore ``--remote-debugging-port`` for the default profile, which is
    exactly what broke v1.5 DOM locating in live runs.
    """
    return [
        chrome,
        f"--remote-debugging-port={port}",
        f"--user-data-dir={profile_dir}",
        "--no-first-run",
        "--no-default-browser-check",
        url,
    ]


def _wait_for_cdp(endpoint: str, timeout: float) -> bool:
    """Poll the DevTools HTTP endpoint until it answers (or timeout)."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"{endpoint}/json/version", timeout=1.5) as response:
                if response.status == 200:
                    return True
        except Exception:
            pass
        time.sleep(0.5)
    return False


class AbortError(RuntimeError):
    """Raised when the user aborts the run (hotkey or failsafe corner)."""


def _require(name: str):
    """Import an automation module or fail with an actionable message."""
    try:
        return __import__(name)
    except ImportError:
        raise RuntimeError(
            f"Missing '{name}'. Install the laptop-automation stack:\n"
            "    pip install pyautogui keyboard pyperclip pywin32\n"
            "(all of them must be installed in the active environment)"
        ) from None


class ScreenController:
    """Keyboard/mouse/window control behind the AI chain."""

    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        self._aborted = False
        self._hotkey_handle: Any = None
        self._fail_safe_enabled = False
        self._register_hotkey()
        if not dry_run:
            self._enable_fail_safe()

    # ------------------------------------------------------------------
    # Lifecycle / abort
    # ------------------------------------------------------------------

    def _register_hotkey(self) -> None:
        """Register Ctrl+Alt+X as the global 'stop the robot' hotkey."""
        try:
            keyboard = _require("keyboard")
            self._hotkey_handle = keyboard.add_hotkey("ctrl+alt+x", self._set_abort)
        except RuntimeError as exc:
            logger.warning(f"Abort hotkey unavailable: {exc}")

    def _enable_fail_safe(self) -> None:
        """PyAutoGUI failsafe: mouse in a screen corner raises on next action."""
        try:
            pyautogui = _require("pyautogui")
            pyautogui.FAILSAFE = True
            self._fail_safe_enabled = True
        except RuntimeError:
            pass

    def _set_abort(self) -> None:
        self._aborted = True

    def check_abort(self) -> None:
        """Raise AbortError when the user asked to stop (hotkey or corner)."""
        if self._aborted:
            raise AbortError("Aborted by user (Ctrl+Alt+X).")

    def release(self) -> None:
        """Clean up hotkey listeners when the run finishes."""
        if self._hotkey_handle is not None:
            try:
                keyboard = _require("keyboard")
                keyboard.remove_hotkey(self._hotkey_handle)
            except Exception:
                pass
            self._hotkey_handle = None

    # ------------------------------------------------------------------
    # Browser window handling
    # ------------------------------------------------------------------

    def open_site(self, url: str, title_keyword: str, wait: float) -> None:
        """
        Open a URL in the robot's own Chrome and bring its window forward.

        v1.5 launches a dedicated automation Chrome (persistent profile +
        remote-debugging port) instead of the user's default browser, so
        DOM locating works on every run and logins persist. Falls back to
        the default browser when Chrome cannot be found or launching is
        disabled (``AI_CHAIN_AUTOMATION_PROFILE=0``).
        """
        if self.dry_run:
            logger.info(f"[DRY RUN] would open {url}")
            return
        launched = False
        if automation_profile_enabled():
            launched = self._open_in_automation_chrome(url)
        if not launched:
            import webbrowser

            webbrowser.open(url)
        logger.info(
            f"Waiting for a browser window titled like '{title_keyword}' "
            f"(up to {WINDOW_FIND_TIMEOUT:.0f}s)..."
        )
        hwnd = self._find_window(title_keyword, timeout=WINDOW_FIND_TIMEOUT)
        if hwnd is None:
            raise RuntimeError(
                f"Could not find a browser window titled like '{title_keyword}' "
                f"within {WINDOW_FIND_TIMEOUT:.0f}s. Make sure the site is open "
                "and logged in."
            )
        self._activate_window(hwnd)
        time.sleep(min(wait, 2.0))

    def _open_in_automation_chrome(self, url: str) -> bool:
        """Launch (or reuse) the robot's Chrome with the debug port.

        Returns True when a browser window was opened (even when the CDP
        endpoint never came up — the window still works, just without
        v1.5 DOM locating). Returns False only when we could not launch
        anything and the caller should use the default browser.
        """
        chrome = find_chrome_exe()
        if chrome is None:
            logger.warning(
                "No Chrome/Edge executable found for the automation profile "
                "— opening the default browser instead (v1.5 DOM locating off)."
            )
            return False
        profile = get_automation_profile_dir()
        try:
            profile.mkdir(parents=True, exist_ok=True)
            cmd = _chrome_launch_command(chrome, url, cdp_port(), profile)
            subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
            )
        except Exception as exc:
            logger.warning(f"Could not launch automation Chrome ({exc}) — using default browser.")
            return False

        if _wait_for_cdp(cdp_url(), timeout=30.0):
            logger.info(f"[dom] automation Chrome ready at {cdp_url()} (profile: {profile})")
        else:
            logger.warning(
                "Automation Chrome opened but the DevTools endpoint did not come up "
                "within 30s — v1.5 DOM locating will be off for this run."
            )
        return True

    def focus_address_bar_and_go(self, url: str) -> None:
        """Ctrl+L → type URL → Enter (used when the tab already exists)."""
        self.check_abort()
        if self.dry_run:
            logger.info(f"[DRY RUN] would navigate to {url}")
            return
        self.hotkey("ctrl", "l")
        self.paste(url)
        self.press("enter")

    def window_rect(self, title_keyword: str) -> tuple[int, int, int, int]:
        """(left, top, right, bottom) of the browser window, in pixels."""
        if self.dry_run:
            return (0, 0, 1280, 800)
        hwnd = self._find_window(title_keyword, timeout=10.0)
        if hwnd is None:
            raise RuntimeError(f"Browser window '{title_keyword}' not found.")
        win32gui = _require("win32gui")
        return win32gui.GetWindowRect(hwnd)

    def fraction_point(
        self, rect: tuple[int, int, int, int], fx: float, fy: float
    ) -> tuple[int, int]:
        """Convert window fractions into absolute screen coordinates."""
        left, top, right, bottom = rect
        x = int(left + (right - left) * fx)
        y = int(top + (bottom - top) * fy)
        return (x, y)

    # ------------------------------------------------------------------
    # Input primitives
    # ------------------------------------------------------------------

    def click(self, x: int, y: int) -> None:
        self.check_abort()
        if self.dry_run:
            logger.info(f"[DRY RUN] would click ({x}, {y})")
            return
        try:
            pyautogui = _require("pyautogui")
            pyautogui.click(x, y)
        except Exception as exc:  # pyautogui.FailSafeException & friends
            raise AbortError("Aborted by user (mouse failsafe corner).") from exc

    def paste(self, text: str) -> None:
        """Type text reliably via the clipboard (handles Unicode + speed)."""
        self.check_abort()
        if self.dry_run:
            logger.info(f"[DRY RUN] would paste {len(text)} chars")
            return
        if not text:
            return
        pyperclip = _require("pyperclip")
        pyautogui = _require("pyautogui")
        pyperclip.copy(text)
        time.sleep(0.15)
        pyautogui.hotkey("ctrl", "v")
        time.sleep(0.15)

    def press(self, key: str) -> None:
        self.check_abort()
        if self.dry_run:
            logger.info(f"[DRY RUN] would press {key}")
            return
        pyautogui = _require("pyautogui")
        pyautogui.press(key)

    def hotkey(self, *keys: str) -> None:
        self.check_abort()
        if self.dry_run:
            logger.info(f"[DRY RUN] would press {'+'.join(keys)}")
            return
        pyautogui = _require("pyautogui")
        pyautogui.hotkey(*keys)

    def select_all_and_copy(self) -> str:
        """Ctrl+A then Ctrl+C on the focused page; return the clipboard."""
        self.check_abort()
        if self.dry_run:
            return "[dry-run transcript]"
        pyautogui = _require("pyautogui")
        pyperclip = _require("pyperclip")
        pyperclip.copy("")  # clear so stale clipboard never looks like a read
        pyautogui.hotkey("ctrl", "a")
        time.sleep(0.2)
        pyautogui.hotkey("ctrl", "c")
        time.sleep(0.2)
        return pyperclip.paste() or ""

    def copy_with_button(self, x: int, y: int) -> str:
        """Click a Copy button (registered per site) and return the clipboard.

        Unlike ``select_all_and_copy`` this grabs ONLY what the button
        copies — the assistant's reply — instead of Ctrl+A'ing the whole
        page. Returns "" when the click missed (no button there), so the
        caller can fall back to the keyboard page copy.
        """
        self.check_abort()
        if self.dry_run:
            return "[dry-run transcript]"
        pyautogui = _require("pyautogui")
        pyperclip = _require("pyperclip")
        pyperclip.copy("")  # clear so stale clipboard never looks like a read
        pyautogui.click(x, y)
        time.sleep(0.3)  # let the UI put the message text on the clipboard
        return pyperclip.paste() or ""

    # ------------------------------------------------------------------
    # Calibration helpers
    # ------------------------------------------------------------------

    def cursor_position(self) -> tuple[int, int]:
        """Current absolute mouse position (calibrate.py uses this)."""
        pyautogui = _require("pyautogui")
        x, y = pyautogui.position()
        return int(x), int(y)

    def wait_for_key(self, key: str) -> None:
        """Block until the user presses a key (calibrate.py uses this)."""
        keyboard = _require("keyboard")
        keyboard.read_key(key)

    # ------------------------------------------------------------------
    # Private window helpers
    # ------------------------------------------------------------------

    def _find_window(self, title_keyword: str, timeout: float = 10.0) -> int | None:
        win32gui = _require("win32gui")
        keyword = title_keyword.lower()
        deadline = time.time() + timeout
        while time.time() < deadline:
            hits: list[int] = []

            def collect(hwnd, _extra) -> bool:
                if win32gui.IsWindowVisible(hwnd) and win32gui.IsWindowEnabled(hwnd):
                    title = win32gui.GetWindowText(hwnd)
                    if keyword in title.lower():
                        hits.append(hwnd)
                return True

            win32gui.EnumWindows(collect, None)
            if hits:
                # Prefer the foreground window (the one webbrowser.open just
                # brought up / the user is looking at), then the first hit:
                # EnumWindows walks z-order from front-most to back, so the
                # first enumerated match is the top-most one. Sorting by the
                # numeric hwnd (as before) is wrong — handles carry no
                # z-order information.
                foreground = win32gui.GetForegroundWindow()
                if foreground in hits:
                    return foreground
                return hits[0]
            time.sleep(0.5)
        return None

    def _activate_window(self, hwnd: int) -> None:
        win32gui = _require("win32gui")
        win32con = _require("win32con")
        try:
            if win32gui.IsIconic(hwnd):
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            win32gui.SetForegroundWindow(hwnd)
        except Exception as exc:  # WinError 5 / focus-stealing protection
            logger.debug(f"SetForegroundWindow failed ({exc}); clicking title bar")
            try:
                rect = win32gui.GetWindowRect(hwnd)
                cx = (rect[0] + rect[2]) // 2
                self.click(cx, rect[1] + 12)
            except Exception:
                pass
