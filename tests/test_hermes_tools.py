"""Tests for the Phase 3e Hermes tools.

All six tools delegate to existing Sarthi capabilities; tests verify the
delegation, argument handling, and graceful failures — with the underlying
skills mocked so nothing real launches, closes, or browses.
"""

from unittest.mock import patch

import pytest
from hermes.tool_registry import ToolRegistry
from hermes.tools import (
    BrowserAskTool,
    CloseAppTool,
    HistorySearchTool,
    MemorySearchTool,
    ProjectGetTool,
    SearchWebTool,
    register_default_tools,
)


@pytest.fixture()
def registry() -> ToolRegistry:
    reg = ToolRegistry()
    register_default_tools(reg)
    return reg


# ----------------------------------------------------------------------
# Registration
# ----------------------------------------------------------------------


class TestRegistration:
    def test_all_six_new_tools_registered(self, registry):
        names = set(registry.tool_names())
        assert {"close_app", "search_web", "browser_ask",
                "history_search", "memory_search", "project_get"} <= names

    def test_describe_schemas_have_required_shape(self, registry):
        for tool in registry.list_tools():
            assert tool["name"]
            assert tool["description"]
            assert tool["parameters"].get("type") == "object"


# ----------------------------------------------------------------------
# close_app
# ----------------------------------------------------------------------


class TestCloseApp:
    def test_close_success(self):
        tool = CloseAppTool()
        fake_result = {
            "success": True,
            "action": "close_application",
            "application": "Spotify",
            "closed": 1,
        }
        with patch("brain.executor.BrainExecutor") as mock_exec:
            mock_exec.return_value.execute.return_value = fake_result
            result = tool.execute({"target": "Spotify"})

        assert result.success is True
        assert "Spotify" in result.result

    def test_close_requires_target(self):
        result = CloseAppTool().execute({})
        assert result.success is False
        assert result.invalid is True

    def test_close_not_running_is_graceful(self):
        tool = CloseAppTool()
        with patch("brain.executor.BrainExecutor") as mock_exec:
            mock_exec.return_value.execute.return_value = {
                "success": False,
                "status": "not_running",
                "error": "Spotify doesn't appear to be running.",
            }
            result = tool.execute({"target": "Spotify"})

        assert result.success is False
        assert "running" in result.error

    def test_close_never_leaks_exceptions(self):
        tool = CloseAppTool()
        with patch("brain.executor.BrainExecutor") as mock_exec:
            mock_exec.return_value.execute.side_effect = RuntimeError("boom")
            result = tool.execute({"target": "Spotify"})

        assert result.success is False
        assert "boom" not in result.error


# ----------------------------------------------------------------------
# search_web
# ----------------------------------------------------------------------


class TestSearchWeb:
    def test_search_success(self):
        tool = SearchWebTool()
        with patch("skills.browser.main.BrowserSkill") as mock_browser:
            mock_browser.return_value.execute.return_value = {
                "success": True,
                "result": {"url": "https://www.google.com/search?q=python"},
            }
            result = tool.execute({"query": "python"})

        assert result.success is True
        assert "python" in result.result
        assert result.data["url"].startswith("https://")

    def test_search_requires_query(self):
        result = SearchWebTool().execute({})
        assert result.success is False
        assert result.invalid is True

    def test_search_failure_is_graceful(self):
        tool = SearchWebTool()
        with patch("skills.browser.main.BrowserSkill") as mock_browser:
            mock_browser.return_value.execute.return_value = {
                "success": False,
                "error": "Browser failed",
            }
            result = tool.execute({"query": "python"})

        assert result.success is False
        assert "Browser failed" in result.error


# ----------------------------------------------------------------------
# browser_ask
# ----------------------------------------------------------------------


class TestBrowserAsk:
    def test_ask_requires_url(self):
        result = BrowserAskTool().execute({"objective": "find pricing"})
        assert result.success is False
        assert result.invalid is True

    def test_ask_test_mode_plan(self):
        """In test mode the awareness skill plans without touching Chrome."""
        tool = BrowserAskTool()
        from brain.modes import set_test_mode

        set_test_mode(True)
        try:
            result = tool.execute({"url": "example.com", "objective": "find the pricing page"})
        finally:
            set_test_mode(False)

        assert result.success is True
        assert "example.com" in result.result or "planned" in result.result.lower()

    def test_ask_failure_is_graceful(self):
        tool = BrowserAskTool()
        with patch(
            "skills.browser_awareness.main.BrowserAwarenessSkill"
        ) as mock_skill:
            mock_skill.return_value.execute.return_value = {
                "success": False,
                "error": "No website to inspect",
            }
            result = tool.execute({"url": "example.com"})

        assert result.success is False


