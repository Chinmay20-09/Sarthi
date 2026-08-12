"""
Sarthi wake word launcher.

Listens for the wake word phrase(s) configured in variable.py. When
detected, it runs start.bat — which boots the API + UI and opens the
Sarthi website in your default browser.

For a hands-off background listener, double-click wakeword.bat: it runs
this script fully windowless (pythonw, no console) with a system tray
icon, logs to logs/wakeword.log, and restarts the listener if it ever
crashes. Saying the wake word launches Sarthi without opening any
terminal windows (see start.bat's background mode).

After a wake word launches Sarthi, the listener goes dormant (no
microphone use) until Sarthi is closed, then listens again automatically
— see variable.py's DORMANT_WHILE_RUNNING settings.

Usage:
    python wakeword.py                    # keep listening (Ctrl+C to stop)
    python wakeword.py --once             # listen for one wake word, then exit
    python wakeword.py --tray             # show a system tray icon (right-click to stop)
    python wakeword.py --supervise        # windowless watchdog: run --tray, restart on crash
    python wakeword.py --log-file LOG     # also write logs to a file
"""

import argparse
import ctypes
import ctypes.wintypes
import logging
import os
import signal
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path
from typing import Any

import variable
from speech.speech_to_text import get_model
from speech.wake_word import WakeWordListener, wake_word_matches
from utils.logger import setup_logging

ROOT = Path(__file__).resolve().parent
START_BAT = ROOT / "start.bat"
LOCK_FILE = ROOT / "wakeword.pid"

# Windows flag that creates a process without a console window. Used for
# every background subprocess so no terminal ever flashes or persists.
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

logger = logging.getLogger("wakeword")  # configured in main() via setup_logging

_launched_at = 0.0

# The active listener (set in _listen) and the tray icon while tray mode
# runs — used by the dormant-mode watcher to pause/resume and to update
# the tray tooltip.
_listener: "WakeWordListener | None" = None
_tray_icon: Any = None


def launch_sarthi(_text: str = "") -> bool:
    """Run start.bat to boot Sarthi and open the website.

    Accepts the detected text so it can be used directly as the
    WakeWordListener's on_wake callback.

    After a successful launch the listener goes dormant (no mic use)
    until Sarthi exits — see _enter_dormancy().

    Returns:
        True if start.bat was launched, False if it was skipped
        (cooldown) or the launch failed.
    """
    global _launched_at

    now = time.monotonic()
    cooldown = getattr(variable, "LAUNCH_COOLDOWN", 30)
    if now - _launched_at < cooldown:
        remaining = int(cooldown - (now - _launched_at))
        print(f"⏳ Already launched recently — ignoring (cooldown {remaining}s left).")
        logger.info("Ignoring wake word — cooldown %ss left.", remaining)
        return False

    print("🚀 Wake word detected! Launching Sarthi...")
    try:
        # start.bat in "background" mode launches the API/UI windowless
        # (pythonw); CREATE_NO_WINDOW hides the cmd wrapper itself.
        subprocess.Popen(
            ["cmd", "/c", str(START_BAT), "background"],
            cwd=str(ROOT),
            creationflags=_NO_WINDOW,
        )
        _launched_at = now
        logger.info("Wake word detected — launched start.bat (background).")
    except OSError as e:
        print(f"❌ Could not run start.bat: {e}")
        logger.error("Could not run start.bat: %s", e)
        return False

    _enter_dormancy()
    return True


# ------------------------------------------------------------------
# Dormant mode — stop listening while Sarthi is running
# ------------------------------------------------------------------


def _sarthi_is_up() -> bool:
    """Return True if the Sarthi API health endpoint is responding."""
    url = getattr(variable, "SARTHI_HEALTH_URL", "http://127.0.0.1:8000/health")
    try:
        with urllib.request.urlopen(url, timeout=2) as resp:
            return resp.status == 200
    except Exception:
        return False


def _clear_cooldown() -> None:
    """Allow an immediate re-launch once Sarthi is no longer running."""
    global _launched_at
    _launched_at = 0.0


def _set_tray_title(title: str) -> None:
    """Update the tray icon tooltip (no-op when tray mode is inactive)."""
    icon = _tray_icon
    if icon is None:
        return
    try:
        icon.title = title
    except Exception:
        logger.exception("Could not update tray title")


