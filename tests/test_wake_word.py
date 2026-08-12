"""Tests for speech/wake_word.py — matching logic and listener loop.

These tests never touch the microphone: the listener is tested with
injected fake record/transcribe functions.
"""

import os
import threading
import time

import numpy as np

from speech.wake_word import WakeWordListener, wake_word_matches

LOUD = np.full(8000, 0.1, dtype=np.float32)  # ~0.5s of "speech" at 16 kHz
QUIET = np.zeros(8000, dtype=np.float32)  # digital silence


class TestWakeWordMatches:
    def test_exact_match(self):
        assert wake_word_matches("hey sarthi", ["hey sarthi"]) is True

    def test_case_insensitive(self):
        assert wake_word_matches("Hey Sarthi, open chrome", ["hey sarthi"]) is True

    def test_punctuation_tolerant(self):
        assert wake_word_matches("hey sarthi.", ["hey sarthi"]) is True
        assert wake_word_matches("hey, sarthi", ["hey sarthi"]) is True
        assert wake_word_matches("hey! sarthi?", ["hey sarthi"]) is True

    def test_inside_sentence(self):
        assert wake_word_matches("please open the browser hey sarthi", ["hey sarthi"]) is True

    def test_no_match(self):
        assert wake_word_matches("open chrome", ["hey sarthi"]) is False

    def test_multiple_wake_words(self):
        assert wake_word_matches("okay sarthi", ["hey sarthi", "okay sarthi"]) is True

    def test_single_word_does_not_match_inside_longer_word(self):
        assert wake_word_matches("they are here", ["hey"]) is False

    def test_empty_inputs(self):
        assert wake_word_matches("", ["hey sarthi"]) is False
        assert wake_word_matches("hello", []) is False


class TestWakeWordListener:
    def test_listen_once_transcribes_speech(self):
        chunks = iter([LOUD, LOUD, LOUD, QUIET, QUIET])
        listener = WakeWordListener(
            ["hey sarthi"],
            record_fn=lambda d: next(chunks, QUIET),
            transcribe_fn=lambda audio: "hey sarthi",
        )
        assert listener.listen_once() == "hey sarthi"

    def test_silence_skips_transcription(self):
        def transcribe(audio):  # pragma: no cover - must not be called
            raise AssertionError("silence should not be transcribed")

        listener = WakeWordListener(
            ["hey sarthi"],
            record_fn=lambda d: QUIET,
            transcribe_fn=transcribe,
        )
        assert listener.listen_once(timeout=1.0) is None

    def test_forever_calls_on_wake_and_stops(self):
        state = {"chunks": [LOUD, LOUD, LOUD, QUIET, QUIET], "calls": 0}

        def record(d):
            if state["chunks"]:
                return state["chunks"].pop(0)
            return QUIET

        def on_wake(text):
            state["calls"] += 1
            listener.stop()

        listener = WakeWordListener(
            ["hey sarthi"],
            on_wake=on_wake,
            record_fn=record,
            transcribe_fn=lambda audio: "hey sarthi",
        )
        listener.listen_forever(publish_event=False)

        assert state["calls"] == 1
        assert listener._stop is True

    def test_forever_ignores_non_matching_speech(self):
        state = {"chunks": [LOUD, LOUD, QUIET, QUIET], "calls": 0}

        def record(d):
            if state["chunks"]:
                return state["chunks"].pop(0)
            return QUIET

        def on_wake(text):
            state["calls"] += 1

        listener = WakeWordListener(
            ["hey sarthi"],
            on_wake=on_wake,
            record_fn=record,
            transcribe_fn=lambda audio: "open chrome",
        )

        # One full utterance cycle must not trigger the callback
        text = listener.listen_once()
        assert text == "open chrome"
        assert wake_word_matches(text, listener.wake_words) is False
        assert state["calls"] == 0

    def test_stop_flag_halts_listening(self):
        listener = WakeWordListener(["hey sarthi"], record_fn=lambda d: QUIET)
        assert listener._stop is False
        listener.stop()
        assert listener._stop is True

    def test_accepts_single_string_wake_word(self):
        listener = WakeWordListener("hey sarthi")
        assert listener.wake_words == ["hey sarthi"]

    def test_normalizes_and_filters_wake_words(self):
        listener = WakeWordListener([" Hey Sarthi ", "", "  "])
        assert listener.wake_words == ["hey sarthi"]

    def test_rms_of_silence_is_zero(self):
        assert WakeWordListener._rms(QUIET) == 0.0

    def test_rms_of_loud_chunk_is_positive(self):
        assert WakeWordListener._rms(LOUD) > 0.0

    def test_tiny_chunk_duration_is_clamped(self):
        listener = WakeWordListener(["hey sarthi"], chunk_duration=0)
        assert listener.chunk_duration >= 0.1


