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
        with pytest.raises(
            RuntimeError, match="Could not find a browser window titled like 'ChatGPT'"
        ):
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
            "ChatGPT\nLog in to continue\nContinue with Google\nEmail address  Password  Continue"
        )
        assert classify(wall, "make a logo", self._spec()) is ScreenState.LOGIN_WALL

    def test_gemini_login_wall(self):
        wall = "Sign in\nSign in to continue to Gemini\nUse Gemini"
        assert classify(wall, "hello", self._spec("gemini")) is ScreenState.LOGIN_WALL

    def test_new_chat_landing(self):
        landing = "Gemini  New chat  How can I help you today?  Ask Gemini"
        assert classify(landing, "make a logo", self._spec("gemini")) is ScreenState.LANDING_PAGE

    def test_loading_spinner(self):
        busy = "Gemini is thinking and will reply shortly Stop  Generating your answer now"
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
        assert (
            classify("only this one element got copied", "make a logo", self._spec())
            is ScreenState.FRAGMENT
        )

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
    composer text (paste verification); every later Select-All+Copy call
    pops the next page transcript from ``page_reads``. ``button_copies``
    are what the site's Copy button puts on the clipboard (``copy_with_button``);
    an empty list means the button never works, so the driver falls back
    to the page copy.
    """

    def __init__(self, composer_copies=0, composer_text="", page_reads=(), button_copies=()):
        self._composer_remaining = composer_copies
        self._composer_text = composer_text
        self._page_reads = list(page_reads)
        self._button_copies = list(button_copies)
        self.dry_run = False
        self.pastes: list[str] = []
        self.pressed: list[str] = []
        self.clicked: list[tuple[int, int]] = []
        self.button_clicked: list[tuple[int, int]] = []
        self.page_copy_calls = 0

    def check_abort(self):
        pass

    def release(self):
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
        self.page_copy_calls += 1
        return self._page_reads.pop(0) if self._page_reads else ""

    def copy_with_button(self, x, y):
        """Click the registered Copy button; return what it copied."""
        self.button_clicked.append((x, y))
        return self._button_copies.pop(0) if self._button_copies else ""


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
        monkeypatch.setattr("skills.automation_engine.ai_chain.sites.MIN_FINISH_SECONDS", 0.0)
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
        monkeypatch.setattr("skills.automation_engine.ai_chain.sites.MIN_FINISH_SECONDS", 0.0)
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

    def test_ask_uses_registered_copy_button(self, monkeypatch):
        """The site's Copy button is clicked — the page is never Ctrl+A'd."""
        from skills.automation_engine.ai_chain import sites

        monkeypatch.setattr("skills.automation_engine.ai_chain.sites.time.sleep", lambda s: None)
        monkeypatch.setattr("skills.automation_engine.ai_chain.sites.MIN_FINISH_SECONDS", 0.0)
        prompt = "make a logo"
        # A Copy button returns ONLY the assistant's message — it never
        # carries the sent prompt, and it is already the reply.
        reply_text = "ChatGPT: Here is your logo, a blue circle."
        ctrl = _StubController(
            composer_copies=1,
            composer_text=prompt,
            button_copies=[reply_text, reply_text, reply_text],
        )
        driver = sites.WebAiDriver(ctrl)
        result = driver.ask(self._instant_spec(), prompt)
        assert "blue circle" in result
        assert len(ctrl.button_clicked) >= 1
        # The reply came from the Copy button — no whole-page Select-All
        # + Copy was used to read it (the only Select-All is the composer
        # paste verification, which does not count as a page copy).
        assert ctrl.page_copy_calls == 0

    def test_ask_falls_back_to_page_copy_when_button_misses(self, monkeypatch):
        """A Copy button that never yields text degrades to Ctrl+A/Ctrl+C."""
        from skills.automation_engine.ai_chain import sites

        monkeypatch.setattr("skills.automation_engine.ai_chain.sites.time.sleep", lambda s: None)
        monkeypatch.setattr("skills.automation_engine.ai_chain.sites.MIN_FINISH_SECONDS", 0.0)
        prompt = "give me five jokes"
        conversation = f"ChatGPT\n{prompt}\nassistant: Why did the robot laugh?"
        ctrl = _StubController(
            composer_copies=1,
            composer_text=prompt,
            page_reads=[conversation, conversation, conversation],
            button_copies=[""] * 30,  # the Copy button never works
        )
        driver = sites.WebAiDriver(ctrl)
        reply = driver.ask(self._instant_spec(), prompt)
        assert "robot laugh" in reply
        assert len(ctrl.button_clicked) >= 1
        assert ctrl.page_copy_calls >= 1

    def test_ask_finds_copy_button_by_scanning(self, monkeypatch):
        """A missed point is recovered by scanning the last-message region."""
        from skills.automation_engine.ai_chain import sites

        monkeypatch.setattr("skills.automation_engine.ai_chain.sites.time.sleep", lambda s: None)
        monkeypatch.setattr("skills.automation_engine.ai_chain.sites.MIN_FINISH_SECONDS", 0.0)
        prompt = "make a logo"
        reply_text = "ChatGPT: Here is your logo, a blue circle."
        # The registered point misses on every read; the FIRST scan cell
        # (nearest to the point) finds the button.
        ctrl = _StubController(
            composer_copies=1,
            composer_text=prompt,
            button_copies=["", reply_text, "", reply_text, "", reply_text],
        )
        driver = sites.WebAiDriver(ctrl)
        result = driver.ask(self._instant_spec(), prompt)
        assert "blue circle" in result
        # Registered point attempted first, then a different scan cell.
        assert ctrl.button_clicked[0] == (88, 87)  # chatgpt default copy point
        assert ctrl.button_clicked[1] != (88, 87)
        # The reply came from a button — never a whole-page copy.
        assert ctrl.page_copy_calls == 0


# ----------------------------------------------------------------------
# Browser awareness registry (per-site action knowledge)
# ----------------------------------------------------------------------


class TestBrowserAwarenessRegistry:
    def test_default_button_copy_for_known_sites(self):
        from skills.automation_engine.ai_chain import registry

        registry.reset_cache()
        chatgpt = registry.get_actions("chatgpt")
        assert chatgpt.copy.uses_button is True
        assert chatgpt.copy.label == "Copy"
        assert registry.get_copy_point("chatgpt") is not None
        assert registry.uses_button_copy("gemini") is True
        assert registry.copy_retries("chatgpt") >= 1

    def test_unknown_site_falls_back_to_keyboard_copy(self):
        from skills.automation_engine.ai_chain import registry

        registry.reset_cache()
        actions = registry.get_actions("clippy")
        assert actions.copy.uses_button is False
        assert registry.uses_button_copy("clippy") is False
        assert registry.get_copy_point("clippy") is None

    def test_copy_scan_candidates_start_at_point_and_stay_in_region(self):
        from skills.automation_engine.ai_chain import registry

        registry.reset_cache()
        candidates = registry.copy_scan_candidates("chatgpt")
        assert candidates, "known sites must offer click candidates"
        # The registered point is tried first.
        assert candidates[0] == registry.get_copy_point("chatgpt")
        # Every candidate lies inside the scan region, budget-capped.
        x0, y0, x1, y1 = registry.get_scan_region("chatgpt")
        for fx, fy in candidates:
            assert x0 <= fx <= x1
            assert y0 <= fy <= y1
        assert len(candidates) == registry.copy_retries("chatgpt")

    def test_copy_scan_candidates_empty_for_unknown_site(self):
        from skills.automation_engine.ai_chain import registry

        registry.reset_cache()
        assert registry.copy_scan_candidates("clippy") == []

    def test_actions_override_via_calibration(self, monkeypatch):
        from skills.automation_engine.ai_chain import registry

        monkeypatch.setattr(
            registry,
            "_load_calibration",
            lambda: {
                "actions": {
                    "chatgpt": {
                        "copy": {
                            "method": "button",
                            "label": "Copy response",
                            "point": [0.9, 0.8],
                            "scan_region": [0.7, 0.7, 0.99, 0.9],
                            "retries": 4,
                        }
                    }
                }
            },
        )
        registry.reset_cache()
        copy = registry.get_actions("chatgpt").copy
        assert copy.label == "Copy response"
        assert copy.point == (0.9, 0.8)
        assert copy.scan_region == (0.7, 0.7, 0.99, 0.9)
        assert copy.retries == 4
        assert registry.copy_retries("chatgpt") == 4
        # Scan candidates honour the overridden region + budget.
        candidates = registry.copy_scan_candidates("chatgpt")
        assert len(candidates) == 4
        assert all(0.7 <= fx <= 0.99 and 0.7 <= fy <= 0.9 for fx, fy in candidates)

    def test_copy_point_recorded_by_calibrate_is_honoured(self, monkeypatch):
        from skills.automation_engine.ai_chain import registry

        monkeypatch.setattr(
            registry,
            "_load_calibration",
            lambda: {"sites": {"gemini": {"copy_point": [0.75, 0.79]}}},
        )
        registry.reset_cache()
        assert registry.get_copy_point("gemini") == (0.75, 0.79)

    def test_env_override_wins(self, monkeypatch):
        from skills.automation_engine.ai_chain import registry

        monkeypatch.setenv("AI_CHAIN_CHATGPT_COPY_POINT", "0.7,0.6")
        monkeypatch.setenv("AI_CHAIN_CHATGPT_COPY_SCAN_REGION", "0.5,0.6,0.95,0.9")
        monkeypatch.setattr(registry, "_load_calibration", lambda: {})
        registry.reset_cache()
        assert registry.get_copy_point("chatgpt") == (0.7, 0.6)
        assert registry.get_scan_region("chatgpt") == (0.5, 0.6, 0.95, 0.9)

    def test_scan_region_derived_from_point_when_absent(self, monkeypatch):
        from skills.automation_engine.ai_chain import registry

        monkeypatch.setattr(
            registry,
            "_load_calibration",
            lambda: {"actions": {"chatgpt": {"copy": {"scan_region": None}}}},
        )
        registry.reset_cache()
        point = registry.get_copy_point("chatgpt")
        assert registry.get_scan_region("chatgpt") is None
        candidates = registry.copy_scan_candidates("chatgpt")
        assert candidates[0] == point
        # Derived region still produces in-bounds candidates.
        assert all(0.0 <= fx <= 1.0 and 0.0 <= fy <= 1.0 for fx, fy in candidates)


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
        monkeypatch.setattr("skills.automation_engine.ai_chain.chain.announce", lambda msg: None)

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

        outcome = run_ai_chain("make a logo", ai1="chatgpt", ai2="gemini", execute=False)

        assert outcome.status == "planned"
        assert TaskSandbox(str(root)).lookup("make a logo") == []


# ----------------------------------------------------------------------
# AutomationSkill dispatch (run_ai_chain mocked)
# ----------------------------------------------------------------------


class TestSkillDispatch:
    def _skill_with_fake_chain(self, monkeypatch, status="planned", message="planned chain"):
        calls = {}

        def fake_run_ai_chain(query, ai1, ai2, save_images, execute):
            calls.update(query=query, ai1=ai1, ai2=ai2, save_images=save_images, execute=execute)
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


# ----------------------------------------------------------------------
# v1.5 — DOM locating (regex over the page HTML)
# ----------------------------------------------------------------------


class TestDomLocator:
    """Pure regex/geometry helpers in dom.py (no browser needed)."""

    def test_dom_enabled_switch(self, monkeypatch):
        from skills.automation_engine.ai_chain.dom import dom_enabled

        monkeypatch.delenv("AI_CHAIN_DOM", raising=False)
        assert dom_enabled() is True
        monkeypatch.setenv("AI_CHAIN_DOM", "0")
        assert dom_enabled() is False
        monkeypatch.setenv("AI_CHAIN_DOM", "1")
        assert dom_enabled() is True

    def test_keyword_for(self):
        from skills.automation_engine.ai_chain.dom import keyword_for

        assert keyword_for("https://chatgpt.com/") == "chatgpt.com"
        assert keyword_for("https://www.gemini.google.com/app") == "gemini.google.com"
        assert keyword_for("") == ""

    def test_rect_to_fraction(self):
        from skills.automation_engine.ai_chain.dom import (
            ElementRect,
            ViewportDims,
            rect_to_fraction,
        )

        # 100px browser chrome split horizontally, 100px on top.
        dims = ViewportDims(outer_width=1200, inner_width=1100, outer_height=900, inner_height=800)
        rect = ElementRect(x=100, y=150, width=50, height=20)
        fx, fy = rect_to_fraction(dims, rect)
        assert fx == pytest.approx((50 + 125) / 1200)  # chrome_x = (1200-1100)/2
        assert fy == pytest.approx((100 + 160) / 900)  # chrome_y = 900-800

    def test_rect_to_fraction_clamps_to_window(self):
        from skills.automation_engine.ai_chain.dom import (
            ElementRect,
            ViewportDims,
            rect_to_fraction,
        )

        dims = ViewportDims(outer_width=1200, inner_width=1100, outer_height=900, inner_height=800)
        fx, fy = rect_to_fraction(dims, ElementRect(x=-9999, y=-9999, width=10, height=10))
        assert fx == 0.0
        assert fy == 0.0
        fx, fy = rect_to_fraction(dims, ElementRect(x=99999, y=99999, width=10, height=10))
        assert fx == 1.0
        assert fy == 1.0

    def test_find_affordances_exact_word_beat_loose(self):
        from skills.automation_engine.ai_chain.dom import find_affordances
        from skills.automation_engine.ai_chain.registry import DomMatcher

        html = (
            '<header><button aria-label="Edit">Edit</button></header>'
            "<main>"
            '<button data-testid="copy-context-menu-item" aria-label="Copy">Copy</button>'
            '<button aria-label="Copy code">&lt;/&gt;</button>'
            "</main>"
            "<footer><button aria-label='Copy'>Copy</button></footer>"
        )
        exact = DomMatcher("copy", "button", "aria-label", r"^copy$")
        assert find_affordances(html, exact) == ["Copy", "Copy"]  # in order; not "Copy code"
        loose = DomMatcher("copy", "button", "aria-label", r"copy")
        assert find_affordances(html, loose) == ["Copy", "Copy code", "Copy"]

    def test_find_affordances_any_tag_and_guard(self):
        from skills.automation_engine.ai_chain.dom import find_affordances
        from skills.automation_engine.ai_chain.registry import DomMatcher

        html = '<div aria-label="Enter a prompt here"></div><p aria-label="Ask Gemini"></p>'
        any_tag = DomMatcher("composer", "", "aria-label", r"prompt|ask gemini")
        assert find_affordances(html, any_tag) == ["Enter a prompt here", "Ask Gemini"]
        # Missing attribute or pattern -> no match, no crash.
        assert find_affordances(html, DomMatcher("composer", "", "", r"x")) == []
        assert find_affordances("", any_tag) == []
        assert find_affordances(None, any_tag) == []


class TestDomRegistry:
    """Per-site DOM matcher catalogue + overrides."""

    def test_defaults(self):
        from skills.automation_engine.ai_chain import registry

        registry.reset_cache()
        assert registry.get_dom_matchers("chatgpt", "copy")
        assert registry.get_dom_matchers("chatgpt", "composer")
        assert registry.get_dom_matchers("gemini", "copy")
        assert registry.get_dom_matchers("gemini", "composer")
        # Gemini is the image-capable site: only it has download matchers.
        assert registry.get_dom_matchers("gemini", "download")
        assert registry.get_dom_matchers("chatgpt", "download") == ()
        # Unknown sites have no DOM profile.
        assert registry.get_dom_matchers("clippy", "copy") == ()

    def test_action_kill_switch_env(self, monkeypatch):
        from skills.automation_engine.ai_chain import registry

        monkeypatch.setenv("AI_CHAIN_CHATGPT_DOM_COPY", "0")
        assert registry.dom_action_enabled("chatgpt", "copy") is False
        # Other actions on the same site stay enabled.
        assert registry.dom_action_enabled("chatgpt", "composer") is True
        monkeypatch.delenv("AI_CHAIN_CHATGPT_DOM_COPY")
        assert registry.dom_action_enabled("chatgpt", "copy") is True

    def test_master_switch_disables_everything(self, monkeypatch):
        from skills.automation_engine.ai_chain import registry

        monkeypatch.setenv("AI_CHAIN_DOM", "0")
        assert registry.dom_action_enabled("chatgpt", "copy") is False
        assert registry.dom_action_enabled("gemini", "download") is False

    def test_calibration_override_replaces_matchers(self, monkeypatch):
        from skills.automation_engine.ai_chain import registry

        monkeypatch.setattr(
            registry,
            "_load_calibration",
            lambda: {
                "actions": {
                    "chatgpt": {
                        "dom": {
                            "copy": [
                                {
                                    "tag": "div",
                                    "attribute": "data-testid",
                                    "value_pattern": "copy-.*",
                                }
                            ]
                        }
                    }
                }
            },
        )
        registry.reset_cache()
        matchers = registry.get_dom_matchers("chatgpt", "copy")
        assert len(matchers) == 1
        assert matchers[0].tag == "div"
        assert matchers[0].attribute == "data-testid"
        assert matchers[0].value_pattern == "copy-.*"
        # Composer is untouched by a copy-only override.
        assert registry.get_dom_matchers("chatgpt", "composer")


class TestExtendedSites:
    """Claude + other AI sites added to the catalogue (v1.5 matchers)."""

    def test_resolution_and_aliases(self):
        from skills.automation_engine.ai_chain import registry
        from skills.automation_engine.ai_chain.calibration import resolve_site

        registry.reset_cache()
        assert resolve_site("claude").key == "claude"
        assert resolve_site("claude ai").key == "claude"
        assert resolve_site("anthropic").key == "claude"
        assert resolve_site("perplexity").key == "perplexity"
        assert resolve_site("grok").key == "grok"
        assert resolve_site("x ai").key == "grok"
        assert resolve_site("deepseek").key == "deepseek"
        assert resolve_site("copilot").key == "copilot"
        # Unchanged: unknown names still raise.
        with pytest.raises(ValueError, match="Unknown AI"):
            resolve_site("clippy")

    def test_copy_actions_registered_for_new_sites(self):
        from skills.automation_engine.ai_chain import registry

        registry.reset_cache()
        for key in ("claude", "perplexity", "grok", "deepseek", "copilot"):
            assert registry.uses_button_copy(key) is True
            assert registry.get_copy_point(key) is not None

    def test_dom_matchers_ship_for_new_sites(self):
        from skills.automation_engine.ai_chain import registry

        registry.reset_cache()
        for key in ("claude", "perplexity", "grok", "deepseek", "copilot"):
            assert registry.get_dom_matchers(key, "copy"), f"{key} needs copy matchers"
            assert registry.get_dom_matchers(key, "composer"), f"{key} needs composer matchers"

    def test_deepseek_composer_matcher_targets_chat_input(self):
        from skills.automation_engine.ai_chain import registry

        registry.reset_cache()
        matchers = registry.get_dom_matchers("deepseek", "composer")
        assert matchers[0].attribute == "id"
        assert "chat-input" in matchers[0].value_pattern

    def test_image_capable_flags(self):
        from skills.automation_engine.ai_chain.calibration import resolve_site

        assert resolve_site("grok").image_capable is True
        assert resolve_site("copilot").image_capable is True
        assert resolve_site("claude").image_capable is False
        assert resolve_site("perplexity").image_capable is False
        assert resolve_site("deepseek").image_capable is False

    def test_dom_location_on_claude_markup(self):
        from skills.automation_engine.ai_chain import registry
        from skills.automation_engine.ai_chain.dom import find_affordances

        registry.reset_cache()
        html = (
            '<div class="composer" contenteditable="true" role="textbox" aria-label="Message Claude"></div>'
            '<button aria-label="Copy">copy</button>'
        )
        composer = [m for m in registry.get_dom_matchers("claude", "composer")]
        assert find_affordances(html, composer[0]) == ["Message Claude"]
        copy = registry.get_dom_matchers("claude", "copy")[0]
        assert find_affordances(html, copy) == ["Copy"]

    def test_dom_location_on_deepseek_markup(self):
        from skills.automation_engine.ai_chain import registry
        from skills.automation_engine.ai_chain.dom import find_affordances

        registry.reset_cache()
        html = '<textarea id="chat-input" placeholder="Message DeepSeek"></textarea>'
        matcher = registry.get_dom_matchers("deepseek", "composer")[0]
        assert find_affordances(html, matcher) == ["chat-input"]


class TestHandoffStore:
    """Backend hand-off: prompts/responses saved, reloaded, never clipboard-born."""

    def setup_method(self):
        from skills.automation_engine.ai_chain import handoff

        handoff.reset()

    def test_round_trip(self):
        from skills.automation_engine.ai_chain import handoff

        assert handoff.load("missing") == ""
        assert handoff.has("missing") is False
        handoff.save("step1_response", "  hello world  ")
        assert handoff.load("step1_response") == "hello world"
        assert handoff.has("step1_response") is True

    def test_overwrite_and_reset(self):
        from skills.automation_engine.ai_chain import handoff

        handoff.save("k", "first")
        handoff.save("k", "second")
        assert handoff.load("k") == "second"
        handoff.reset()
        assert handoff.load("k") == ""

    def test_step2_prompt_comes_from_backend(self, monkeypatch):
        """The chain sources AI2's prompt from the saved copy, not memory."""
        from skills.automation_engine.ai_chain import chain, handoff
        from skills.automation_engine.ai_chain.models import StepOutcome

        captured = {}

        def fake_drive(ctrl, run, spec, prompt, index):
            # Mirrors the real _drive's backend saves.
            captured[index] = prompt
            handoff.save(f"step{index}_prompt", prompt)
            outcome = StepOutcome(
                index=index, site_key=spec.key, site_label=spec.label, prompt=prompt
            )
            outcome.response = f"reply-{index}"
            handoff.save(f"step{index}_response", outcome.response)
            return outcome

        monkeypatch.setattr(chain, "_drive", fake_drive)
        monkeypatch.setattr(chain, "_countdown", lambda ctrl: None)
        monkeypatch.setattr("skills.automation_engine.ai_chain.chain.announce", lambda msg: None)
        monkeypatch.setattr(chain, "_save_to_sandbox", lambda req, outcome: None)
        monkeypatch.setattr(
            chain, "get_downloads_dir", lambda: __import__("pathlib").Path("/nonexistent")
        )

        class _Run:
            def __init__(self):
                self.dir = None

            def write_text(self, *a, **k):
                return __import__("pathlib").Path("/nonexistent/f.txt")

            def harvest_file(self, *a, **k):
                return __import__("pathlib").Path("/nonexistent/f.png")

        monkeypatch.setattr(
            "skills.automation_engine.ai_chain.chain.ChainRun", lambda *a, **k: _Run()
        )

        outcome = run_ai_chain(
            "hello",
            ai1="chatgpt",
            ai2="gemini",
            save_images=False,
            execute=True,
            controller=_StubController(),
        )
        assert outcome.status == "completed"
        # Step 1 prompt = the query; step 2 prompt = AI1's reply from the backend.
        assert captured[1] == "hello"
        assert captured[2] == "reply-1"
        assert handoff.load("step2_response") == "reply-2"