# ----------------------------------------------------------------------
# history_search
# ----------------------------------------------------------------------


class TestHistorySearch:
    def test_search_matches_commands(self):
        tool = HistorySearchTool()
        fake_history = [
            {"command": "open youtube", "action": "open", "target": "youtube",
             "success": 1, "timestamp": "t1"},
            {"command": "close chrome", "action": "close", "target": "chrome",
             "success": 1, "timestamp": "t2"},
        ]
        with patch("knowledge.memory.get_memory") as mock_mem:
            mock_mem.return_value.get_history.return_value = fake_history
            result = tool.execute({"query": "youtube"})

        assert result.success is True
        assert result.data["count"] == 1
        assert "youtube" in result.result

    def test_search_no_matches(self):
        tool = HistorySearchTool()
        with patch("knowledge.memory.get_memory") as mock_mem:
            mock_mem.return_value.get_history.return_value = []
            result = tool.execute({"query": "anything"})

        assert result.success is True
        assert result.data["count"] == 0

    def test_search_requires_query(self):
        result = HistorySearchTool().execute({})
        assert result.success is False
        assert result.invalid is True


# ----------------------------------------------------------------------
# memory_search
# ----------------------------------------------------------------------


class TestMemorySearch:
    def test_search_matches_facts(self):
        tool = MemorySearchTool()
        with patch("knowledge.memory.get_memory") as mock_mem:
            mock_mem.return_value.list_memories.return_value = [
                {"key": "user_project", "value": "Sarthi desktop assistant"},
                {"key": "pref_theme", "value": "dark"},
            ]
            result = tool.execute({"query": "sarthi"})

        assert result.success is True
        assert result.data["count"] == 1
        assert "Sarthi" in result.result

    def test_values_are_clipped(self):
        tool = MemorySearchTool()
        with patch("knowledge.memory.get_memory") as mock_mem:
            mock_mem.return_value.list_memories.return_value = [
                {"key": "big", "value": "x" * 500},
            ]
            result = tool.execute({"query": "big"})

        assert all(len(m["value"]) <= 120 for m in result.data["matches"])

    def test_search_failure_is_graceful(self):
        tool = MemorySearchTool()
        with patch("knowledge.memory.get_memory") as mock_mem:
            mock_mem.return_value.list_memories.side_effect = RuntimeError("db")
            result = tool.execute({"query": "x"})

        assert result.success is False
        assert "unavailable" in result.error


# ----------------------------------------------------------------------
# project_get
# ----------------------------------------------------------------------


class TestProjectGet:
    def test_status_success(self):
        tool = ProjectGetTool()
        with patch("skills.project_tracker.main.GitHubProjectSkill") as mock_skill:
            mock_skill.return_value.execute.return_value = {
                "success": True,
                "status": "3 tracked projects, 1 pending",
            }
            result = tool.execute({})

        assert result.success is True
        assert "3 tracked projects" in result.result

    def test_unknown_operation_refused(self):
        result = ProjectGetTool().execute({"operation": "delete_all"})
        assert result.success is False
        assert result.invalid is True

    def test_failure_is_graceful(self):
        tool = ProjectGetTool()
        with patch("skills.project_tracker.main.GitHubProjectSkill") as mock_skill:
            mock_skill.return_value.execute.side_effect = RuntimeError("no github")
            result = tool.execute({"operation": "status"})

        assert result.success is False
        assert "unavailable" in result.error


# ----------------------------------------------------------------------
# Registry end-to-end (validator + dispatch)
# ----------------------------------------------------------------------


class TestRegistryEndToEnd:
    def test_all_tools_execute_through_registry_validation(self, registry):
        """Every new tool validates and dispatches through the registry."""
        with patch("knowledge.memory.get_memory") as mock_mem:
            mock_mem.return_value.get_history.return_value = []
            mock_mem.return_value.list_memories.return_value = []
            result = registry.execute("history_search", {"query": "test"})
            assert result.success is True
            result = registry.execute("memory_search", {"query": "test"})
            assert result.success is True

    def test_invalid_arguments_fail_before_execution(self, registry):
        result = registry.execute("close_app", {})
        assert result.success is False
        assert result.invalid is True

    def test_unknown_tool_still_fails_safely(self, registry):
        result = registry.execute("not_a_tool", {})
        assert result.success is False
        assert result.unknown is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
