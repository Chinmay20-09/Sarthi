"""Tests for the Browser Awareness capability.

Everything is tested with pure logic, fake providers and fake browser
components — the suite never needs Playwright, Chrome or the local model.

Covers: snapshot building (caps/filters/sanitization), Hermes JSON
validation, the pure safety gate, selector allow-list, the manager
inspect -> observe -> validate -> execute -> reinspect loop (incl.
cleanup and confirmation halts), skill parsing + test-mode planning,
interpreter routing (URL sentences -> browse, known sites stay fast),
and the Brain 'browse' handler delegation.
"""

import pytest

from brain.intent import Intent
from brain.interpreter import interpret, interpret_many
from skills.browser_awareness.page_snapshot import build_page_snapshot, snapshot_for_hermes
from skills.browser_awareness.schemas import (
    ActionOutcome,
    ElementInfo,
    InspectionResult,
    PageSnapshot,
    RecommendedAction,
    validate_inspection,
)


def _element(
    kind="button",
    text="Pricing",
    selector="a:nth-of-type(2)",
    visible=True,
    enabled=True,
    name="",
    placeholder="",
    label="",
    href="",
):
    return ElementInfo(
        id="el_1",
        kind=kind,
        text=text,
        selector=selector,
        visible=visible,
        enabled=enabled,
        name=name,
        placeholder=placeholder,
        label=label,
        href=href,
    )


def _snapshot(elements=None, text="Page body text.", url="https://example.com/"):
    return PageSnapshot(
        url=url,
        title="Example",
        text=text,
        elements=elements or [_element()],
    )


class TestSnapshotBuilding:
    def test_hidden_and_disabled_elements_are_dropped(self):
        raw = [
            {"kind": "button", "text": "ok", "selector": "#a", "visible": True, "enabled": True},
            {
                "kind": "button",
                "text": "ghost",
                "selector": "#b",
                "visible": False,
                "enabled": True,
            },
            {
                "kind": "button",
                "text": "locked",
                "selector": "#c",
                "visible": True,
                "enabled": False,
            },
            {"kind": "link", "text": "no selector", "visible": True, "enabled": True},
        ]
        snapshot = build_page_snapshot("https://x.io", "X", "body", raw)
        assert [e.text for e in snapshot.elements] == ["ok"]

    def test_element_cap_is_enforced(self):
        raw = [
            {
                "kind": "link",
                "text": f"l{i}",
                "selector": f"#id{i}",
                "visible": True,
                "enabled": True,
            }
            for i in range(60)
        ]
        snapshot = build_page_snapshot("https://x.io", "X", "body", raw, max_elements=10)
        assert len(snapshot.elements) == 10
        assert snapshot.elements_truncated is True

    def test_text_is_capped_and_flag_set(self):
        snapshot = build_page_snapshot("https://x.io", "X", "word " * 1000, [], max_text_chars=100)
        assert snapshot.text_truncated is True
        assert len(snapshot.text) < 200

    def test_sensitive_field_values_never_leak(self):
        raw = [
            {
                "kind": "input",
                "name": "password",
                "placeholder": "SuperSecret123",
                "selector": "input[name='password']",
                "visible": True,
                "enabled": True,
            }
        ]
        snapshot = build_page_snapshot("https://x.io", "X", "", raw)
        element = snapshot.elements[0]
        assert "SuperSecret123" not in element.placeholder

    def test_duplicate_selectors_are_dropped(self):
        raw = [
            {
                "kind": "button",
                "text": "first",
                "selector": "#dup",
                "visible": True,
                "enabled": True,
            },
            {
                "kind": "button",
                "text": "second",
                "selector": "#dup",
                "visible": True,
                "enabled": True,
            },
        ]
        snapshot = build_page_snapshot("https://x.io", "X", "", raw)
        assert len(snapshot.elements) == 1

    def test_hermes_block_lists_element_ids_and_kinds(self):
        snapshot = build_page_snapshot(
            "https://example.com",
            "Example",
            "Welcome",
            [
                {
                    "kind": "link",
                    "text": "Pricing",
                    "href": "/pricing",
                    "selector": "#pricing",
                    "visible": True,
                    "enabled": True,
                }
            ],
        )
        block = snapshot_for_hermes(snapshot)
        assert "[link]" in block and "id=el_1" in block and "Pricing" in block
        assert "<html" not in block  # never raw HTML


