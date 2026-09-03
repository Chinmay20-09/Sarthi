"""
Tests for the automation engine's ai_chain module.

Covers the pure logic (site resolution, command parsing, reply
extraction, run storage), the dry-run planner (never touches the
machine), and the AutomationSkill dispatch path — with run_ai_chain
mocked so no real laptop control is attempted.
"""

import pytest

from brain.intent import Intent
from skills.automation_engine.ai_chain.calibration import resolve_site
from skills.automation_engine.ai_chain.chain import run_ai_chain
from skills.automation_engine.ai_chain.control import AbortError
from skills.automation_engine.ai_chain.models import ChainOutcome, ChainRequest
from skills.automation_engine.ai_chain.parsing import extract_reply, parse_chain_command
from skills.automation_engine.ai_chain.storage import ChainRun, slugify
from skills.automation_engine.skill import AutomationSkill

# ----------------------------------------------------------------------
# Site resolution
# ----------------------------------------------------------------------


class TestResolveSite:
    def test_default_sites_exist(self):
        assert resolve_site("chatgpt").key == "chatgpt"
        assert resolve_site("gemini").key == "gemini"

    def test_aliases(self):
        assert resolve_site("gpt").key == "chatgpt"
        assert resolve_site("openai").key == "chatgpt"
        assert resolve_site("google gemini").key == "gemini"

    def test_unknown_site_raises(self):
        with pytest.raises(ValueError, match="Unknown AI"):
            resolve_site("clippy")

    def test_gemini_is_image_capable(self):
        assert resolve_site("gemini").image_capable is True
        assert resolve_site("chatgpt").image_capable is False


# ----------------------------------------------------------------------
# Command parsing
# ----------------------------------------------------------------------


class TestParseChainCommand:
    def test_defaults_when_no_from_to(self):
        req = parse_chain_command("chain write a poem about rain")
        assert req.ai1 == "chatgpt"
        assert req.ai2 == "gemini"
        assert "poem" in req.query

    def test_explicit_from_to(self):
        req = parse_chain_command(
            "chain make an image of the sarthi workflow from chatgpt to gemini"
        )
        assert req.ai1 == "chatgpt"
        assert req.ai2 == "gemini"
        assert "sarthi workflow" in req.query

    def test_reversed_order(self):
        req = parse_chain_command("automate a short story from gemini to chatgpt")
        assert req.ai1 == "gemini"
        assert req.ai2 == "chatgpt"
        assert "short story" in req.query

    def test_slash_command(self):
        req = parse_chain_command("/chain image of a dragon from chatgpt to gemini")
        assert req.ai1 == "chatgpt"
        assert req.ai2 == "gemini"

    def test_unknown_ai_falls_back_to_defaults(self):
        req = parse_chain_command("chain hello from clippy to claude")
        assert req.ai1 == "chatgpt"
        assert req.ai2 == "gemini"
        assert req.query  # whole text kept as query

    def test_aliases_in_sentence(self):
        req = parse_chain_command("chain a logo from google gemini to gpt")
        assert req.ai1 == "gemini"
        assert req.ai2 == "chatgpt"

    def test_open_chain_pattern(self):
        """'open <AI1> <query> ... to <AI2>' parses as a chain."""
        req = parse_chain_command(
            "open chatgpt and get prompt for making birthday invitation "
            "image prompt and sendit to gemini"
        )
        assert req.ai1 == "chatgpt"
        assert req.ai2 == "gemini"
        assert req.query == "get prompt for making birthday invitation image prompt"

    def test_open_chain_cleans_send_it_suffix(self):
        """Trailing 'and send it' filler is stripped from the query."""
        req = parse_chain_command("open chatgpt and write a poem and send it to gemini")
        assert req.ai1 == "chatgpt"
        assert req.ai2 == "gemini"
        assert req.query == "write a poem"


# ----------------------------------------------------------------------
# Reply extraction
# ----------------------------------------------------------------------


class TestExtractReply:
    def test_reply_after_prompt(self):
        transcript = "Chat page chrome\nuser: hello\nassistant: hi there, friend!"
        # The reply is everything the copy picked up after the sent prompt.
        assert extract_reply(transcript, "hello") == "assistant: hi there, friend!"

    def test_footer_marker_trimmed(self):
        transcript = "assistant: the sky is blue\nChatGPT can make mistakes. Check info."
        reply = extract_reply(transcript, "assistant:", ("ChatGPT can make mistakes",))
        assert "sky is blue" in reply
        assert "mistakes" not in reply

    def test_empty_transcript(self):
        assert extract_reply("", "prompt") == ""

    def test_prompt_not_found_best_effort(self):
        assert extract_reply("just some page text", "prompt") == "just some page text"

    def test_whitespace_tolerant_match(self):
        transcript = "Q:  prompt words\nA: answer text"
        assert extract_reply(transcript, "prompt words") == "A: answer text"


# ----------------------------------------------------------------------
# Run storage
# ----------------------------------------------------------------------


