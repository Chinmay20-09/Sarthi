"""
Tests for the automation engine's ai_chain module.

Covers the pure logic (site resolution, command parsing, reply
extraction, run storage), the dry-run planner (never touches the
machine), and the AutomationSkill dispatch path — with run_ai_chain
mocked so no real laptop control is attempted.
"""

import pytest

from brain.intent import Intent
from skills.automation_engine.ai_chain.awareness import (
    NO_REPLY_MARKER,
    AwarenessExtractor,
    needs_awareness,
)
from skills.automation_engine.ai_chain.calibration import resolve_site
from skills.automation_engine.ai_chain.chain import run_ai_chain
from skills.automation_engine.ai_chain.control import AbortError
from skills.automation_engine.ai_chain.models import ChainOutcome, ChainRequest
from skills.automation_engine.ai_chain.parsing import (
    extract_reply,
    parse_chain_command,
    paste_verify_prefix,
    prompt_present,
)
from skills.automation_engine.ai_chain.screen import ScreenState, classify, state_message
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


class TestPromptPresent:
    def test_prompt_found(self):
        assert prompt_present("user: hello\nassistant: hi", "hello") is True

    def test_prompt_missing(self):
        assert prompt_present("Gemini New chat Search chats", "hello there") is False

    def test_whitespace_tolerant(self):
        assert prompt_present("Q:  some  prompt\nA: ok", "some prompt") is True

    def test_empty_prompt_is_always_present(self):
        assert prompt_present("anything", "") is True


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
# Browser awareness (local Hermes model transcript interpretation)
# ----------------------------------------------------------------------


class _FakeAwarenessProvider:
    """Provider stand-in that records the task prompt and returns canned text."""

    def __init__(self, text="", error=""):
        self._text = text
        self._error = error
        self.calls: list[str] = []

    def generate(self, task):
        self.calls.append(task.prompt)
        from hermes.providers.base import ProviderResponse

        if self._error:
            return ProviderResponse(
                success=False, provider="Ollama", model="hermes3:8b", text="", error=self._error
            )
        return ProviderResponse(
            success=True, provider="Ollama", model="hermes3:8b", text=self._text
        )


class TestBrowserAwareness:
    def test_needs_awareness_when_prompt_missing_from_transcript(self):
        """Page chrome with no trace of the prompt must be double-checked."""
        chrome = "Gemini New chat Search chats Students Images Library"
        assert needs_awareness(chrome, chrome, "make a logo") is True

    def test_no_awareness_when_heuristic_is_confident(self):
        """Prompt found + text after it — the heuristic result is trusted."""
        transcript = "user: make a logo\nassistant: Here is your logo"
        assert needs_awareness("Here is your logo", transcript, "make a logo") is False

    def test_needs_awareness_when_reply_empty(self):
        assert needs_awareness("", "some transcript", "prompt") is True

    def test_extract_returns_model_reply(self):
        provider = _FakeAwarenessProvider(text="Here is the real answer")
        extractor = AwarenessExtractor(provider=provider)
        assert extractor.extract("chrome chrome", "my prompt") == "Here is the real answer"

    def test_extract_no_reply_marker_returns_empty(self):
        provider = _FakeAwarenessProvider(text=NO_REPLY_MARKER)
        extractor = AwarenessExtractor(provider=provider)
        assert extractor.extract("New chat\nSearch chats", "my prompt") == ""

    def test_extract_provider_failure_returns_empty(self):
        provider = _FakeAwarenessProvider(error="Missing Ollama URL")
        extractor = AwarenessExtractor(provider=provider)
        assert extractor.extract("chrome", "prompt") == ""

    def test_extract_provider_exception_returns_empty(self):
        class ExplodingProvider:
            def generate(self, task):
                raise RuntimeError("boom")

        extractor = AwarenessExtractor(provider=ExplodingProvider())
        assert extractor.extract("chrome", "prompt") == ""

    def test_extract_strips_marker_line_keeps_reply(self):
        provider = _FakeAwarenessProvider(text=f"{NO_REPLY_MARKER}\nReal reply here")
        extractor = AwarenessExtractor(provider=provider)
        assert extractor.extract("chrome", "prompt") == "Real reply here"

    def test_extract_caps_transcript_length(self):
        provider = _FakeAwarenessProvider(text="ok")
        extractor = AwarenessExtractor(provider=provider)
        extractor.extract("x" * 100_000, "y" * 10_000)
        assert len(provider.calls) == 1
        assert len(provider.calls[0]) < 10_000  # transcript capped, not 100k