class _FakeProvider:
    """Provider stand-in returning canned text (or raising)."""

    def __init__(self, text="", error=""):
        self._text = text
        self._error = error

    def generate(self, task):
        from hermes.providers.base import ProviderResponse

        if self._error:
            return ProviderResponse(
                success=False, provider="Ollama", model="hermes3:8b", text="", error=self._error
            )
        return ProviderResponse(
            success=True, provider="Ollama", model="hermes3:8b", text=self._text
        )


class TestHermesInspector:
    def _inspector(self, provider):
        from skills.browser_awareness.hermes_inspector import HermesInspector

        return HermesInspector(provider=provider)

    def test_valid_observation_parsed(self):
        payload = (
            '{"status": "continue", "understanding": "Pricing link visible.", '
            '"action": {"type": "click", "element_id": "el_1", '
            '"rationale": "opens pricing"}}'
        )
        provider = _FakeProvider(text=payload)
        result = self._inspector(provider).observe("find pricing", _snapshot())
        assert result.status == "continue"
        assert result.action is not None
        assert result.action.type == "click"
        assert result.action.element_id == "el_1"

    def test_json_in_fences_parsed(self):
        provider = _FakeProvider(
            text='```json\n{"status": "done", "understanding": "on pricing"}\n```'
        )
        result = self._inspector(provider).observe("find pricing", _snapshot())
        assert result.status == "done"
        assert result.action is None

    def test_garbage_is_blocked_not_executed(self):
        provider = _FakeProvider(text="sure, I'll click the pricing link for you!")
        result = self._inspector(provider).observe("find pricing", _snapshot())
        assert result.status == "blocked"

    def test_provider_failure_is_blocked(self):
        provider = _FakeProvider(error="model down")
        result = self._inspector(provider).observe("find pricing", _snapshot())
        assert result.status == "blocked"

    def test_provider_exception_is_blocked(self):
        class ExplodingProvider:
            def generate(self, task):
                raise RuntimeError("boom")

        result = self._inspector(ExplodingProvider()).observe("find pricing", _snapshot())
        assert result.status == "blocked"

    def test_malformed_schema_is_blocked(self):
        provider = _FakeProvider(
            text='{"status": "continue", "action": {"type": "hack", "element_id": "el_1"}}'
        )
        result = self._inspector(provider).observe("find pricing", _snapshot())
        assert result.status == "blocked"


class TestSafetyGate:
    def test_valid_click_passes(self):
        inspection = InspectionResult(
            status="continue",
            action=RecommendedAction(type="click", element_id="el_1"),
        )
        assert validate_inspection(inspection, _snapshot()) == []

    def test_unknown_element_rejected(self):
        inspection = InspectionResult(
            status="continue",
            action=RecommendedAction(type="click", element_id="el_99"),
        )
        assert validate_inspection(inspection, _snapshot())

    def test_kind_mismatch_rejected(self):
        """Hermes may not type into a link."""
        inspection = InspectionResult(
            status="continue",
            action=RecommendedAction(type="type", element_id="el_1", value="hi"),
        )
        snapshot = _snapshot(elements=[_element(kind="link")])
        problems = validate_inspection(inspection, snapshot)
        assert any("link" in p for p in problems)

    def test_hidden_element_rejected(self):
        inspection = InspectionResult(
            status="continue",
            action=RecommendedAction(type="click", element_id="el_1"),
        )
        snapshot = _snapshot(elements=[_element(visible=False)])
        assert any("hidden" in p for p in validate_inspection(inspection, snapshot))

    def test_navigate_requires_http(self):
        bad = InspectionResult(
            status="continue", action=RecommendedAction(type="navigate", url="file:///etc/passwd")
        )
        assert validate_inspection(bad, _snapshot())
        good = InspectionResult(
            status="continue",
            action=RecommendedAction(type="navigate", url="https://example.com/pricing"),
        )
        assert validate_inspection(good, _snapshot()) == []

    def test_done_needs_no_action(self):
        inspection = InspectionResult(status="done", understanding="reached")
        assert validate_inspection(inspection, _snapshot()) == []


class TestSelectorSafety:
    def _is_safe(self, selector):
        from skills.browser_awareness.executor import _is_safe_selector

        return _is_safe_selector(selector)

    @pytest.mark.parametrize(
        "selector",
        [
            "#pricing",
            '[data-testid="pricing"]',
            'input[name="email"]',
            "button:nth-of-type(2)",
            "div:nth-of-type(1) > a:nth-of-type(3)",
            "a",
        ],
    )
    def test_generated_selectors_allowed(self, selector):
        assert self._is_safe(selector)

    @pytest.mark.parametrize(
        "selector",
        [
            "javascript:alert(1)",
            "#pricing img[src=x onerror=alert(1)]",
            "a[href='/x']",
            "button > script",
            'body:has-text("drop")',
            ".classy",
            "xpath=//a",
        ],
    )
    def test_foreign_selectors_denied(self, selector):
        assert not self._is_safe(selector)