class TestChainRun:
    def test_slugify(self):
        assert slugify("Make an Image! of Sarthi") == "make-an-image-of-sarthi"
        assert slugify("!!!") == "run"

    def test_run_folder_writes_and_harvests(self, tmp_path):
        run = ChainRun("hello world", root=tmp_path)
        assert run.dir.exists()
        assert run.dir.name.startswith("20")  # timestamp prefix

        query_file = run.write_text("01_query.txt", "hello world")
        assert query_file.read_text(encoding="utf-8") == "hello world"

        source = tmp_path / "downloaded.png"
        source.write_bytes(b"png-bytes")
        kept = run.harvest_file(source)
        assert kept.exists()
        assert kept.read_bytes() == b"png-bytes"
        assert not source.exists()  # moved, not copied


# ----------------------------------------------------------------------
# Dry-run planner (never touches the machine)
# ----------------------------------------------------------------------


class TestDryRun:
    def test_planned_outcome(self):
        outcome = run_ai_chain(
            "make an image of the sarthi workflow",
            ai1="chatgpt",
            ai2="gemini",
            execute=False,
        )
        assert outcome.status == "planned"
        assert outcome.success is True
        assert outcome.run_dir is None
        assert len(outcome.steps) == 2
        assert "ChatGPT" in outcome.message
        assert "Gemini" in outcome.message

    def test_unknown_ai_is_reported_not_crashing(self):
        outcome = run_ai_chain("hello", ai1="clippy", ai2="gemini", execute=False)
        assert outcome.status == "failed"
        assert not outcome.success
        assert "clippy" in outcome.message

    def test_same_ai_rejected(self):
        with pytest.raises(ValueError, match="different sites"):
            run_ai_chain("hello", ai1="chatgpt", ai2="chatgpt", execute=False)


# ----------------------------------------------------------------------
# Browser window discovery (control.py)
# ----------------------------------------------------------------------


class _FakeWin32Gui:
    """win32gui stand-in: windows listed in EnumWindows order."""

    def __init__(self, windows, foreground):
        self._windows = windows  # [(hwnd, title), ...] in enum order
        self._foreground = foreground

    def IsWindowVisible(self, hwnd):
        return True

    def IsWindowEnabled(self, hwnd):
        return True

    def GetWindowText(self, hwnd):
        return dict(self._windows).get(hwnd, "")

    def EnumWindows(self, callback, _extra):
        for hwnd, _title in self._windows:
            callback(hwnd, None)
        return True

    def GetForegroundWindow(self):
        return self._foreground


def _require_fake(fake):
    """control._require replacement: only win32gui is available."""

    def _require(name):
        if name == "win32gui":
            return fake
        raise RuntimeError(f"Missing '{name}'")

    return _require


class TestFindWindow:
    def test_prefers_foreground_window(self, monkeypatch):
        """The window the user is looking at wins over other matches."""
        from skills.automation_engine.ai_chain import control

        fake = _FakeWin32Gui(
            windows=[(101, "ChatGPT - Old chat"), (102, "ChatGPT - New chat")],
            foreground=102,
        )
        monkeypatch.setattr(control, "_require", _require_fake(fake))
        ctrl = control.ScreenController(dry_run=True)
        assert ctrl._find_window("chatgpt") == 102

    def test_first_enumerated_hit_is_topmost(self, monkeypatch):
        """EnumWindows walks z-order; the first hit is the top-most window."""
        from skills.automation_engine.ai_chain import control

        fake = _FakeWin32Gui(
            windows=[(101, "ChatGPT"), (202, "Other app")],
            foreground=303,  # not a match
        )
        monkeypatch.setattr(control, "_require", _require_fake(fake))
        ctrl = control.ScreenController(dry_run=True)
        assert ctrl._find_window("chatgpt") == 101

    def test_open_site_reports_friendly_error_when_window_missing(self, monkeypatch):
        """A browser that never appears raises a clear message, not a crash."""
        import pytest

        from skills.automation_engine.ai_chain import control

        fake = _FakeWin32Gui(windows=[], foreground=0)
        monkeypatch.setattr(control, "_require", _require_fake(fake))
        monkeypatch.setattr(control, "WINDOW_FIND_TIMEOUT", 0.2)
        monkeypatch.setattr("webbrowser.open", lambda url: None)
        monkeypatch.setattr("skills.automation_engine.ai_chain.control.time.sleep", lambda s: None)

        ctrl = control.ScreenController(dry_run=False)
        with pytest.raises(RuntimeError, match="Could not find a browser window titled like 'ChatGPT'"):
            ctrl.open_site("https://chatgpt.com/", "ChatGPT", wait=1.0)


# ----------------------------------------------------------------------
# Sandbox recording (failed/aborted runs stay visible in the sandbox)
# ----------------------------------------------------------------------


class _AbortController:
    """ScreenController stand-in that aborts on the first check."""

    def check_abort(self):
        raise AbortError("Aborted by user (Ctrl+Alt+X).")

    def release(self):
        pass


def _tmp_sandbox(monkeypatch, tmp_path):
    """Point HERMES_SANDBOX_PATH at a temp dir and clear the config cache."""
    from hermes.config.loader import ConfigLoader

    monkeypatch.setenv("HERMES_SANDBOX_PATH", str(tmp_path))
    monkeypatch.setattr(ConfigLoader, "_cached", None)
    return tmp_path


