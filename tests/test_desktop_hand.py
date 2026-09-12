"""Tests for the Desktop hand (hands/desktop/).

The Desktop hand is Sarthi's physical execution layer. These tests lock:

    - capability registration and the static allow-list
    - invalid actions / invalid arguments rejected before execution
    - structured DesktopResult results on success AND failure
    - the launch/close/clipboard/keyboard/filesystem/process abstractions
    - [Desktop] action logging
    - Executor → Desktop delegation (the built-in close handler)

No test opens a real application, touches the real clipboard, moves the
mouse, or writes outside tmp_path — all OS backends are faked with
monkeypatch.
"""

import logging
from pathlib import Path

import pytest

from hands.desktop import DesktopHand
from hands.desktop.capabilities import ACTIONS, CAPABILITIES, PLANNED_CAPABILITIES, action_spec
from hands.desktop.filesystem import FilesystemBackend, FilesystemScopeError
from hands.desktop.models import DesktopResult

# ---------------------------------------------------------------------------
# Capability registration
# ---------------------------------------------------------------------------


class TestCapabilityRegistration:
    def test_every_registered_action_has_an_implementation(self):
        hand = DesktopHand()
        for action in ACTIONS:
            assert action in hand._actions, f"capability action {action!r} has no backend"

    def test_no_implementation_without_capability(self):
        """Every implemented action must be declared by a capability —
        the registry is the only source of truth."""
        hand = DesktopHand()
        for action in hand._actions:
            assert action in ACTIONS, f"undocumented action {action!r}"

    def test_planned_capabilities_are_not_registered(self):
        for cap_id in PLANNED_CAPABILITIES:
            assert cap_id not in CAPABILITIES

    def test_capability_report_shape(self):
        hand = DesktopHand()
        report = hand.capabilities()
        assert {c["id"] for c in report["implemented"]} == set(CAPABILITIES)
        assert report["planned"] == list(PLANNED_CAPABILITIES)
        for cap in report["implemented"]:
            assert cap["actions"] == sorted(cap["actions"])

    def test_action_spec_lookup(self):
        assert "path" in action_spec("open_application")
        assert action_spec("no_such_action") == {}


# ---------------------------------------------------------------------------
# Invalid actions / invalid arguments
# ---------------------------------------------------------------------------


class TestValidation:
    def test_unknown_action_rejected(self):
        hand = DesktopHand()
        result = hand.execute("launch_nuclear_missile")
        assert result["success"] is False
        assert result["error"] == "unknown_action"

    def test_unexpected_argument_rejected(self):
        hand = DesktopHand()
        result = hand.execute("open_url", url="https://x.com", shell_command="rm -rf /")
        assert result["success"] is False
        assert result["error"] == "invalid_arguments"

    def test_missing_required_argument_rejected(self):
        hand = DesktopHand()
        result = hand.execute("open_application")
        assert result["success"] is False
        assert "path" in result["message"]

    def test_wrong_argument_type_rejected(self):
        hand = DesktopHand()
        result = hand.execute("type_text", text=12345)
        assert result["success"] is False
        assert result["error"] == "invalid_arguments"

    def test_empty_string_argument_rejected(self):
        hand = DesktopHand()
        result = hand.execute("copy", text="   ")
        assert result["success"] is False

    def test_invalid_url_scheme_rejected(self):
        hand = DesktopHand()
        for url in ("file:///C:/Windows/system32", "javascript:alert(1)", "not a url"):
            result = hand.execute("open_url", url=url)
            assert result["success"] is False, url


# ---------------------------------------------------------------------------
# Structured results
# ---------------------------------------------------------------------------