class _FakeSession:
    def __init__(self):
        self.page = object()
        self.closed = False

    def close(self):
        self.closed = True


class _ScriptedHermes:
    def __init__(self, results):
        self._results = list(results)
        self.calls = []

    def observe(self, objective, snapshot):
        self.calls.append((objective, snapshot.url))
        return self._results.pop(0)


class _RecordingExecutor:
    """Records perform() calls; the outcome script decides the manager path."""

    def __init__(self, outcomes):
        self._outcomes = list(outcomes)

    def perform(self, inspection, snapshot, confirmed=False):
        return self._outcomes.pop(0)


def _click_action(element_id="el_1"):
    return InspectionResult(
        status="continue",
        understanding="clicking",
        action=RecommendedAction(type="click", element_id=element_id, rationale="next"),
    )


class TestManagerLoop:
    def _manager(self, session, snapshot, hermes, outcomes, announce=False):
        from skills.browser_awareness.manager import BrowserAwarenessManager

        class FixedInspector:
            def __init__(self, page):
                self.page = page
                self.count = 0

            def inspect(self):
                self.count += 1
                return snapshot

        def executor_factory(page):
            return _RecordingExecutor(outcomes)

        return BrowserAwarenessManager(
            session_factory=lambda url: session,
            inspector_factory=FixedInspector,
            hermes=hermes,
            executor_factory=executor_factory,
            announce_progress=announce,
        )

    def test_completes_after_execute_then_done(self):
        session = _FakeSession()
        snapshot = _snapshot()
        hermes = _ScriptedHermes(
            [_click_action(), InspectionResult(status="done", understanding="Found it.")]
        )
        manager = self._manager(
            session,
            snapshot,
            hermes,
            [ActionOutcome(ok=True, status="executed", message="Clicked el_1.")],
        )

        result = manager.run("https://example.com", "find pricing")
        assert result.status == "completed"
        assert result.success is True
        assert result.final_understanding == "Found it."
        assert session.closed is True  # temporary context destroyed
        assert len(hermes.calls) == 2
        assert "Clicked el_1" in " ".join(result.steps)

    def test_blocked_observation_stops_immediately(self):
        session = _FakeSession()
        hermes = _ScriptedHermes([InspectionResult(status="blocked", message="login required")])
        manager = self._manager(session, _snapshot(), hermes, [])

        result = manager.run("https://example.com", "buy thing")
        assert result.status == "blocked"
        assert "login" in result.message
        assert session.closed is True

    def test_high_impact_action_halts_for_confirmation(self):
        session = _FakeSession()
        inspection = _click_action()
        inspection.action.requires_confirmation = True
        hermes = _ScriptedHermes([inspection])
        manager = self._manager(
            session,
            _snapshot(),
            hermes,
            [ActionOutcome(ok=False, status="needs_confirmation", message="confirm?")],
        )

        result = manager.run("https://example.com", "purchase", confirm=False)
        assert result.status == "needs_confirmation"
        assert session.closed is True

    def test_session_closed_even_when_run_raises(self):
        session = _FakeSession()

        class BrokenInspector:
            def inspect(self):
                raise RuntimeError("boom")

        from skills.browser_awareness.manager import BrowserAwarenessManager

        manager = BrowserAwarenessManager(
            session_factory=lambda url: session,
            inspector_factory=lambda page: BrokenInspector(),
            hermes=_ScriptedHermes([]),
            executor_factory=lambda page: _RecordingExecutor([]),
            announce_progress=False,
        )
        result = manager.run("https://example.com")
        assert result.status == "failed"
        assert session.closed is True

    def test_step_limit_stops_cleanly(self):
        session = _FakeSession()
        hermes = _ScriptedHermes([_click_action()] * 20)
        manager = self._manager(
            session,
            _snapshot(),
            hermes,
            [ActionOutcome(ok=True, status="executed", message="ok")] * 20,
        )
        result = manager.run("https://example.com", "task", max_steps=3)
        assert result.status == "blocked"
        assert "3 steps" in result.message
        assert session.closed is True

    def test_voice_progress_announces_start_action_and_done(self, monkeypatch):
        """Live spoken progress mirrors the AI-chain announcement pattern."""
        spoken = []
        monkeypatch.setattr("skills.browser_awareness.manager.announce", spoken.append)
        session = _FakeSession()
        snapshot = _snapshot(elements=[_element(kind="link", text="Pricing")])
        hermes = _ScriptedHermes(
            [_click_action(), InspectionResult(status="done", understanding="Found it.")]
        )
        manager = self._manager(
            session,
            snapshot,
            hermes,
            [ActionOutcome(ok=True, status="executed", message="Clicked el_1.")],
            announce=True,
        )

        result = manager.run("https://example.com", "find pricing")
        assert result.status == "completed"
        # Start: names the site, like "Hands off..." does for the AI chain.
        assert spoken[0].startswith("Browser awareness started.")
        assert "example.com" in spoken[0]
        # Mid-run: what is happening, in user language (not element ids).
        assert "Clicking Pricing" in spoken[1]
        # Terminal: outcome summary.
        assert spoken[2].startswith("Done.")