class TestComposerRetryCandidates:
    """Failed paste verifies must try NEW points, not the same one thrice."""

    def setup_method(self):
        # The hand-off store is module-level: a previous test's saved
        # "step2_prompt" would leak into these runs and be re-pasted on
        # retry instead of this test's own prompt.
        from skills.automation_engine.ai_chain import handoff

        handoff.reset()

    def _spec(self, key="gemini"):
        import dataclasses

        return dataclasses.replace(resolve_site(key), poll_interval=0.0, max_wait=30.0)

    def test_retries_click_different_candidates(self, monkeypatch):
        from skills.automation_engine.ai_chain import sites

        monkeypatch.setattr("skills.automation_engine.ai_chain.sites.time.sleep", lambda s: None)
        monkeypatch.setattr("skills.automation_engine.ai_chain.sites.MIN_FINISH_SECONDS", 0.0)

        class _FlakyComposer(_StubController):
            """First two composer verifies come back empty, then it works."""

            def __init__(self, fail_first, composer_text, **kw):
                super().__init__(**kw)
                self._fail_first = fail_first
                self._composer_text = composer_text

            def select_all_and_copy(self):
                if self._fail_first > 0:
                    self._fail_first -= 1
                    return ""
                return self._composer_text

        prompt = "tell me a joke"
        conversation = f"Gemini\n{prompt}\nassistant: why did the robot laugh"
        ctrl = _FlakyComposer(
            fail_first=2,
            composer_text=prompt,
            button_copies=[conversation, conversation, conversation],
        )
        dom = _FakeDomReader(points={"composer": (0.5, 0.955), "copy": (0.86, 0.85)})
        driver = sites.WebAiDriver(ctrl, dom_reader=dom)
        reply = driver.ask(self._spec(), prompt, prompt_key="step2_prompt")
        assert "robot laugh" in reply
        # Composer-region clicks: DOM hit, then two DIFFERENT fallbacks.
        composer_clicks = [c for c in ctrl.clicked if c[1] >= 85]  # lower window area
        assert len(composer_clicks) == 3
        assert len(set(composer_clicks)) == 3, f"retries repeated points: {composer_clicks}"
        # Every retry pasted again (backend re-copy), and the run succeeded.
        assert len(ctrl.pastes) == 3
        assert all(p == prompt for p in ctrl.pastes)

    def test_total_failure_mentions_backend(self, monkeypatch):
        from skills.automation_engine.ai_chain import handoff, sites

        monkeypatch.setattr("skills.automation_engine.ai_chain.sites.time.sleep", lambda s: None)
        ctrl = _StubController(composer_copies=3, composer_text="", page_reads=[])
        driver = sites.WebAiDriver(ctrl)
        handoff.save("step2_prompt", "the saved prompt")
        with pytest.raises(RuntimeError, match="backend hand-off"):
            driver.ask(self._spec(), "the saved prompt", prompt_key="step2_prompt")