# ----------------------------------------------------------------------
# Screen-state classification (pure, no machine)
# ----------------------------------------------------------------------


class TestScreenState:
    def _spec(self, key="chatgpt"):
        return resolve_site(key)

    def test_prompt_on_page_is_conversation_even_with_chrome(self):
        """A real chat may carry 'Sign up'/'New chat' words in its chrome."""
        transcript = (
            "New chat  Log in  ChatGPT\n"
            "user: make a logo\n"
            "assistant: Here is your logo, a blue circle."
        )
        assert classify(transcript, "make a logo", self._spec()) is ScreenState.CONVERSATION

    def test_login_wall(self):
        wall = (
            "ChatGPT\nLog in to continue\nContinue with Google\n"
            "Email address  Password  Continue"
        )
        assert classify(wall, "make a logo", self._spec()) is ScreenState.LOGIN_WALL

    def test_gemini_login_wall(self):
        wall = "Sign in\nSign in to continue to Gemini\nUse Gemini"
        assert classify(wall, "hello", self._spec("gemini")) is ScreenState.LOGIN_WALL

    def test_new_chat_landing(self):
        landing = "Gemini  New chat  How can I help you today?  Ask Gemini"
        assert classify(landing, "make a logo", self._spec("gemini")) is ScreenState.LANDING_PAGE

    def test_loading_spinner(self):
        busy = (
            "Gemini is thinking and will reply shortly "
            "Stop  Generating your answer now"
        )
        assert classify(busy, "make a logo", self._spec("gemini")) is ScreenState.LOADING

    def test_single_word_marker_matches_on_word_boundary(self):
        """'Stop' must not fire on 'stopped' or 'desktop'."""
        text = (
            "I was stopped by the desktop page while finishing a sentence. "
            "It continues with many more words of ordinary prose so that "
            "the copied text is comfortably large and clearly not an "
            "element fragment."
        )
        assert classify(text, "make a logo", self._spec("gemini")) is ScreenState.UNKNOWN

    def test_fragment_is_too_small_to_be_a_page(self):
        """A message element captured whole is small and prompt-less."""
        assert classify("only this one element got copied", "make a logo", self._spec()) is ScreenState.FRAGMENT

    def test_empty_transcript(self):
        assert classify("", "make a logo", self._spec()) is ScreenState.EMPTY

    def test_unknown_large_copy_without_markers(self):
        big = "lorem ipsum dolor sit amet " * 20
        assert classify(big, "make a logo", self._spec()) is ScreenState.UNKNOWN

    def test_state_messages_are_actionable(self):
        spec = self._spec()
        assert "login screen" in state_message(ScreenState.LOGIN_WALL, spec)
        assert "composer" in state_message(ScreenState.LANDING_PAGE, spec)


class TestPasteVerifyPrefix:
    def test_short_prompt_passthrough(self):
        assert paste_verify_prefix("make a logo") == "make a logo"

    def test_long_prompt_cut_on_word_boundary(self):
        prefix = paste_verify_prefix("word " * 200)
        assert len(prefix) <= 240
        assert prefix.endswith("word")  # never mid-word

    def test_roundtrip_through_prompt_present(self):
        """Composer copy containing the pasted prompt verifies cleanly."""
        prompt = "give me five funny programming jokes please"
        composer = f"{prompt}\n"  # composers often add a trailing newline
        assert prompt_present(composer, paste_verify_prefix(prompt)) is True


# ----------------------------------------------------------------------
# Driver screen awareness (WebAiDriver with a stub controller)
# ----------------------------------------------------------------------


class _StubController:
    """ScreenController stand-in that replays canned clipboard copies.

    The first ``composer_copies`` Select-All+Copy calls answer with the
    composer text (paste verification); every later call pops the next
    page transcript from ``page_reads``.
    """

    def __init__(self, composer_copies=0, composer_text="", page_reads=()):
        self._composer_remaining = composer_copies
        self._composer_text = composer_text
        self._page_reads = list(page_reads)
        self.dry_run = False
        self.pastes: list[str] = []
        self.pressed: list[str] = []
        self.clicked: list[tuple[int, int]] = []

    def check_abort(self):
        pass

    def open_site(self, url, title_keyword, wait):
        pass

    def window_rect(self, title_keyword):
        return (0, 0, 100, 100)

    def fraction_point(self, rect, fx, fy):
        return (int(rect[2] * fx), int(rect[3] * fy))

    def click(self, x, y):
        self.clicked.append((x, y))

    def paste(self, text):
        self.pastes.append(text)

    def press(self, key):
        self.pressed.append(key)

    def hotkey(self, *keys):
        pass

    def select_all_and_copy(self):
        if self._composer_remaining > 0:
            self._composer_remaining -= 1
            return self._composer_text
        return self._page_reads.pop(0) if self._page_reads else ""


