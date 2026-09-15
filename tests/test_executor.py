"""Tests for brain/executor.py.

Tests handler registration, dispatch, error handling,
and the fallback default handler.
"""

import pytest
from brain.context import BrainContext
from brain.executor import BrainExecutor
from brain.intent import Intent


@pytest.fixture
def executor():
    return BrainExecutor()


@pytest.fixture
def context():
    return BrainContext(original_text="test")


# ---------------------------------------------------------------------------
# Handler Registration
# ---------------------------------------------------------------------------


class TestHandlerRegistration:
    def test_register_handler(self, executor):
        """Registering a handler should make it callable."""

        def my_handler(intent):
            return {"message": f"Handled {intent.action}"}

        executor.register_handler("test_action", my_handler)
        result = executor.execute(Intent(action="test_action"))
        assert result["success"] is True
        assert result["status"] == "executed"
        assert result["result"]["message"] == "Handled test_action"

    def test_register_default_handler(self, executor):
        """Default handler should be called for unknown actions."""

        def default_handler(intent):
            return {"message": "Default fallback"}

        executor.set_default_handler(default_handler)
        result = executor.execute(Intent(action="unknown_action"))
        assert result["success"] is True
        assert result["result"]["message"] == "Default fallback"


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------


class TestExecute:
    def test_execute_returns_expected_structure(self, executor):
        """Execute should return dict with success/status/result/error."""

        def handler(intent):
            return None

        executor.register_handler("test", handler)
        result = executor.execute(Intent(action="test"))
        assert "success" in result
        assert "status" in result
        assert "result" in result
        assert "error" in result

    def test_execute_passes_intent_to_handler(self, executor):
        """Handler should receive the correct intent."""
        captured = {}

        def handler(intent):
            captured["action"] = intent.action
            captured["target"] = intent.target
            return None

        executor.register_handler("search", handler)
        executor.execute(Intent(action="search", target="python"))
        assert captured["action"] == "search"
        assert captured["target"] == "python"

    def test_execute_with_context(self, executor, context):
        """Execute should accept an optional context."""

        def handler(intent):
            return {"ok": True}

        executor.register_handler("test", handler)
        # This should not crash
        result = executor.execute(Intent(action="test"), context=context)
        assert result["success"] is True


# ---------------------------------------------------------------------------
# No Handler Found
# ---------------------------------------------------------------------------


class TestNoHandler:
    def test_no_handler_for_action(self, executor):
        """Unknown action with no default handler returns error."""
        result = executor.execute(Intent(action="nonexistent"))
        assert result["success"] is False
        assert result["status"] == "no_handler"
        assert "Unknown action" in result["error"]

    def test_no_handler_error_message(self, executor):
        """Error should include the action name."""
        result = executor.execute(Intent(action="bogus"))
        assert "bogus" in result["error"]


# ---------------------------------------------------------------------------
# Error Handling
# ---------------------------------------------------------------------------


class TestErrorHandling:
    def test_handler_exception_caught(self, executor):
        """Exceptions in handler should be caught and returned as error."""

        def broken_handler(intent):
            raise ValueError("Something broke")

        executor.register_handler("broken", broken_handler)
        result = executor.execute(Intent(action="broken"))
        assert result["success"] is False
        assert result["status"] == "error"
        assert "Something broke" in result["error"]

    def test_default_handler_exception_caught(self, executor):
        """Exceptions in default handler should be caught."""

        def broken_default(intent):
            raise RuntimeError("Default died")

        executor.set_default_handler(broken_default)
        result = executor.execute(Intent(action="anything"))
        assert result["success"] is False
        assert "Default died" in result["error"]


# ---------------------------------------------------------------------------
# Multiple Handlers
# ---------------------------------------------------------------------------


class TestMultipleHandlers:
    def test_different_actions_different_handlers(self, executor):
        """Different actions should dispatch to different handlers."""
        results = []

        def handler_a(intent):
            results.append("a")
            return None

        def handler_b(intent):
            results.append("b")
            return None

        executor.register_handler("action_a", handler_a)
        executor.register_handler("action_b", handler_b)

        executor.execute(Intent(action="action_a"))
        executor.execute(Intent(action="action_b"))

        assert results == ["a", "b"]

    def test_handler_replacement(self, executor):
        """Registering the same action should replace the handler."""

        def old_handler(intent):
            return {"version": "old"}

        def new_handler(intent):
            return {"version": "new"}

        executor.register_handler("test", old_handler)
        executor.register_handler("test", new_handler)
        result = executor.execute(Intent(action="test"))
        assert result["result"]["version"] == "new"


