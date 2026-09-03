"""Tests for '.'-sentence splitting and site-aware 'open X and search Q' parsing.

Covers:
    - brain/interpreter: interpret_many() splits on '.', the query is
      everything after the keyword 'search', and "open X and search Q"
      becomes an open intent + a site-aware search intent.
    - brain/engine: every parsed sentence intent executes in sequence.
    - skills/browser: a search intent with a site searches on that website,
      and falls back to Google for apps (e.g. Chrome).
"""

from typing import Any

import pytest

from brain.engine import BrainEngine
from brain.intent import Intent
from brain.interpreter import interpret, interpret_many, split_queries
from brain.planner import Planner
from knowledge.entity_resolver import EntityResolver

# ---------------------------------------------------------------------------
# Interpreter: query splitting
# ---------------------------------------------------------------------------


def test_split_queries_on_full_stop():
    """'.' separates queries; the query stops at the full stop."""
    assert split_queries("open youtube and search AI. also tell me about weather") == [
        "open youtube and search AI",
        "also tell me about weather",
    ]


def test_split_queries_ignores_empty_fragments():
    assert split_queries("open chrome.") == ["open chrome"]
    assert split_queries("...") == []
    assert split_queries("") == []


# ---------------------------------------------------------------------------
# Interpreter: compound "open X and search Q"
# ---------------------------------------------------------------------------


def test_open_chrome_and_search_uses_everything_after_search():
    """Query = everything after 'search' (stopped at the sentence end)."""
    intents = interpret_many("open chrome and search what is ai")
    assert len(intents) == 2
    assert intents[0].action == "open"
    assert intents[0].target == "chrome"
    assert intents[1].action == "search"
    assert intents[1].target == "what is ai"
    assert intents[1].site == "chrome"


def test_open_youtube_and_search_ai_carries_site():
    """Second intent targets 'youtube' and searches 'AI' on it."""
    intents = interpret_many("open youtube and search AI")
    assert [(i.action, i.target) for i in intents] == [
        ("open", "youtube"),
        ("search", "AI"),
    ]
    assert intents[1].site == "youtube"


def test_open_youtube_and_play_carries_site():
    """Second intent targets 'youtube' and plays 'lofi' on it."""
    intents = interpret_many("open youtube and play lofi")
    assert [(i.action, i.target) for i in intents] == [
        ("open", "youtube"),
        ("play", "lofi"),
    ]
    assert intents[1].site == "youtube"


def test_open_and_play_with_nothing_after_keyword_just_opens():
    """'open chrome and play' with no media only opens chrome."""
    intents = interpret_many("open chrome and play")
    assert [(i.action, i.target) for i in intents] == [("open", "chrome")]


def test_interpret_returns_first_intent():
    """interpret() keeps its single-Intent API (first query wins)."""
    intent = interpret("open chrome and search what is ai. check github")
    assert intent.action == "open"
    assert intent.target == "chrome"


# ---------------------------------------------------------------------------
# Interpreter: multi-sentence input
# ---------------------------------------------------------------------------


def test_period_split_produces_all_queries():
    """'open youtube and search AI. also tell me about weather' => 3 intents."""
    intents = interpret_many("open youtube and search AI. also tell me about weather")
    assert len(intents) == 3

    # Query 1: open youtube + search AI on youtube
    assert intents[0].action == "open"
    assert intents[0].target == "youtube"
    assert intents[1].action == "search"
    assert intents[1].target == "AI"
    assert intents[1].site == "youtube"

    # Query 2: the text after the full stop, kept verbatim for conversation
    assert intents[2].action == "unknown"
    assert intents[2].raw_text == "also tell me about weather"


def test_two_plain_sentences():
    intents = interpret_many("open chrome. check github")
    assert [(i.action, i.target) for i in intents] == [
        ("open", "chrome"),
        ("check", "github"),
    ]