class TestDormantMode:
    """Tests for WakeWordListener.pause()/resume() dormant mode."""

    def test_pause_and_resume_flip_dormant_flag(self):
        listener = WakeWordListener(["hey sarthi"])
        assert listener.dormant is False
        listener.pause("Sarthi running")
        assert listener.dormant is True
        listener.resume()
        assert listener.dormant is False

    def test_listen_once_returns_none_while_dormant(self):
        def no_mic(d):
            raise AssertionError("microphone must not be used while dormant")

        listener = WakeWordListener(["hey sarthi"], record_fn=no_mic)
        listener.pause()
        assert listener.listen_once(timeout=1.0) is None

    def test_forever_skips_mic_while_dormant_then_resumes(self):
        state = {"mic_calls": 0, "before_resume": 0, "resumed": False}

        def record(d):
            state["mic_calls"] += 1
            if not state["resumed"]:
                state["before_resume"] += 1  # mic used while dormant == bug
            return QUIET

        listener = WakeWordListener(
            ["hey sarthi"],
            record_fn=record,
            transcribe_fn=lambda audio: "hey sarthi",
        )
        listener.pause("test")

        def lifecycle():
            time.sleep(0.4)
            state["resumed"] = True
            listener.resume()
            time.sleep(0.4)
            listener.stop()

        threading.Thread(target=lifecycle, daemon=True).start()
        listener.listen_forever(publish_event=False)

        assert state["resumed"] is True
        assert state["before_resume"] == 0  # mic untouched while dormant
        assert state["mic_calls"] > 0  # mic used again after resume


def test_launch_sarthi_accepts_text_arg(monkeypatch):
    """Regression: on_wake callbacks receive the detected text."""
    import wakeword

    calls = []
    monkeypatch.setattr(wakeword.subprocess, "Popen", lambda *a, **k: calls.append(a))
    wakeword.launch_sarthi("hey sarthi")  # must not raise TypeError
    assert calls, "start.bat should be launched"


def test_make_icon_returns_rgba_image():
    import wakeword

    img = wakeword._make_icon()
    assert img.size == (64, 64)
    assert img.mode == "RGBA"


def test_run_with_tray_falls_back_without_pystray(monkeypatch):
    import wakeword

    real_import = __import__

    def fake_import(name, *args, **kwargs):
        if name == "pystray":
            raise ImportError("no pystray")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", fake_import)

    listener = WakeWordListener(["hey sarthi"], record_fn=lambda d: QUIET)
    monkeypatch.setattr(listener, "listen_forever", lambda: None)
    # Without a tray the launcher must not restart the listener (exit 3)
    assert wakeword._run_with_tray(listener) == 3


def test_run_with_tray_wraps_on_wake_and_notifies(monkeypatch):
    """Tray mode: on_wake still launches Sarthi and also fires a notification."""
    import wakeword

    calls = {"launch": 0, "notify": 0}
    real_import = __import__

    class FakeIcon:
        def __init__(self, *args, **kwargs):
            pass

        def run(self):
            pass

        def stop(self):
            pass

        def notify(self, message, title):
            calls["notify"] += 1

    class FakePystray:
        class Menu:
            SEPARATOR = object()

            def __init__(self, *items):
                self.items = items

        class MenuItem:
            def __init__(self, *args, **kwargs):
                pass

        Icon = FakeIcon

    def fake_import(name, *args, **kwargs):
        if name == "pystray":
            return FakePystray
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", fake_import)

    listener = WakeWordListener(
        ["hey sarthi"],
        on_wake=lambda t: calls.__setitem__("launch", calls["launch"] + 1),
        record_fn=lambda d: QUIET,
    )
    monkeypatch.setattr(listener, "listen_forever", listener.stop)

    assert wakeword._run_with_tray(listener) == 3

    # After tray mode, on_wake is wrapped: it launches Sarthi AND notifies
    listener.on_wake("hey sarthi")
    assert calls["launch"] == 1
    assert calls["notify"] == 1