# ---------------------------------------------------------------------------
# Built-in "open" handler: application -> website -> ask (open_choice)
# ---------------------------------------------------------------------------


class TestOpenHandlerFlow:
    """handle_open search order: applications, then websites, then ask."""

    def _executor(self, monkeypatch, app_skill, site_skill):
        monkeypatch.setattr("skills.app_launcher.main.AppLauncherSkill", app_skill)
        monkeypatch.setattr("skills.browser.main.BrowserSkill", site_skill)
        return BrainExecutor()

    def test_application_is_tried_before_website(self, monkeypatch):
        """A known app opens directly; the website skill is never consulted."""

        class FakeAppSkill:
            @staticmethod
            def execute(intent):
                return {
                    "success": True,
                    "status": "executed",
                    "result": {"application": "Chrome", "path": r"C:\chrome.exe"},
                }

        class FakeBrowserSkill:
            @staticmethod
            def execute(intent):
                raise AssertionError("website must not be tried when the app exists")

        executor = self._executor(monkeypatch, FakeAppSkill, FakeBrowserSkill)
        result = executor.execute(Intent(action="open", target="chrome"))

        assert result["success"] is True
        assert result["result"]["action"] == "open_application"
        assert result["result"]["application"] == "Chrome"

    def test_website_opened_when_app_not_found(self, monkeypatch):
        """App not found -> the website knowledge base is searched."""

        class FakeAppSkill:
            @staticmethod
            def execute(intent):
                return {"success": False, "status": "not_found", "error": "Application not found"}

        class FakeBrowserSkill:
            @staticmethod
            def execute(intent):
                return {
                    "success": True,
                    "status": "executed",
                    "result": {"website": "YouTube", "url": "https://youtube.com"},
                }

        executor = self._executor(monkeypatch, FakeAppSkill, FakeBrowserSkill)
        result = executor.execute(Intent(action="open", target="youtube"))

        assert result["success"] is True
        assert result["result"]["action"] == "open_website"
        assert result["result"]["url"] == "https://youtube.com"

    def test_unknown_target_offers_open_choice(self, monkeypatch):
        """Neither an app nor a website -> scan / search-on-browser prompt."""

        class FakeAppSkill:
            @staticmethod
            def execute(intent):
                return {"success": False, "status": "not_found", "error": "Application not found"}

        class FakeBrowserSkill:
            @staticmethod
            def execute(intent):
                return {"success": False, "status": "not_found", "error": "Website not found"}

        executor = self._executor(monkeypatch, FakeAppSkill, FakeBrowserSkill)
        result = executor.execute(Intent(action="open", target="mystery"))

        assert result["success"] is False
        assert result["status"] == "needs_decision"
        assert result["result"]["visual"]["type"] == "open_choice"
        assert result["result"]["visual"]["data"]["name"] == "mystery"

    def test_found_but_uncategorized_app_keeps_decision_prompt(self, monkeypatch):
        """An app that exists (ignored/unattended) keeps its own prompt."""

        class FakeAppSkill:
            @staticmethod
            def execute(intent):
                return {
                    "success": False,
                    "status": "needs_decision",
                    "handled": True,
                    "error": "not categorized yet",
                    "result": {
                        "visual": {
                            "type": "app_decision",
                            "data": {"name": "Slack", "app_status": "unattended"},
                        }
                    },
                }

        class FakeBrowserSkill:
            @staticmethod
            def execute(intent):
                raise AssertionError("website must not be tried for a found app")

        executor = self._executor(monkeypatch, FakeAppSkill, FakeBrowserSkill)
        result = executor.execute(Intent(action="open", target="slack"))

        assert result["success"] is False
        assert result["status"] == "needs_decision"
        assert result["result"]["visual"]["type"] == "app_decision"


# ---------------------------------------------------------------------------
# Default Handler Priority
# ---------------------------------------------------------------------------


class TestHandlerPriority:
    def test_specific_handler_takes_priority(self, executor):
        """Specific handler should be used over default handler."""

        def specific(intent):
            return {"source": "specific"}

        def default_handler(intent):
            return {"source": "default"}

        executor.register_handler("exists", specific)
        executor.set_default_handler(default_handler)

        result = executor.execute(Intent(action="exists"))
        assert result["result"]["source"] == "specific"

    def test_default_fallback(self, executor):
        """Default handler should be used when no specific handler exists."""

        def default_handler(intent):
            return {"source": "default"}

        executor.set_default_handler(default_handler)
        result = executor.execute(Intent(action="missing"))
        assert result["result"]["source"] == "default"