class TestBrowseRequestParsing:
    def _parse(self, text):
        from skills.browser_awareness.main import parse_browse_request

        return parse_browse_request(text)

    def test_slash_command(self):
        url, objective = self._parse("/browse example.com and find the pricing page")
        assert url == "https://example.com"
        assert "pricing" in objective

    def test_open_sentence(self):
        url, objective = self._parse("open example.com and find the More Information link")
        assert url == "https://example.com"
        assert "More Information" in objective

    def test_full_url_with_path_kept(self):
        url, _ = self._parse("browse https://example.com/pricing tell me about plans")
        assert url == "https://example.com/pricing"

    def test_no_objective_describes_page(self):
        url, objective = self._parse("/browse example.com")
        assert url == "https://example.com"
        assert objective == ""

    def test_no_url_returns_empty(self):
        assert self._parse("what is the weather") == ("", "")


class TestSkill:
    def _skill(self):
        from skills.browser_awareness.main import BrowserAwarenessSkill

        return BrowserAwarenessSkill()

    def test_test_mode_plans_without_browser(self, monkeypatch):
        import brain.modes as modes

        monkeypatch.setattr(modes, "_test_mode", True)
        result = self._skill().execute(
            Intent(action="browse", raw_text="/browse example.com and find the pricing page")
        )
        assert result["success"] is True
        assert result["status"] == "planned"
        assert "example.com" in result["result"]["message"]

    def test_unknown_action_not_claimed(self):
        result = self._skill().execute(Intent(action="play", target="music"))
        assert result["success"] is False
        assert "handled" not in result  # executor keeps searching

    def test_missing_url_errors_clearly(self):
        result = self._skill().execute(Intent(action="browse", raw_text="browse"))
        assert result["success"] is False
        assert "website" in result["error"]


class TestInterpreterRouting:
    def test_open_domain_and_task_becomes_single_browse_intent(self):
        intent = interpret("open example.com and find the pricing page")
        assert intent.action == "browse"
        assert intent.target == "example.com"
        assert intent.raw_text  # skill re-parses url + objective from raw text

    def test_known_youtube_stays_two_fast_intents(self):
        intents = interpret_many("open youtube and play motivation video")
        assert [i.action for i in intents] == ["open", "play"]

    def test_known_domain_youtube_com_stays_fast(self):
        intents = interpret_many("open youtube.com and play a song")
        assert [i.action for i in intents] == ["open", "play"]

    def test_browse_action_word(self):
        intent = interpret("browse example.com")
        assert intent.action == "browse"


class TestBrainBrowseHandler:
    def test_browse_intent_delegates_to_awareness_skill(self, monkeypatch):
        calls = {}

        class FakeAwarenessSkill:
            @staticmethod
            def execute(intent):
                calls["action"] = intent.action
                return {
                    "success": True,
                    "handled": True,
                    "status": "completed",
                    "result": {"message": "Found the pricing page."},
                }

        monkeypatch.setattr(
            "skills.browser_awareness.main.BrowserAwarenessSkill", FakeAwarenessSkill
        )
        from brain.executor import BrainExecutor

        executor = BrainExecutor()
        result = executor.execute(
            Intent(
                action="browse",
                target="example.com",
                raw_text="open example.com and find the pricing page",
            )
        )
        assert result["success"] is True
        assert result["status"] == "completed"
        assert calls["action"] == "browse"