class TestAutomationChrome:
    """The robot launches its own Chrome (debug port + persistent profile)."""

    def test_find_chrome_exe_env_override(self, monkeypatch, tmp_path):
        from skills.automation_engine.ai_chain import control

        fake = tmp_path / "chrome.exe"
        fake.write_bytes(b"MZ")
        monkeypatch.setenv("AI_CHAIN_CHROME_PATH", str(fake))
        assert control.find_chrome_exe() == str(fake)

    def test_profile_dir_env_override(self, monkeypatch, tmp_path):
        from skills.automation_engine.ai_chain import calibration

        monkeypatch.setenv("AI_CHAIN_PROFILE_DIR", str(tmp_path / "prof"))
        assert calibration.get_automation_profile_dir() == tmp_path / "prof"
        monkeypatch.delenv("AI_CHAIN_PROFILE_DIR")
        assert calibration.get_automation_profile_dir().name == ".chrome-profile"

    def test_launch_command_has_explicit_profile(self):
        from pathlib import Path

        from skills.automation_engine.ai_chain.control import _chrome_launch_command

        cmd = _chrome_launch_command(
            "C:/chrome.exe", "https://chatgpt.com/", 9222, Path("/tmp/prof")
        )
        assert cmd[0] == "C:/chrome.exe"
        assert "--remote-debugging-port=9222" in cmd
        # The explicit user-data-dir is what makes Chrome honour the port.
        assert any(a.startswith("--user-data-dir=") for a in cmd)
        assert cmd[-1] == "https://chatgpt.com/"

    def test_open_site_falls_back_without_chrome(self, monkeypatch):
        from skills.automation_engine.ai_chain import control

        opened = []

        class _Ctrl(control.ScreenController):
            def __init__(self):
                self.dry_run = True  # skip real window work

        # Not dry-run, but with no chrome exe and webbrowser patched, the
        # fallback path must trigger instead of raising.
        monkeypatch.setattr(control, "find_chrome_exe", lambda: None)
        monkeypatch.setattr(
            "skills.automation_engine.ai_chain.control.ScreenController._find_window",
            lambda self, kw, timeout: 1,
        )
        monkeypatch.setattr(
            "skills.automation_engine.ai_chain.control.ScreenController._activate_window",
            lambda self, hwnd: None,
        )
        import webbrowser

        monkeypatch.setattr(webbrowser, "open", lambda url: opened.append(url) or True)
        ctrl = control.ScreenController(dry_run=False)
        ctrl._register_hotkey = lambda: None  # no keyboard in tests
        ctrl.open_site("https://chatgpt.com/", "ChatGPT", 0.0)
        assert opened == ["https://chatgpt.com/"]

    def test_cdp_port_resolution(self, monkeypatch):
        from skills.automation_engine.ai_chain import dom

        monkeypatch.delenv(dom.CDP_URL_ENV, raising=False)
        monkeypatch.delenv(dom.CDP_PORT_ENV, raising=False)
        assert dom.cdp_port() == 9222
        monkeypatch.setenv(dom.CDP_PORT_ENV, "9333")
        assert dom.cdp_port() == 9333
        assert dom.cdp_url() == "http://127.0.0.1:9333"
        monkeypatch.setenv(dom.CDP_URL_ENV, "http://127.0.0.1:9444")
        assert dom.cdp_port() == 9444