class TestDriverScreenAwareness:
    def _instant_spec(self, key="chatgpt"):
        import dataclasses

        return dataclasses.replace(resolve_site(key), poll_interval=0.0, max_wait=30.0)

    def test_ask_fails_fast_on_login_wall(self, monkeypatch):
        """Two consecutive wall reads raise before the wait budget burns."""
        from skills.automation_engine.ai_chain import sites

        monkeypatch.setattr("skills.automation_engine.ai_chain.sites.time.sleep", lambda s: None)
        wall = "ChatGPT  Log in  Continue with Google  Email address"
        ctrl = _StubController(
            composer_copies=1, composer_text="make a logo", page_reads=[wall, wall]
        )
        driver = sites.WebAiDriver(ctrl)
        with pytest.raises(RuntimeError, match="login screen"):
            driver.ask(self._instant_spec(), "make a logo")
        # The paste was verified, so Enter went out — the wall was only
        # discovered when the reply never came back, and it failed fast
        # instead of polling out the whole budget.
        assert ctrl.pressed == ["enter"]

    def test_ask_succeeds_when_composer_holds_prompt(self, monkeypatch):
        """Paste verified, reply read until stable and extracted."""
        from skills.automation_engine.ai_chain import sites

        monkeypatch.setattr("skills.automation_engine.ai_chain.sites.time.sleep", lambda s: None)
        monkeypatch.setattr(
            "skills.automation_engine.ai_chain.sites.MIN_FINISH_SECONDS", 0.0
        )
        prompt = "make a birthday invitation prompt"
        conversation = (
            "ChatGPT  New chat  Search\n"
            f"{prompt}\n"
            "ChatGPT: Here is a prompt for your invitation card."
        )
        ctrl = _StubController(
            composer_copies=1,
            composer_text=prompt,
            page_reads=[conversation, conversation, conversation],
        )
        driver = sites.WebAiDriver(ctrl)
        reply = driver.ask(self._instant_spec(), prompt)
        assert "invitation card" in reply
        assert ctrl.pressed == ["enter"]
        assert len(ctrl.pastes) == 1  # no duplicate re-paste

    def test_ask_retries_and_fails_when_paste_never_lands(self, monkeypatch):
        """A composer that never shows the prompt fails with an actionable error."""
        from skills.automation_engine.ai_chain import sites

        monkeypatch.setattr("skills.automation_engine.ai_chain.sites.time.sleep", lambda s: None)
        ctrl = _StubController(composer_copies=3, composer_text="", page_reads=[])
        driver = sites.WebAiDriver(ctrl)
        with pytest.raises(RuntimeError, match="could not get the prompt into the message box"):
            driver.ask(self._instant_spec(), "make a logo")
        assert len(ctrl.pastes) == 3  # original + two retries, then gave up

    def test_ask_rereads_element_fragment_before_concluding(self, monkeypatch):
        """A copy that grabbed one element is re-read until the page shows."""
        from skills.automation_engine.ai_chain import sites

        monkeypatch.setattr("skills.automation_engine.ai_chain.sites.time.sleep", lambda s: None)
        monkeypatch.setattr(
            "skills.automation_engine.ai_chain.sites.MIN_FINISH_SECONDS", 0.0
        )
        prompt = "give me five jokes"
        fragment = "only this element got copied"  # < 80 chars, no markers
        conversation = f"ChatGPT\n{prompt}\nassistant: Why did the robot laugh?"
        ctrl = _StubController(
            composer_copies=1,
            composer_text=prompt,
            page_reads=[fragment, fragment, fragment, conversation, conversation, conversation],
        )
        driver = sites.WebAiDriver(ctrl)
        reply = driver.ask(self._instant_spec(), prompt)
        assert "robot laugh" in reply


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
