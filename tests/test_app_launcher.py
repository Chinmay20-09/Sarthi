"""Tests for safe application launching.

Regression: the launcher used ``subprocess.Popen(app_path, shell=True)``,
which passed the path through cmd.exe. Paths with shell metacharacters could
have been interpreted as commands. The launcher must now:
    - launch .exe targets with a list-form Popen (CreateProcess, no shell)
    - launch every other target (.lnk, .bat, URLs) with os.startfile
      (ShellExecute — also no shell)
"""

from brain.intent import Intent
from skills.app_launcher.main import AppLauncherSkill


def test_exe_launched_with_list_form_popen(monkeypatch):
    """An .exe target is started via Popen([path]) — a list, never a string."""
    captured = {}

    def fake_popen(args, **kwargs):
        captured["args"] = args
        captured["shell"] = kwargs.get("shell")

    monkeypatch.setattr("skills.app_launcher.main.subprocess.Popen", fake_popen)
    monkeypatch.setattr("skills.app_launcher.main.os.startfile", lambda p: captured.setdefault("startfile", p))

    AppLauncherSkill._launch_path(r"C:\Program Files\Chrome\chrome.exe")

    assert captured["args"] == [r"C:\Program Files\Chrome\chrome.exe"]
    assert captured["shell"] is not True  # shell is not passed at all
    assert "startfile" not in captured


def test_lnk_launched_with_startfile(monkeypatch):
    """A .lnk shortcut (not creatable via CreateProcess) uses os.startfile."""
    captured = {}

    def fake_startfile(path):
        captured["startfile"] = path

    monkeypatch.setattr("skills.app_launcher.main.subprocess.Popen", lambda *a, **k: captured.setdefault("popen", True))
    monkeypatch.setattr("skills.app_launcher.main.os.startfile", fake_startfile)

    AppLauncherSkill._launch_path(r"C:\ProgramData\Microsoft\Windows\Start Menu\Chrome.lnk")

    assert captured["startfile"] == r"C:\ProgramData\Microsoft\Windows\Start Menu\Chrome.lnk"
    assert "popen" not in captured


def test_launch_case_insensitive_for_exe(monkeypatch):
    """Exe detection is case-insensitive (APP.EXE, .Exe)."""
    captured = {}

    def fake_popen(args, **kwargs):
        captured["args"] = args

    monkeypatch.setattr("skills.app_launcher.main.subprocess.Popen", fake_popen)
    monkeypatch.setattr("skills.app_launcher.main.os.startfile", lambda p: captured.setdefault("startfile", p))

    AppLauncherSkill._launch_path("C:\\Tools\\MYAPP.EXE")

    assert captured["args"] == ["C:\\Tools\\MYAPP.EXE"]
    assert "startfile" not in captured


class _FakeKnowledge:
    """Knowledge stand-in that always finds one favourite app."""

    def __init__(self, path):
        self.path = path

    def find_application(self, target):
        return {"name": "My App", "path": self.path, "app_status": "favourite"}


def test_execute_launches_favourite_via_safe_path(monkeypatch):
    """execute() routes the stored path through the safe launcher."""
    captured = {}

    def fake_popen(args, **kwargs):
        captured["args"] = args
        captured["shell"] = kwargs.get("shell")

    monkeypatch.setattr("skills.app_launcher.main.subprocess.Popen", fake_popen)

    skill = AppLauncherSkill(knowledge_manager=_FakeKnowledge(r"C:\Apps\thing.exe"))
    result = skill.execute(Intent(action="open", target="thing"))

    assert result["success"] is True
    assert captured["args"] == [r"C:\Apps\thing.exe"]
    assert captured["shell"] is not True  # never shell=True


def test_execute_launch_failure_is_graceful(monkeypatch):
    """A missing/invalid path surfaces as a safe error, not an exception leak."""

    def boom(path):
        raise FileNotFoundError(path)

    monkeypatch.setattr("skills.app_launcher.main.os.startfile", boom)

    skill = AppLauncherSkill(knowledge_manager=_FakeKnowledge(r"C:\Nope\missing.lnk"))
    result = skill.execute(Intent(action="open", target="thing"))

    assert result["success"] is False
    assert result["status"] == "error"
    assert "missing.lnk" in result["error"]


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])