class TestStructuredResults:
    def test_success_shape(self, monkeypatch):
        captured = {}

        def fake_launch(path):
            captured["path"] = path
            return type("P", (), {"pid": 4242})()

        monkeypatch.setattr("hands.desktop.processes.subprocess.Popen", fake_launch)
        hand = DesktopHand()
        result = hand.execute(
            "open_application", target="chrome", path=r"C:\Apps\chrome.exe", name="Chrome"
        )
        assert result["success"] is True
        assert result["action"] == "open_application"
        assert result["target"] == "chrome"
        assert "Chrome" in result["message"]
        assert result["data"]["pid"] == 4242

    def test_failure_shape_carries_error(self):
        hand = DesktopHand()
        result = hand.execute("open_url", url="ftp://bad.example")
        assert result["success"] is False
        assert result["action"] == "open_url"
        assert result["error"] == "execution_failed"
        assert result["message"]

    def test_desktop_result_model_helpers(self):
        ok = DesktopResult.ok("copy", "done", target="clip")
        assert ok.success and ok.action == "copy" and ok.target == "clip"
        bad = DesktopResult.fail("copy", "nope")
        assert not bad.success and bad.error == "nope"
        assert bad.to_dict()["error"] == "nope"
        assert "error" not in ok.to_dict()  # clean success dicts


# ---------------------------------------------------------------------------
# Application launch / close abstraction
# ---------------------------------------------------------------------------


class TestApplicationLaunch:
    def test_exe_launch_uses_list_form_popen(self, monkeypatch):
        captured = {}

        def fake_popen(args, **kwargs):
            captured["args"] = args
            captured["shell"] = kwargs.get("shell")
            return type("P", (), {"pid": 7})()

        monkeypatch.setattr("hands.desktop.processes.subprocess.Popen", fake_popen)
        result = DesktopHand().execute("open_application", path=r"C:\Apps\tool.exe")
        assert result["success"] is True
        assert captured["args"] == [r"C:\Apps\tool.exe"]
        assert captured["shell"] is not True  # never shell=True

    def test_launch_process_rejects_non_exe(self):
        hand = DesktopHand()
        result = hand.execute("launch_process", path=r"C:\Apps\thing.lnk")
        assert result["success"] is False
        assert result["error"] == "execution_failed"

    def test_launch_failure_is_structured(self, monkeypatch):
        def boom(path):
            raise OSError("access denied")

        monkeypatch.setattr("hands.desktop.processes.subprocess.Popen", boom)
        result = DesktopHand().execute("open_application", path=r"C:\Nope\app.exe")
        assert result["success"] is False
        assert result["error"] == "execution_failed"
        assert "access denied" in result["message"]


class TestApplicationClose:
    def _hand_with_procs(self, monkeypatch, procs):

        fake = [
            type("P", (), {"info": {"pid": p, "name": n, "memory_info": None}})() for p, n in procs
        ]
        monkeypatch.setattr(
            "hands.desktop.processes.psutil.process_iter", lambda *_a, **_k: iter(fake)
        )
        return DesktopHand()

    def test_find_application_process_matches_exe_name(self, monkeypatch):
        hand = self._hand_with_procs(monkeypatch, [(11, "chrome.exe"), (22, "code.exe")])
        matched = hand.find_application_process("chrome.exe")
        assert [p["pid"] for p in matched] == [11]

    def test_find_application_process_none_when_not_running(self, monkeypatch):
        hand = self._hand_with_procs(monkeypatch, [(11, "chrome.exe")])
        assert hand.find_application_process("steam.exe") is None

    def test_close_application_success(self, monkeypatch):
        terminated = []

        class FakeProc:
            def __init__(self, pid):
                self.pid = pid

            def is_running(self):
                return True

            def terminate(self):
                terminated.append(self.pid)

            def wait(self, timeout=None):
                return 0

        import psutil

        monkeypatch.setattr(psutil, "Process", lambda pid: FakeProc(pid))
        result = DesktopHand().execute("close_application", target="chrome", pid=11, name="Chrome")
        assert result["success"] is True
        assert terminated == [11]
        assert "Chrome" in result["message"]

    def test_close_application_unknown_pid_fails_cleanly(self, monkeypatch):
        import psutil

        class FakeProc:
            def __init__(self, pid):
                self.pid = pid

            def is_running(self):
                return False

        monkeypatch.setattr(psutil, "Process", lambda pid: FakeProc(pid))
        result = DesktopHand().execute("close_application", pid=999)
        assert result["success"] is False
        assert result["error"] == "not_found"