def _watch_until_sarthi_exits(listener: WakeWordListener) -> None:
    """Wait for Sarthi to exit, then resume the listener.

    Phase 1 waits for the API to come up (gives start.bat time to boot
    the server). Phase 2 waits for it to go away again, which is how we
    know Sarthi has been closed. The listener stays dormant throughout.
    """
    start_timeout = getattr(variable, "SARTHI_START_TIMEOUT", 90)
    poll = getattr(variable, "SARTHI_POLL_INTERVAL", 3.0)

    deadline = time.monotonic() + start_timeout
    while time.monotonic() < deadline:
        if _sarthi_is_up():
            break
        time.sleep(poll)
    else:
        logger.warning(
            "Sarthi never came up within %ss — resuming listener.", start_timeout
        )
        _clear_cooldown()
        listener.resume()
        return

    logger.info("Sarthi is running — listener dormant until it exits.")
    _set_tray_title("Sarthi Wake Word — dormant (Sarthi running)")

    while _sarthi_is_up():
        time.sleep(poll)

    logger.info("Sarthi exited — resuming listener.")
    _clear_cooldown()
    _set_tray_title("Sarthi Wake Word")
    listener.resume()


def _enter_dormancy() -> None:
    """Pause the listener and wake it again once Sarthi exits.

    Called right after a successful launch. The listener stops using the
    microphone and a background watcher resumes it when Sarthi's API
    stops responding. Disabled via variable.DORMANT_WHILE_RUNNING.
    """
    if not getattr(variable, "DORMANT_WHILE_RUNNING", True):
        logger.info("Dormant mode disabled — keeping the listener awake.")
        return
    if _listener is None:
        logger.warning("No active listener — cannot enter dormant mode.")
        return
    if _listener.dormant:
        logger.info("Already dormant — a watcher is already running.")
        return
    _listener.pause("Sarthi launched")
    threading.Thread(
        target=_watch_until_sarthi_exits,
        args=(_listener,),
        daemon=True,
        name="sarthi-watch",
    ).start()


# ------------------------------------------------------------------
# Single-instance lock (prevents two listeners from running at once)
# ------------------------------------------------------------------


def _open_process(pid: int) -> Any:
    """Open a handle to the process with the given PID (0 if not found)."""
    if sys.platform != "win32":
        return 0
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    kernel32 = ctypes.windll.kernel32
    try:
        # HANDLEs are 64-bit; without a restype the pointer gets truncated
        # to a 32-bit int on 64-bit Windows.
        kernel32.OpenProcess.restype = ctypes.wintypes.HANDLE
    except AttributeError:
        pass  # windll is faked in tests
    return kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)


def _close_process(handle: Any) -> None:
    """Close a process handle, ignoring failures (e.g. raced/invalid handles)."""
    try:
        if handle:
            ctypes.windll.kernel32.CloseHandle(handle)
    except Exception:
        pass


def _process_is_alive(pid: int) -> bool:
    """Return True if a process with the given PID is running."""
    if pid <= 0:
        return False
    if sys.platform == "win32":
        # NOTE: os.kill(pid, 0) would KILL the process on Windows, so
        # OpenProcess is used to check existence instead.
        handle = _open_process(pid)
        if not handle:
            return False
        _close_process(handle)
        return True
    # Non-Windows: os.kill(pid, 0) probes existence without signalling.
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except OSError:
        return True  # e.g. PermissionError — the process exists



def _process_is_python(pid: int) -> bool:
    """Return True if the process with the given PID is a Python interpreter.

    The pid file can outlive its owner (crash, reboot), after which the PID
    can be reused by an unrelated process. Requiring the lock owner to
    actually be Python prevents a stale lock from blocking the listener
    forever. On non-Windows platforms this check is skipped (always True).
    """
    if sys.platform != "win32" or pid <= 0:
        return True
    handle = _open_process(pid)
    if not handle:
        return False
    try:
        kernel32 = ctypes.windll.kernel32
        try:
            kernel32.QueryFullProcessImageNameW.argtypes = [
                ctypes.wintypes.HANDLE,
                ctypes.wintypes.DWORD,
                ctypes.wintypes.LPWSTR,
                ctypes.POINTER(ctypes.wintypes.DWORD),
            ]
            kernel32.QueryFullProcessImageNameW.restype = ctypes.wintypes.BOOL
        except AttributeError:
            pass  # windll is faked in tests
        buf = ctypes.create_unicode_buffer(1024)
        size = ctypes.wintypes.DWORD(len(buf))
        if not kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
            return False
        return Path(buf.value).name.lower().startswith("python")
    finally:
        _close_process(handle)