def test_open_and_play_then_second_sentence():
    """'open youtube and play lofi. ...' keeps the split on the full stop."""
    intents = interpret_many("open youtube and play lofi. what is the weather")
    assert [(i.action, i.target) for i in intents] == [
        ("open", "youtube"),
        ("play", "lofi"),
        ("what", "weather"),
    ]
    assert intents[1].site == "youtube"


# ---------------------------------------------------------------------------
# Interpreter: plain searches + legacy single intents
# ---------------------------------------------------------------------------


def test_plain_search_query_is_everything_after_keyword():
    """Even 'what' / 'is' after the keyword stay in the query."""
    intent = interpret("search what is ai")
    assert intent.action == "search"
    assert intent.target == "what is ai"
    assert intent.site == ""


def test_plain_find_maps_to_search():
    intent = interpret("find python tutorials")
    assert intent.action == "search"
    assert intent.target == "python tutorials"


def test_plain_play_unchanged():
    intent = interpret("play lofi")
    assert intent.action == "play"
    assert intent.target == "lofi"
    assert intent.site == ""


def test_legacy_single_commands_unchanged():
    assert (interpret("play lofi").action, interpret("play lofi").target) == ("play", "lofi")
    assert (interpret("open the chrome").action, interpret("open the chrome").target) == (
        "open",
        "chrome",
    )
    assert (interpret("scan my system").action, interpret("scan my system").target) == (
        "scan",
        "system",
    )
    hello = interpret("hello sarthi")
    assert hello.action == "unknown"
    assert hello.confidence == 0.0


def test_slash_commands_survive():
    intents = interpret_many("/remember my name is Alice")
    assert len(intents) == 1
    assert intents[0].action == "remember"
    assert intents[0].target == "my name is Alice"


def test_punctuation_only_input_returns_unknown():
    assert interpret("...").action == "unknown"
    assert interpret_many("...") == []
    assert interpret("").action == "unknown"


# ---------------------------------------------------------------------------
# Engine: sequential execution of every parsed query
# ---------------------------------------------------------------------------


class RecordingExecutor:
    """Collects every executed intent; always succeeds."""

    def __init__(self):
        self.executed: list[Intent] = []

    def register_skill(self, skill) -> None:  # skills never run in these tests
        pass

    def execute(self, intent: Intent, context=None) -> dict[str, Any]:
        self.executed.append(intent)
        return {"success": True, "status": "executed", "result": {}}


def _entities() -> list[dict]:
    return [
        {"name": "Chrome", "aliases": ["chrome", "google chrome"], "category": "applications"},
        {"name": "YouTube", "aliases": ["youtube", "yt"], "category": "websites"},
    ]


def _engine(executor: RecordingExecutor) -> BrainEngine:
    return BrainEngine(
        resolver=EntityResolver(entities=_entities()),
        executor=executor,  # type: ignore
        planner=Planner(),
    )


def test_engine_executes_open_then_search_in_order():
    """'open chrome and search python tutorials' runs both steps."""
    executor = RecordingExecutor()
    response = _engine(executor).process("open chrome and search python tutorials")

    assert response.success is True
    assert [i.action for i in executor.executed] == ["open", "search"]
    assert [i.target for i in executor.executed] == ["Chrome", "python tutorials"]
    assert [i.site for i in executor.executed] == ["", "chrome"]


def test_engine_executes_open_then_play_in_order():
    """'open youtube and play lofi' runs both steps."""
    executor = RecordingExecutor()
    response = _engine(executor).process("open youtube and play lofi")

    assert response.success is True
    assert [i.action for i in executor.executed] == ["open", "play"]
    assert [i.target for i in executor.executed] == ["YouTube", "lofi"]
    assert [i.site for i in executor.executed] == ["", "youtube"]