# ---------------------------------------------------------------------------
# Clipboard abstraction
# ---------------------------------------------------------------------------


class TestClipboard:
    def test_copy_places_text_on_clipboard(self, monkeypatch):
        store = {}

        class FakePyperclip:
            @staticmethod
            def copy(text):
                store["text"] = text

            @staticmethod
            def paste():
                return store.get("text", "")

        monkeypatch.setitem(__import__("sys").modules, "pyperclip", FakePyperclip)
        hand = DesktopHand()
        assert hand.execute("copy", text="payload")["success"] is True
        assert hand.execute("read_clipboard")["data"]["text"] == "payload"

    def test_paste_sends_ctrl_v(self, monkeypatch):
        calls = []

        class FakePyautogui:
            @staticmethod
            def hotkey(*keys, interval=0.0):
                calls.append(keys)

        monkeypatch.setitem(__import__("sys").modules, "pyautogui", FakePyautogui)
        result = DesktopHand().execute("paste")
        assert result["success"] is True
        assert calls == [("ctrl", "v")]

    def test_clipboard_backend_without_pyperclip_fails_gracefully(self, monkeypatch):
        monkeypatch.setitem(__import__("sys").modules, "pyperclip", None)
        result = DesktopHand().execute("read_clipboard")
        assert result["success"] is False
        assert result["error"] == "execution_failed"


# ---------------------------------------------------------------------------
# Keyboard abstraction
# ---------------------------------------------------------------------------


class TestKeyboard:
    def _fake_pyautogui(self, monkeypatch):
        calls = []

        class FakePyautogui:
            @staticmethod
            def typewrite(text, interval=0.0):
                calls.append(("type", text))

            @staticmethod
            def press(key):
                calls.append(("press", key))

            @staticmethod
            def hotkey(*keys, interval=0.0):
                calls.append(("hotkey", keys))

        monkeypatch.setitem(__import__("sys").modules, "pyautogui", FakePyautogui)
        return calls

    def test_type_text(self, monkeypatch):
        calls = self._fake_pyautogui(monkeypatch)
        result = DesktopHand().execute("type_text", text="hello world")
        assert result["success"] is True
        assert ("type", "hello world") in calls

    def test_press_key(self, monkeypatch):
        calls = self._fake_pyautogui(monkeypatch)
        assert DesktopHand().execute("press_key", key="enter")["success"] is True
        assert ("press", "enter") in calls

    def test_hotkey(self, monkeypatch):
        calls = self._fake_pyautogui(monkeypatch)
        assert DesktopHand().execute("hotkey", keys=["ctrl", "c"])["success"] is True
        assert ("hotkey", ("ctrl", "c")) in calls

    def test_keyboard_without_pyautogui_fails_gracefully(self, monkeypatch):
        monkeypatch.setitem(__import__("sys").modules, "pyautogui", None)
        result = DesktopHand().execute("type_text", text="hi")
        assert result["success"] is False
        assert result["error"] == "execution_failed"


# ---------------------------------------------------------------------------
# Filesystem validation
# ---------------------------------------------------------------------------


class TestFilesystem:
    def test_read_write_delete_inside_scope(self, tmp_path):
        fs = FilesystemBackend(allowed_roots=[str(tmp_path)])
        target = tmp_path / "notes" / "todo.txt"
        assert fs.write_file(target, "buy milk") == 8
        assert fs.read_file(target) == "buy milk"
        assert fs.list_directory(target.parent)[0]["name"] == "todo.txt"
        assert fs.delete_file(target) is True
        assert fs.delete_file(target) is False  # already gone

    def test_path_outside_roots_refused(self, tmp_path):
        fs = FilesystemBackend(allowed_roots=[str(tmp_path / "allowed")])
        with pytest.raises(FilesystemScopeError):
            fs.resolve_scoped(r"C:\Windows\system32\config")
        with pytest.raises(FilesystemScopeError):
            fs.resolve_scoped(tmp_path.parent / "elsewhere.txt")

    def test_traversal_stays_scoped(self, tmp_path):
        fs = FilesystemBackend(allowed_roots=[str(tmp_path)])
        with pytest.raises(FilesystemScopeError):
            fs.resolve_scoped(tmp_path / ".." / ".." / "Windows" / "system32")

    def test_delete_directory_refused(self, tmp_path):
        fs = FilesystemBackend(allowed_roots=[str(tmp_path)])
        (tmp_path / "folder").mkdir()
        assert fs.delete_file(tmp_path / "folder") is False  # only files, never dirs

    def test_hand_reports_out_of_scope_as_failure(self, tmp_path):
        hand = DesktopHand(allowed_roots=[str(tmp_path)])
        result = hand.execute("read_file", path=r"C:\Windows\win.ini")
        assert result["success"] is False
        assert result["error"] == "outside_scope"