class TestDormancy:
    """Tests for wakeword.py's dormant-while-Sarthi-runs logic."""

    def test_launch_sarthi_enters_dormancy(self, monkeypatch):
        import wakeword

        monkeypatch.setattr(wakeword.subprocess, "Popen", lambda *a, **k: None)
        monkeypatch.setattr(wakeword, "_launched_at", 0.0)
        entered = {"value": False}
        monkeypatch.setattr(
            wakeword, "_enter_dormancy", lambda: entered.__setitem__("value", True)
        )

        assert wakeword.launch_sarthi("hey sarthi") is True
        assert entered["value"] is True

    def test_launch_sarthi_respects_cooldown(self, monkeypatch):
        import wakeword

        calls = []
        monkeypatch.setattr(
            wakeword.subprocess, "Popen", lambda *a, **k: calls.append(a)
        )
        monkeypatch.setattr(wakeword, "_launched_at", time.monotonic())
        entered = {"value": False}
        monkeypatch.setattr(
            wakeword, "_enter_dormancy", lambda: entered.__setitem__("value", True)
        )

        assert wakeword.launch_sarthi("hey sarthi") is False
        assert not calls
        assert entered["value"] is False

    def test_sarthi_is_up_when_health_responds(self, monkeypatch):
        import urllib.request

        import wakeword

        class FakeResp:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        def fake_urlopen(url, timeout):
            assert url == "http://127.0.0.1:8000/health"
            return FakeResp()

        monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
        assert wakeword._sarthi_is_up() is True

    def test_sarthi_is_down_when_health_fails(self, monkeypatch):
        import urllib.request

        import wakeword

        def fake_urlopen(url, timeout):
            raise OSError("connection refused")

        monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
        assert wakeword._sarthi_is_up() is False

    def test_enter_dormancy_pauses_listener_and_spawns_watcher(self, monkeypatch):
        import wakeword

        listener = WakeWordListener(["hey sarthi"])
        monkeypatch.setattr(wakeword, "_listener", listener)
        started = []
        monkeypatch.setattr(
            wakeword.threading.Thread, "start", lambda self: started.append(self)
        )

        wakeword._enter_dormancy()
        assert listener.dormant is True
        assert len(started) == 1
        assert started[0].name == "sarthi-watch"

    def test_enter_dormancy_respects_disabled_config(self, monkeypatch):
        import wakeword

        listener = WakeWordListener(["hey sarthi"])
        monkeypatch.setattr(wakeword, "_listener", listener)
        monkeypatch.setattr(wakeword.variable, "DORMANT_WHILE_RUNNING", False)

        wakeword._enter_dormancy()
        assert listener.dormant is False

    def test_enter_dormancy_skips_without_listener(self, monkeypatch):
        import wakeword

        monkeypatch.setattr(wakeword, "_listener", None)
        wakeword._enter_dormancy()  # must not raise

    def test_enter_dormancy_skips_when_already_dormant(self, monkeypatch):
        import wakeword

        listener = WakeWordListener(["hey sarthi"])
        listener.pause("already dormant")
        monkeypatch.setattr(wakeword, "_listener", listener)
        started = []
        monkeypatch.setattr(
            wakeword.threading.Thread, "start", lambda self: started.append(self)
        )

        wakeword._enter_dormancy()
        assert listener.dormant is True
        assert started == []  # no second watcher thread

    def test_watch_resumes_after_sarthi_exits(self, monkeypatch):
        import wakeword

        checks = {"n": 0}

        def fake_is_up():
            checks["n"] += 1
            return checks["n"] <= 3  # up for the first checks, then down

        monkeypatch.setattr(wakeword, "_sarthi_is_up", fake_is_up)
        monkeypatch.setattr(wakeword.variable, "SARTHI_POLL_INTERVAL", 0.01)
        monkeypatch.setattr(wakeword, "_set_tray_title", lambda t: None)
        monkeypatch.setattr(wakeword, "_launched_at", 123.0)

        listener = WakeWordListener(["hey sarthi"])
        state = {"resumed": False}
        monkeypatch.setattr(
            listener, "resume", lambda: state.__setitem__("resumed", True)
        )

        wakeword._watch_until_sarthi_exits(listener)
        assert state["resumed"] is True
        # Cooldown cleared so the wake word works immediately after exit
        assert wakeword._launched_at == 0.0

    def test_watch_resumes_if_sarthi_never_starts(self, monkeypatch):
        import wakeword

        monkeypatch.setattr(wakeword, "_sarthi_is_up", lambda: False)
        monkeypatch.setattr(wakeword.variable, "SARTHI_POLL_INTERVAL", 0.01)
        monkeypatch.setattr(wakeword.variable, "SARTHI_START_TIMEOUT", 0.05)
        monkeypatch.setattr(wakeword, "_set_tray_title", lambda t: None)
        monkeypatch.setattr(wakeword, "_launched_at", 123.0)

        listener = WakeWordListener(["hey sarthi"])
        state = {"resumed": False}
        monkeypatch.setattr(
            listener, "resume", lambda: state.__setitem__("resumed", True)
        )

        wakeword._watch_until_sarthi_exits(listener)
        assert state["resumed"] is True
        # Cooldown cleared so the user can retry the wake word immediately
        assert wakeword._launched_at == 0.0