def _read_lock_pid() -> int | None:
    """Read the pid stored in the lock file, or None if unreadable."""
    try:
        return int(LOCK_FILE.read_text(encoding="utf-8").strip())
    except (ValueError, OSError):
        return None


def _acquire_lock() -> bool:
    """Try to take the single-instance lock (atomically).

    The pid file is created with O_CREAT|O_EXCL, so two listeners that
    start at the same instant cannot both succeed (the old check-then-
    write raced). A stale lock — one whose owner is dead or no longer a
    Python process — is cleared and the create retried once, so a
    leftover pid file (crash/reboot + PID reuse) never blocks startup.

    Returns:
        True if this process now owns the lock, False if another wake
        word listener is already running.
    """
    for _ in range(2):
        try:
            fd = os.open(str(LOCK_FILE), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
            os.write(fd, str(os.getpid()).encode("ascii"))
            os.close(fd)
            return True
        except FileExistsError:
            other = _read_lock_pid()
            if other and _process_is_alive(other) and _process_is_python(other):
                return False
            try:
                LOCK_FILE.unlink()  # stale — clear and retry once
            except OSError:
                return False
        except OSError:
            return False
    return False


def _release_lock() -> None:
    """Release the lock if this process still owns it."""
    try:
        if LOCK_FILE.exists():
            if LOCK_FILE.read_text(encoding="utf-8").strip() == str(os.getpid()):
                LOCK_FILE.unlink()
    except OSError:
        pass


# ------------------------------------------------------------------
# System tray icon (pystray + Pillow)
# ------------------------------------------------------------------


def _make_icon() -> Any:
    """Draw a small microphone icon for the tray (no asset file needed)."""
    from PIL import Image, ImageDraw

    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    blue = (59, 130, 246, 255)
    dark = (30, 58, 138, 255)
    d.rounded_rectangle((22, 8, 42, 36), radius=10, fill=blue)  # mic capsule
    d.rectangle((29, 30, 35, 38), fill=blue)  # capsule -> stand connector
    d.rectangle((30, 38, 34, 48), fill=dark)  # stand
    d.rounded_rectangle((18, 48, 46, 54), radius=3, fill=dark)  # base
    return img


def _pids_listening_on(port: int) -> list[int]:
    """Return the PIDs of processes LISTENING on a TCP port (netstat)."""
    pids: set[int] = set()
    try:
        out = subprocess.check_output(
            ["netstat", "-ano"],
            text=True,
            errors="replace",
            creationflags=_NO_WINDOW,
        )
    except OSError:
        return []
    for line in out.splitlines():
        if f":{port} " in line and "LISTENING" in line.upper():
            parts = line.split()
            if parts and parts[-1].isdigit():
                pids.add(int(parts[-1]))
    return sorted(pids)


def _stop_sarthi(_icon: Any = None, _item: Any = None) -> None:
    """Stop the running Sarthi API/UI servers (tray menu item).

    Terminates the processes listening on the Sarthi ports; the dormant-
    mode watcher then notices Sarthi is gone and resumes the listener.
    """
    stopped: list[int] = []
    for port in (8000, 5500):
        for pid in _pids_listening_on(port):
            try:
                os.kill(pid, signal.SIGTERM)
                stopped.append(pid)
            except OSError:
                logger.exception("Could not stop Sarthi process %s", pid)
    if stopped:
        logger.info("Stopped Sarthi process(es): %s", ", ".join(map(str, stopped)))
    else:
        logger.info("Stop Sarthi: nothing was running on ports 8000/5500.")


def _open_log(log_file: str | None = None) -> None:
    """Open the wake word log file in the default text editor."""
    log_path = Path(log_file).resolve() if log_file else ROOT / "logs" / "wakeword.log"
    if sys.platform == "win32" and log_path.exists():
        os.startfile(str(log_path))  # type: ignore[attr-defined]
    else:
        logger.warning(
            "Cannot open log at %s (exists=%s, platform=%s)",
            log_path,
            log_path.exists(),
            sys.platform,
        )


def _build_tray_icon(listener: WakeWordListener, log_file: str | None = None) -> Any:
    """Build the system tray icon and its menu for the background listener."""
    import pystray

    def tray_exit(icon: Any, _item: Any) -> None:
        logger.info("Tray Exit clicked — stopping listener.")
        listener.stop()
        icon.stop()

    menu = pystray.Menu(
        pystray.MenuItem(
            "Listening for: " + ", ".join(listener.wake_words), None, enabled=False
        ),
        pystray.MenuItem("Launch Sarthi", lambda _i, _it: launch_sarthi(), default=True),
        pystray.MenuItem(
            "Stop Sarthi",
            lambda _i, _it: _stop_sarthi(),
            enabled=lambda _item: _sarthi_is_up(),  # pystray passes the item
        ),
        pystray.MenuItem("Open log", lambda _i, _it: _open_log(log_file)),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Exit", tray_exit),
    )
    return pystray.Icon("sarthi_wakeword", _make_icon(), "Sarthi Wake Word", menu=menu)


def _run_with_tray(listener: WakeWordListener, log_file: str | None = None) -> int:
    """Run the listener with a system tray icon (blocks until Exit).

    Returns exit code 3 so the background launcher (wakeword.bat) knows the
    user stopped it on purpose and should not restart it.
    """
    global _tray_icon

    try:
        import pystray  # noqa: F401 - availability check only
    except ImportError:
        logger.error(
            "Tray icon unavailable (install pystray + pillow) — running without tray."
        )
        print("⚠️  Tray unavailable (pip install pystray pillow) — running without tray.")
        try:
            listener.listen_forever()
        except KeyboardInterrupt:
            listener.stop()
        return 3

    icon = _build_tray_icon(listener, log_file)
    _tray_icon = icon
    original_on_wake = listener.on_wake

    def on_wake_with_notify(text: str) -> None:
        original_on_wake(text)
        try:
            icon.notify("Wake word detected — launching Sarthi", "Sarthi")
        except Exception:
            logger.exception("Tray notification failed")

    listener.on_wake = on_wake_with_notify

    def _run_icon() -> None:
        """Run the tray icon, logging any failure (stderr is None under pythonw)."""
        try:
            icon.run()
        except Exception:
            logger.exception("Tray icon failed to run")

    threading.Thread(target=_run_icon, daemon=True, name="tray").start()
    logger.info("Tray icon active — right-click it to stop the listener.")

    try:
        listener.listen_forever()
    except KeyboardInterrupt:
        listener.stop()
    finally:
        _tray_icon = None
        icon.stop()

    logger.info("Listener stopped from the tray.")
    return 3


# ------------------------------------------------------------------
# Supervisor (windowless watchdog)
# ------------------------------------------------------------------


def _supervise(args: argparse.Namespace) -> int:
    """Windowless supervisor — restart the tray listener if it crashes.

    Replaces wakeword.bat's old ``:loop`` watchdog, which needed a
    visible (minimized) console window to host the batch loop. This loop
    runs inside wakeword.py, so the entire background stack is pythonw
    and no console is ever created.

    Exit code contract (identical to the old batch loop):
        2 = another listener already owns the single-instance lock → stop
        3 = the user exited from the tray                       → stop
        anything else = crash → restart after 5 seconds
    """
    script = Path(__file__).resolve()
    log_file = args.log_file or str(ROOT / "logs" / "wakeword.log")

    try:
        while True:
            cmd = [sys.executable, str(script), "--tray", "--log-file", log_file]
            logger.info("Supervisor spawning listener: %s", " ".join(cmd))
            try:
                proc = subprocess.Popen(
                    cmd, cwd=str(ROOT), creationflags=_NO_WINDOW
                )
            except OSError as e:
                logger.error("Supervisor could not spawn listener: %s", e)
                time.sleep(5.0)
                continue
            code = proc.wait()
            if code in (2, 3):
                logger.info(
                    "Listener exited deliberately (code %s) — supervisor stopping.",
                    code,
                )
                return code
            logger.warning(
                "Listener exited unexpectedly (code %s) — restarting in 5s.", code
            )
            time.sleep(5.0)
    except KeyboardInterrupt:
        logger.info("Supervisor stopped by user (Ctrl+C).")
        return 3


# ------------------------------------------------------------------
# Main
# ------------------------------------------------------------------


def _listen(args: argparse.Namespace) -> int:
    """Run the listener (called after the lock is acquired)."""
    global _listener

    model = getattr(variable, "WHISPER_MODEL", "tiny")
    wake_words = getattr(variable, "WAKE_WORDS", ["hey sarthi"])
    energy_threshold = getattr(variable, "ENERGY_THRESHOLD", 0.015)
    chunk_duration = getattr(variable, "CHUNK_DURATION", 0.5)
    max_utterance = getattr(variable, "MAX_UTTERANCE", 6.0)
    silence_pause = getattr(variable, "SILENCE_PAUSE", 0.8)

    # Fail fast with a friendly message if no microphone is available
    try:
        import sounddevice as sd

        sd.check_input_settings()
    except Exception as e:
        logger.error("No microphone available: %s", e)
        print(f"❌ No microphone available: {e}")
        print("   Plug in a microphone and try again.")
        return 1

    # Pre-load the configured (lightweight) Whisper model before listening
    logger.info("Loading Whisper model '%s'...", model)
    try:
        get_model(model=model)
    except Exception as e:
        logger.error("Could not load Whisper model: %s", e)
        print(f"❌ Could not load Whisper model: {e}")
        return 1

    banner = "=" * 58
    print(banner)
    print("🎙️  Sarthi Wake Word Launcher")
    print("    Say:  " + "  |  ".join(wake_words))
    print("    Model: " + model)
    print("    Stop: Ctrl+C")
    print(banner)
    logger.info("Listening for: %s (model=%s)", ", ".join(wake_words), model)

    listener = WakeWordListener(
        wake_words,
        on_wake=launch_sarthi,
        energy_threshold=energy_threshold,
        chunk_duration=chunk_duration,
        max_utterance=max_utterance,
        silence_pause=silence_pause,
    )
    _listener = listener

    try:
        if args.once:
            text = listener.listen_once(timeout=30)
            if text:
                print(f"🗣️  Heard: {text}")
                if wake_word_matches(text, wake_words):
                    launch_sarthi()
            else:
                print("🤫 No speech detected.")
            return 0

        if args.tray:
            return _run_with_tray(listener, args.log_file)

        listener.listen_forever()
    except KeyboardInterrupt:
        listener.stop()
        print("\n👋 Stopped.")
    return 0


def main() -> int:
    # Emoji prints must never crash the listener — force UTF-8 output even
    # when stdout is a pipe/redirect (Windows defaults to cp1252 there).
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="Sarthi wake word launcher")
    parser.add_argument(
        "--once",
        action="store_true",
        help="listen for a single wake word, then exit",
    )
    parser.add_argument(
        "--log-file",
        metavar="PATH",
        help="append logs to a file (used by wakeword.bat background mode)",
    )
    parser.add_argument(
        "--tray",
        action="store_true",
        help="show a system tray icon to launch/stop Sarthi (background mode)",
    )
    parser.add_argument(
        "--supervise",
        action="store_true",
        help=(
            "windowless supervisor: run the tray listener as a child and "
            "restart it if it crashes (used by wakeword.bat background mode)"
        ),
    )
    args = parser.parse_args()

    setup_logging(log_file=Path(args.log_file) if args.log_file else None)

    # Under pythonw (background mode) there is no console: sys.stdout and
    # sys.stderr are None, which would crash every print() call below.
    # Route them to devnull so the listener never dies on a print.
    # (Detachment from the caller's console/pipes is handled by
    # wakeword.bat, which respawns us with DEVNULL stdio.)
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")

    # The supervisor never takes the lock itself — its child listener does.
    if args.supervise:
        return _supervise(args)

    if not _acquire_lock():
        print("🔒 Another wake word listener is already running.")
        logger.info("Another wake word listener is already running — exiting.")
        return 2

    try:
        return _listen(args)
    finally:
        _release_lock()


if __name__ == "__main__":
    raise SystemExit(main())