# ---------------------------------------------------------------------------
# Process validation
# ---------------------------------------------------------------------------


class TestProcesses:
    def test_get_processes_returns_capped_snapshot(self, monkeypatch):
        import psutil

        class FakeProc:
            def __init__(self, pid, name):
                self.pid = pid
                self.info = {"pid": pid, "name": name, "memory_info": None}

        fake = [FakeProc(1, "a.exe"), FakeProc(2, "b.exe")]
        monkeypatch.setattr(psutil, "process_iter", lambda *_a, **_k: iter(fake))
        result = DesktopHand().execute("get_processes")
        assert result["success"] is True
        assert [p["pid"] for p in result["data"]["processes"]] == [1, 2]

    def test_terminate_process_explicit_pid_only(self, monkeypatch):
        import psutil

        killed = []

        class FakeProc:
            def __init__(self, pid):
                self.pid = pid

            def is_running(self):
                return True

            def terminate(self):
                killed.append(self.pid)

            def wait(self, timeout=None):
                return 0

        monkeypatch.setattr(psutil, "Process", lambda pid: FakeProc(pid))
        result = DesktopHand().execute("terminate_process", pid=42)
        assert result["success"] is True
        assert killed == [42]


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------


class TestLogging:
    def test_actions_are_logged(self, monkeypatch, caplog):
        class FakePyautogui:
            @staticmethod
            def typewrite(text, interval=0.0):
                pass

        monkeypatch.setitem(__import__("sys").modules, "pyautogui", FakePyautogui)
        with caplog.at_level(logging.INFO, logger="hands.desktop.hand"):
            DesktopHand().execute("type_text", text="hi")
        desktop_logs = [r.message for r in caplog.records if r.name == "hands.desktop.hand"]
        assert any("[Desktop] action=type_text" in m for m in desktop_logs)
        assert any("status=success" in m for m in desktop_logs)

    def test_failures_are_logged(self, monkeypatch, caplog):
        with caplog.at_level(logging.INFO, logger="hands.desktop.hand"):
            DesktopHand().execute("open_url", url="nope")
        assert any("status=failure" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# Executor → Desktop delegation
# ---------------------------------------------------------------------------


class _FakeKnowledge:
    """Knowledge stand-in resolving one app to a fixed path."""

    def __init__(self, apps):
        self._apps = apps

    def find_application(self, name):
        return self._apps.get(name.lower())


class TestExecutorDelegation:
    def _register_close_with_fakes(self, monkeypatch, knowledge, procs):
        import psutil

        fake = [
            type("P", (), {"pid": p, "name": n, "memory_info": None, "info": {}})()
            for p, n in procs
        ]
        monkeypatch.setattr(psutil, "process_iter", lambda *_a, **_k: iter(fake))
        monkeypatch.setattr("knowledge.manager.get_manager", lambda: knowledge)

        from brain.executor import BrainExecutor

        executor = BrainExecutor()
        # Drop the open/browse handlers' skill imports by only asserting close.
        return executor

    def test_close_handler_closes_matching_process(self, monkeypatch):
        knowledge = _FakeKnowledge(
            {"chrome": {"name": "Google Chrome", "path": r"C:\Apps\chrome.exe"}}
        )
        terminated = []

        class FakeProc:
            def __init__(self, pid):
                self.pid = pid

            def is_running(self):
                return True

            def terminate(self):
                terminated.append(self.pid)

            def wait(self, timeout=None):
                return 0

        import psutil

        fake = [type("P", (), {"info": {"pid": 11, "name": "chrome.exe", "memory_info": None}})()]
        monkeypatch.setattr(psutil, "process_iter", lambda *_a, **_k: iter(fake))
        monkeypatch.setattr(psutil, "Process", lambda pid: FakeProc(pid))
        monkeypatch.setattr("knowledge.manager.get_manager", lambda: knowledge)

        from brain.executor import BrainExecutor
        from brain.intent import Intent

        result = BrainExecutor().execute(Intent(action="close", target="chrome"))
        assert result["success"] is True
        assert result["result"]["action"] == "close_application"
        assert terminated == [11]

    def test_close_handler_unknown_app_is_structured_not_found(self, monkeypatch):
        monkeypatch.setattr("knowledge.manager.get_manager", lambda: _FakeKnowledge({}))

        from brain.executor import BrainExecutor
        from brain.intent import Intent

        result = BrainExecutor().execute(Intent(action="close", target="mystery"))
        assert result["success"] is False
        assert result["status"] == "not_found"

    def test_close_handler_reports_not_running(self, monkeypatch):
        knowledge = _FakeKnowledge(
            {"chrome": {"name": "Google Chrome", "path": r"C:\Apps\chrome.exe"}}
        )
        import psutil

        monkeypatch.setattr(psutil, "process_iter", lambda *_a, **_k: iter([]))
        monkeypatch.setattr("knowledge.manager.get_manager", lambda: knowledge)

        from brain.executor import BrainExecutor
        from brain.intent import Intent

        result = BrainExecutor().execute(Intent(action="close", target="chrome"))
        assert result["success"] is False
        assert result["status"] == "not_running"

    def test_open_flow_still_delegates_through_desktop(self, monkeypatch):
        """The existing open flow keeps working: knowledge → Desktop launch."""
        knowledge = _FakeKnowledge(
            {"chrome": {"name": "Google Chrome", "path": r"C:\Apps\chrome.exe"}}
        )
        launched = {}

        def fake_popen(args, **kwargs):
            launched["args"] = args
            return type("P", (), {"pid": 5})()

        import psutil

        monkeypatch.setattr(psutil, "process_iter", lambda *_a, **_k: iter([]))
        monkeypatch.setattr("hands.desktop.processes.subprocess.Popen", fake_popen)

        from brain.intent import Intent
        from skills.app_launcher.main import AppLauncherSkill

        skill = AppLauncherSkill(knowledge_manager=knowledge)
        result = skill.execute(Intent(action="open", target="chrome"))
        assert result["success"] is True
        assert launched["args"] == [r"C:\Apps\chrome.exe"]


# ---------------------------------------------------------------------------
# Architecture guards
# ---------------------------------------------------------------------------


class TestArchitectureGuards:
    def test_hand_has_no_reasoning_entry_points(self):
        """The hand exposes execute/capabilities/lookup — nothing else that
        could become a second brain."""
        hand = DesktopHand()
        public = {name for name in dir(hand) if not name.startswith("_")}
        assert public <= {"execute", "capabilities", "fs", "find_application_process"}

    def test_no_shell_execution_path_in_hand_package(self):
        """No module in the hand may run commands through a shell."""
        import hands.desktop.browser as b
        import hands.desktop.filesystem as f
        import hands.desktop.hand as h
        import hands.desktop.input as i
        import hands.desktop.models as m
        import hands.desktop.processes as p
        import hands.desktop.windows as w

        for mod in (b, f, h, i, m, p, w):
            source = Path(mod.__file__).read_text(encoding="utf-8")
            assert "shell=True" not in source, mod.__name__
            assert "os.system" not in source, mod.__name__
            assert "eval(" not in source and "exec(" not in source, mod.__name__

    def test_lazy_singleton_returns_same_instance(self):
        from hands.desktop.hand import get_desktop_hand

        assert get_desktop_hand() is get_desktop_hand()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