class TestWindowlessLaunch:
    """wakeword.py launches Sarthi without any visible terminal."""

    def test_launch_sarthi_uses_background_no_window(self, monkeypatch):
        import wakeword

        captured = {}

        def fake_popen(*args, **kwargs):
            captured["args"] = args
            captured["kwargs"] = kwargs

        monkeypatch.setattr(wakeword.subprocess, "Popen", fake_popen)
        monkeypatch.setattr(wakeword, "_launched_at", 0.0)
        monkeypatch.setattr(wakeword, "_enter_dormancy", lambda: None)

        wakeword.launch_sarthi("hey sarthi")
        cmd = captured["args"][0]
        assert cmd[-1] == "background"  # start.bat's windowless mode
        assert captured["kwargs"].get("creationflags") == wakeword._NO_WINDOW


class TestStopSarthi:
    """Tray "Stop Sarthi" — finds and terminates the API/UI processes."""

    def test_pids_listening_on_parses_netstat(self, monkeypatch):
        import wakeword

        out = (
            "  TCP    127.0.0.1:8000         0.0.0.0:0              LISTENING       13344\r\n"
            "  TCP    [::]:8000              [::]:0                 LISTENING       13344\r\n"
            "  TCP    0.0.0.0:5500           0.0.0.0:0              LISTENING       20160\r\n"
        )
        monkeypatch.setattr(wakeword.subprocess, "check_output", lambda *a, **k: out)
        assert wakeword._pids_listening_on(8000) == [13344]
        assert wakeword._pids_listening_on(5500) == [20160]

    def test_stop_sarthi_kills_api_and_ui(self, monkeypatch):
        import wakeword

        by_port = {8000: [13344], 5500: [20160]}
        monkeypatch.setattr(wakeword, "_pids_listening_on", lambda p: by_port[p])
        killed = []
        monkeypatch.setattr(wakeword.os, "kill", lambda pid, sig: killed.append(pid))

        wakeword._stop_sarthi()
        assert sorted(killed) == [13344, 20160]


class TestSupervise:
    """wakeword.py --supervise — windowless watchdog (no console needed)."""

    def test_exits_without_restart_on_deliberate_exit(self, monkeypatch):
        import wakeword
        from types import SimpleNamespace

        calls = []

        class FakeProc:
            returncode = 3

            def wait(self):
                return self.returncode

        monkeypatch.setattr(
            wakeword.subprocess,
            "Popen",
            lambda cmd, **kw: (calls.append(cmd), FakeProc())[1],
        )

        args = SimpleNamespace(log_file="logs/x.log")
        assert wakeword._supervise(args) == 3
        assert len(calls) == 1
        assert "--tray" in calls[0]
        assert "--log-file" in calls[0]

    def test_exits_without_restart_on_lock_conflict(self, monkeypatch):
        import wakeword
        from types import SimpleNamespace

        calls = []

        class FakeProc:
            returncode = 2

            def wait(self):
                return self.returncode

        monkeypatch.setattr(
            wakeword.subprocess,
            "Popen",
            lambda cmd, **kw: (calls.append(cmd), FakeProc())[1],
        )

        assert wakeword._supervise(SimpleNamespace(log_file=None)) == 2
        assert len(calls) == 1

    def test_restarts_after_unexpected_crash(self, monkeypatch):
        import wakeword
        from types import SimpleNamespace

        codes = iter([1, 3])
        calls = []

        class FakeProc:
            def __init__(self):
                self.returncode = next(codes)

            def wait(self):
                return self.returncode

        monkeypatch.setattr(
            wakeword.subprocess,
            "Popen",
            lambda cmd, **kw: (calls.append(cmd), FakeProc())[1],
        )
        monkeypatch.setattr(wakeword.time, "sleep", lambda s: None)

        assert wakeword._supervise(SimpleNamespace(log_file=None)) == 3
        assert len(calls) == 2  # crashed once, then ran until deliberate exit