def test_response_steps_cover_every_executed_action():
    """process() exposes one API payload per executed step."""
    executor = RecordingExecutor()
    response = _engine(executor).process("open youtube and play lofi. how are you")

    steps = response.steps or []
    assert [s["action"] for s in steps] == ["open", "play", "how"]
    assert [s["target"] for s in steps] == ["YouTube", "lofi", ""]
    assert all(s["success"] is True for s in steps)
    # The last step mirrors the top-level response fields
    last = steps[-1]
    api = response.to_api_dict()
    assert api["action"] == last["action"]
    assert api["target"] == last["target"]
    assert api["text"] == last["text"]
    assert api["steps"] == steps


def test_single_command_steps_have_one_entry():
    """A single-step command still reports exactly one step."""
    executor = RecordingExecutor()
    response = _engine(executor).process("open youtube")
    steps = response.steps or []
    assert len(steps) == 1
    assert steps[0]["action"] == "open"
    assert steps[0]["target"] == "YouTube"


def test_failing_step_is_kept_in_steps():
    """Fail-fast stops after the first error and keeps that step visible."""

    class FailSecondExecutor(RecordingExecutor):
        def execute(self, intent, context=None):
            self.executed.append(intent)
            if len(self.executed) == 2:
                return {"success": False, "status": "error", "error": "boom"}
            return {"success": True, "status": "executed", "result": {}}

    executor = FailSecondExecutor()
    response = _engine(executor).process("open chrome. check github")

    steps = response.steps or []
    assert response.success is False
    assert [s["action"] for s in steps] == ["open", "check"]
    assert steps[-1]["success"] is False
    assert steps[-1]["error"] == "boom"


def test_engine_executes_period_split_queries_in_order():
    """Each '.'-separated query executes in sequence (3 steps here)."""
    executor = RecordingExecutor()
    response = _engine(executor).process("open youtube and search AI. also tell me about weather")

    assert response.success is True
    assert [i.action for i in executor.executed] == ["open", "search", "unknown"]
    assert [i.target for i in executor.executed] == ["YouTube", "AI", "also weather"]
    assert executor.executed[1].site == "youtube"
    assert executor.executed[2].raw_text == "also tell me about weather"


# ---------------------------------------------------------------------------
# Browser skill: site-aware search
# ---------------------------------------------------------------------------


class FakeKnowledge:
    """Minimal knowledge stand-in with one known website."""

    def __init__(self):
        self.sites = {
            "youtube": {"name": "YouTube", "url": "https://www.youtube.com"},
        }

    def find_website(self, name: str) -> dict | None:
        return self.sites.get((name or "").lower())


@pytest.fixture
def browser_skill(monkeypatch):
    from skills.browser.main import BrowserSkill

    monkeypatch.setattr("skills.browser.main.get_test_mode", lambda: True)
    skill = BrowserSkill(knowledge_manager=FakeKnowledge())
    # Never hit the network for the first YouTube video.
    skill._get_first_youtube_video = lambda query: None
    return skill


def test_search_on_site_uses_opened_website(browser_skill):
    """'open youtube and search AI' searches youtube.com for AI."""
    result = browser_skill.execute(Intent(action="search", target="AI", site="youtube"))
    assert result.get("success") is True
    data = result.get("result") or {}
    assert data.get("website") == "YouTube"
    assert data.get("url") == "https://www.youtube.com/results?search_query=AI"
    assert data.get("query") == "AI"


def test_search_on_app_site_falls_back_to_google(browser_skill):
    """'open chrome and search what is ai' Google-searches (Chrome is an app)."""
    result = browser_skill.execute(Intent(action="search", target="what is ai", site="chrome"))
    assert result.get("success") is True
    data = result.get("result") or {}
    assert data.get("website") == "Google"
    assert "google.com/search?q=what+is+ai" in data.get("url", "")


def test_plain_search_still_works(browser_skill):
    """A search without a site keeps the old first-word-site sniffing."""
    result = browser_skill.execute(Intent(action="search", target="youtube AI"))
    assert result.get("success") is True
    data = result.get("result") or {}
    assert data.get("website") == "YouTube"
    assert data.get("url") == "https://www.youtube.com/results?search_query=AI"