class TestSandboxRecording:
    def test_aborted_chain_is_recorded_in_sandbox(self, monkeypatch, tmp_path):
        """A real run that aborts still lands in the sandbox index."""
        from hermes.sandbox import TaskSandbox

        root = _tmp_sandbox(monkeypatch, tmp_path)
        monkeypatch.setattr(
            "skills.automation_engine.ai_chain.chain.announce", lambda msg: None
        )

        outcome = run_ai_chain(
            "make a logo",
            ai1="chatgpt",
            ai2="gemini",
            execute=True,
            controller=_AbortController(),
        )

        assert outcome.status == "aborted"
        records = TaskSandbox(str(root)).lookup("make a logo")
        assert len(records) == 1
        assert records[0]["status"] == "error"
        assert records[0]["provider"] == "ai_chain"
        assert records[0]["model"] == "chatgpt -> gemini"

    def test_failed_chain_records_trace_and_error(self, monkeypatch, tmp_path):
        """A step failure keeps the error and trace in the sandbox record."""
        from hermes.sandbox import TaskSandbox
        from skills.automation_engine.ai_chain.chain import _save_to_sandbox
        from skills.automation_engine.ai_chain.models import StepOutcome

        root = _tmp_sandbox(monkeypatch, tmp_path)
        request = ChainRequest(
            query="birthday invitation image prompt", ai1="chatgpt", ai2="gemini"
        )
        step = StepOutcome(
            index=1,
            site_key="chatgpt",
            site_label="ChatGPT",
            prompt="birthday invitation image prompt",
            error="Could not find a browser window titled like 'ChatGPT'",
            duration_ms=6123,
        )
        outcome = ChainOutcome(
            request=request,
            success=False,
            status="failed",
            steps=[step],
            message="AI1 (ChatGPT) failed: Could not find a browser window titled like 'ChatGPT'",
        )

        _save_to_sandbox(request, outcome)

        sandbox = TaskSandbox(str(root))
        records = sandbox.lookup("birthday invitation image prompt")
        assert len(records) == 1
        task = sandbox.get_task(records[0]["task_id"])
        assert task is not None
        assert "Could not find a browser window" in task["response"]
        assert task["trace"] and task["trace"][0]["error"].startswith("Could not find")
        assert task["metadata"]["status"] == "error"

    def test_planned_run_never_touches_sandbox(self, monkeypatch, tmp_path):
        """Dry-run plans (test mode) are not recorded."""
        from hermes.sandbox import TaskSandbox

        root = _tmp_sandbox(monkeypatch, tmp_path)

        outcome = run_ai_chain(
            "make a logo", ai1="chatgpt", ai2="gemini", execute=False
        )

        assert outcome.status == "planned"
        assert TaskSandbox(str(root)).lookup("make a logo") == []


# ----------------------------------------------------------------------
# AutomationSkill dispatch (run_ai_chain mocked)
# ----------------------------------------------------------------------


class TestSkillDispatch:
    def _skill_with_fake_chain(self, monkeypatch, status="planned", message="planned chain"):
        calls = {}

        def fake_run_ai_chain(query, ai1, ai2, save_images, execute):
            calls.update(
                query=query, ai1=ai1, ai2=ai2, save_images=save_images, execute=execute
            )
            request = ChainRequest(query=query, ai1=ai1, ai2=ai2)
            # Mirrors run_ai_chain: a planned (dry) run also reports success.
            return ChainOutcome(
                request=request,
                success=status in ("completed", "planned"),
                status=status,
                message=message,
            )

        monkeypatch.setattr("skills.automation_engine.skill.run_ai_chain", fake_run_ai_chain)
        return AutomationSkill(), calls

    def test_chain_intent_dispatches(self, monkeypatch):
        skill, calls = self._skill_with_fake_chain(monkeypatch)
        result = skill.execute(
            Intent(
                action="chain",
                raw_text="chain make an image of the sarthi workflow from chatgpt to gemini",
                confidence=1.0,
            )
        )
        assert result["success"] is True
        assert result["status"] == "planned"
        assert "sarthi workflow" in calls["query"]
        assert calls["ai1"] == "chatgpt"
        assert calls["ai2"] == "gemini"
        assert calls["execute"] is None  # real run when not in test mode

    def test_chain_in_test_mode_is_dry(self, monkeypatch):
        monkeypatch.setattr("skills.automation_engine.skill.get_test_mode", lambda: True)
        skill, calls = self._skill_with_fake_chain(monkeypatch)
        result = skill.execute(
            Intent(action="chain", raw_text="/chain a logo from google gemini to gpt")
        )
        assert result["status"] == "planned"
        assert calls["ai1"] == "gemini"
        assert calls["ai2"] == "chatgpt"
        assert calls["execute"] is False  # test mode -> dry run

    def test_unknown_action_does_not_crash(self):
        skill = AutomationSkill()
        result = skill.execute(Intent(action="bogus", target="nothing"))
        assert result["success"] is False
        assert "Unsupported automation command" in result["error"]