class TestSingleInstanceLock:
    """Tests for the wakeword.py background single-instance lock."""

    def test_process_is_alive_windows(self, monkeypatch):
        import wakeword

        monkeypatch.setattr(wakeword.sys, "platform", "win32")

        class FakeKernel:
            def __init__(self, alive):
                self.alive = alive

            def OpenProcess(self, access, inherit, pid):
                return 7 if self.alive else 0

            def CloseHandle(self, handle):
                pass

        monkeypatch.setattr(
            wakeword.ctypes, "windll", type("W", (), {"kernel32": FakeKernel(False)})()
        )
        assert wakeword._process_is_alive(1234) is False

        monkeypatch.setattr(
            wakeword.ctypes, "windll", type("W", (), {"kernel32": FakeKernel(True)})()
        )
        assert wakeword._process_is_alive(1234) is True

    def test_process_is_alive_posix(self, monkeypatch):
        import wakeword

        monkeypatch.setattr(wakeword.sys, "platform", "linux")

        def fake_kill(pid, sig):
            if pid == 999:
                raise ProcessLookupError

        monkeypatch.setattr(wakeword.os, "kill", fake_kill)
        assert wakeword._process_is_alive(999) is False
        assert wakeword._process_is_alive(1234) is True

    def test_process_is_alive_rejects_non_positive_pids(self):
        import wakeword

        assert wakeword._process_is_alive(0) is False
        assert wakeword._process_is_alive(-5) is False

    def test_lock_acquire_release(self, tmp_path, monkeypatch):
        import wakeword

        monkeypatch.setattr(wakeword, "LOCK_FILE", tmp_path / "wakeword.pid")
        assert wakeword._acquire_lock() is True
        # A second acquire from the same (live) process must be blocked
        assert wakeword._acquire_lock() is False
        wakeword._release_lock()
        assert not wakeword.LOCK_FILE.exists()
        assert wakeword._acquire_lock() is True
        wakeword._release_lock()

    def test_lock_stale_pid_is_ignored(self, tmp_path, monkeypatch):
        import wakeword

        lock = tmp_path / "wakeword.pid"
        monkeypatch.setattr(wakeword, "LOCK_FILE", lock)
        lock.write_text("12345")
        monkeypatch.setattr(wakeword, "_process_is_alive", lambda pid: False)
        assert wakeword._acquire_lock() is True
        assert lock.read_text(encoding="utf-8") == str(os.getpid())
        wakeword._release_lock()

    def test_process_is_python_windows(self, monkeypatch):
        """The lock owner must be a python.exe/pythonw.exe process."""
        import wakeword

        monkeypatch.setattr(wakeword.sys, "platform", "win32")

        class FakeKernel:
            def OpenProcess(self, access, inherit, pid):
                return 7

            def QueryFullProcessImageNameW(self, handle, flags, buf, size):
                buf.value = r"C:\Users\me\Sarthi\.venv\Scripts\pythonw.exe"
                return True

            def CloseHandle(self, handle):
                pass

        monkeypatch.setattr(
            wakeword.ctypes, "windll", type("W", (), {"kernel32": FakeKernel()})()
        )
        assert wakeword._process_is_python(1234) is True

    def test_process_is_python_rejects_other_exes(self, monkeypatch):
        """A stale PID reused by notepad.exe must not count as a listener."""
        import wakeword

        monkeypatch.setattr(wakeword.sys, "platform", "win32")

        class FakeKernel:
            def OpenProcess(self, access, inherit, pid):
                return 7

            def QueryFullProcessImageNameW(self, handle, flags, buf, size):
                buf.value = r"C:\Windows\System32\notepad.exe"
                return True

            def CloseHandle(self, handle):
                pass

        monkeypatch.setattr(
            wakeword.ctypes, "windll", type("W", (), {"kernel32": FakeKernel()})()
        )
        assert wakeword._process_is_python(1234) is False

    def test_process_is_python_skipped_off_windows(self, monkeypatch):
        import wakeword

        monkeypatch.setattr(wakeword.sys, "platform", "linux")
        assert wakeword._process_is_python(999) is True

    def test_lock_ignores_stale_pid_reused_by_other_program(
        self, tmp_path, monkeypatch
    ):
        """Regression: a stale pid whose PID was reused must not block."""
        import wakeword

        lock = tmp_path / "wakeword.pid"
        monkeypatch.setattr(wakeword, "LOCK_FILE", lock)
        lock.write_text("14652")  # alive, but not a Python process
        monkeypatch.setattr(wakeword, "_process_is_alive", lambda pid: True)
        monkeypatch.setattr(wakeword, "_process_is_python", lambda pid: False)
        assert wakeword._acquire_lock() is True
        assert lock.read_text(encoding="utf-8") == str(os.getpid())
        wakeword._release_lock()