class _FakeDomReader:
    """dom.DomReader stand-in returning canned window-fraction points."""

    def __init__(self, points=None):
        self.points = points or {}  # action -> (fx, fy)
        self.calls: list[str] = []

    def locate(self, url_keyword, matchers):
        action = matchers[0].action if matchers else "?"
        self.calls.append(action)
        return self.points.get(action)


class TestDriverDomLocating:
    """WebAiDriver preferring DOM-located points (v1.5) over blind scans."""

    def _spec(self, key="chatgpt"):
        import dataclasses

        return dataclasses.replace(resolve_site(key), poll_interval=0.0, max_wait=30.0)

    def test_dom_copy_button_used_without_scan_or_page_copy(self, monkeypatch):
        from skills.automation_engine.ai_chain import sites

        monkeypatch.setattr("skills.automation_engine.ai_chain.sites.time.sleep", lambda s: None)
        monkeypatch.setattr("skills.automation_engine.ai_chain.sites.MIN_FINISH_SECONDS", 0.0)
        prompt = "make a logo"
        conversation = (
            "ChatGPT  New chat  Search\n"
            f"{prompt}\n"
            "ChatGPT: Here is a prompt for your invitation card."
        )
        ctrl = _StubController(
            composer_copies=1,
            composer_text=prompt,
            button_copies=[conversation, conversation, conversation],
        )
        dom = _FakeDomReader(points={"copy": (0.88, 0.87)})
        driver = sites.WebAiDriver(ctrl, dom_reader=dom)
        reply = driver.ask(self._spec(), prompt)
        assert "invitation card" in reply
        # The DOM point was clicked (fraction 0.88/0.87 of a 100x100 stub
        # window -> 88, 87), the scan grid was never used, and no page
        # copy happened.
        assert ctrl.button_clicked == [(88, 87), (88, 87), (88, 87)]
        assert ctrl.page_copy_calls == 0
        # Composer was asked first (nothing found -> estimate), then each
        # of the three reply polls located the Copy button.
        assert dom.calls[0] == "composer"
        assert dom.calls[1:] == ["copy", "copy", "copy"]

    def test_dom_copy_miss_falls_back_to_scan_and_page_copy(self, monkeypatch):
        from skills.automation_engine.ai_chain import sites

        monkeypatch.setattr("skills.automation_engine.ai_chain.sites.time.sleep", lambda s: None)
        monkeypatch.setattr("skills.automation_engine.ai_chain.sites.MIN_FINISH_SECONDS", 0.0)
        from skills.automation_engine.ai_chain import registry

        prompt = "make a logo"
        conversation = f"ChatGPT  New chat\n{prompt}\nassistant: your logo is ready"
        ctrl = _StubController(
            composer_copies=1,
            composer_text=prompt,
            page_reads=[conversation, conversation, conversation],
        )
        dom = _FakeDomReader(points={})  # regex found nothing -> None
        driver = sites.WebAiDriver(ctrl, dom_reader=dom)
        reply = driver.ask(self._spec(), prompt)
        assert "logo is ready" in reply
        # v1.0 path still works: scan clicked, then the page copy was used.
        assert ctrl.page_copy_calls == 3
        assert len(ctrl.button_clicked) == 3 * registry.copy_retries("chatgpt")

    def test_dom_composer_focus_preferred(self, monkeypatch):
        from skills.automation_engine.ai_chain import sites

        monkeypatch.setattr("skills.automation_engine.ai_chain.sites.time.sleep", lambda s: None)
        monkeypatch.setattr("skills.automation_engine.ai_chain.sites.MIN_FINISH_SECONDS", 0.0)
        prompt = "draw a cat"
        conversation = f"ChatGPT\n{prompt}\nassistant: meow"
        ctrl = _StubController(
            composer_copies=1,
            composer_text=prompt,
            button_copies=[conversation, conversation, conversation],
        )
        dom = _FakeDomReader(points={"composer": (0.3, 0.94), "copy": (0.88, 0.87)})
        driver = sites.WebAiDriver(ctrl, dom_reader=dom)
        driver.ask(self._spec(), prompt)
        # First click (focusing the composer) happened at the DOM point.
        assert ctrl.clicked[0] == (30, 94)
        assert dom.calls[0] == "composer"

    def test_download_uses_dom_point(self, monkeypatch, tmp_path):
        from skills.automation_engine.ai_chain import sites

        monkeypatch.setattr("skills.automation_engine.ai_chain.sites.time.sleep", lambda s: None)
        ctrl = _StubController()
        dom = _FakeDomReader(points={"download": (0.7, 0.45)})
        driver = sites.WebAiDriver(ctrl, dom_reader=dom)
        spec = self._spec("gemini")
        found = driver.download_last_image(spec, tmp_path)  # empty dir -> None
        assert found is None
        # All four attempts clicked the DOM-located download point.
        assert ctrl.clicked[0] == (70, 45)
        assert dom.calls[0] == "download"

    def test_master_switch_skips_dom_entirely(self, monkeypatch):
        from skills.automation_engine.ai_chain import sites

        monkeypatch.setenv("AI_CHAIN_DOM", "0")
        ctrl = _StubController()
        dom = _FakeDomReader(points={"copy": (0.88, 0.87), "composer": (0.3, 0.94)})
        driver = sites.WebAiDriver(ctrl, dom_reader=dom)
        assert driver._dom_point(self._spec(), "copy") is None
        assert driver._dom_point(self._spec(), "composer") is None
        assert dom.calls == []  # reader was never touched
