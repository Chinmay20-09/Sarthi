"""
Phase 2.5 — Sarthi Tool Bridge tests.

Deterministic: no real Chrome installation or running Ollama server is
required. The LLM provider and the underlying Sarthi skills are mocked so
the tool loop, registry, and argument validation are exercised directly.
"""

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from brain.intent import Intent
from hermes.models import Task
from hermes.orchestrator import HermesOrchestrator
from hermes.providers.base import AIProvider, ProviderResponse
from hermes.providers.manager import ProviderManager
from hermes.tool_planner import MAX_TOOL_CALLS_PER_TASK, ToolPlanner, parse_tool_call
from hermes.tool_registry import ToolRegistry
from hermes.tools import GitHubTool, OpenAppTool, OpenWebsiteTool
from hermes.tools.base import BaseTool, ToolResult

TOOL_CALL_JSON = '{"tool_call": {"tool": "open_app", "arguments": {"target": "Chrome"}}}'


# ----------------------------------------------------------------------
# Test doubles
# ----------------------------------------------------------------------


class FakeProvider(AIProvider):
    """Deterministic LLM stand-in: returns pre-queued responses in order."""

    name = "Fake"

    def __init__(self, responses: list[str]):
        self.responses = list(responses)
        self.tasks: list[Task] = []

    def generate(self, task: Task) -> ProviderResponse:
        self.tasks.append(task)
        text = self.responses.pop(0) if self.responses else "Hello!"
        return ProviderResponse(success=True, provider=self.name, model="fake-model", text=text)


class SpyTool(BaseTool):
    """Registered tool that records every call and returns a canned result."""

    description = "Spy tool for tests"
    parameters = {
        "type": "object",
        "properties": {"target": {"type": "string"}},
        "required": ["target"],
    }

    def __init__(self, name: str = "spy", result: ToolResult | None = None):
        self.name = name
        self.calls: list[dict] = []
        self.result = result or ToolResult(success=True, tool=name, result="done")

    def execute(self, arguments: dict) -> ToolResult:
        self.calls.append(arguments)
        return self.result


def make_planner(responses: list[str], name: str = "spy", result: ToolResult | None = None):
    """Build a ToolPlanner with a FakeProvider and a registered SpyTool."""
    fake = FakeProvider(responses)
    registry = ToolRegistry()
    spy = SpyTool(name=name, result=result)
    registry.register(spy)
    return ToolPlanner(registry, fake.generate), fake, spy


# ----------------------------------------------------------------------
# 1. Tool registration
# ----------------------------------------------------------------------


def test_tool_registration():
    """open_app, open_website and github can be registered and discovered."""
    registry = ToolRegistry()
    registry.register(OpenAppTool())
    registry.register(OpenWebsiteTool())
    registry.register(GitHubTool())

    names = {tool["name"] for tool in registry.list_tools()}
    assert "open_app" in names
    assert "open_website" in names
    assert "github" in names
    assert len(registry.list_tools()) == 3


# ----------------------------------------------------------------------
# 2. Tool lookup
# ----------------------------------------------------------------------


def test_tool_lookup():
    """registry.get('open_app') returns the correct tool."""
    registry = ToolRegistry()
    registry.register(OpenAppTool())

    tool = registry.get("open_app")
    assert tool is not None
    assert tool.name == "open_app"
    assert "target" in tool.parameters["required"]
    assert registry.get("missing") is None


# ----------------------------------------------------------------------
# 3. Unknown tool
# ----------------------------------------------------------------------


def test_unknown_tool_fails_safely():
    """An unregistered tool name produces a structured, graceful failure."""
    registry = ToolRegistry()
    result = registry.execute("no_such_tool", {"target": "Chrome"})

    assert result.success is False
    assert result.unknown is True
    assert result.error == ""


# ----------------------------------------------------------------------
# 4. Tool argument validation
# ----------------------------------------------------------------------


def test_missing_argument_fails_safely():
    """Missing required arguments are rejected before execution."""
    registry = ToolRegistry()
    registry.register(OpenAppTool())

    result = registry.execute("open_app", {})
    assert result.success is False
    assert result.invalid is True
    assert "target" in result.error


def test_wrong_argument_type_fails_safely():
    """Non-string arguments are rejected before execution."""
    registry = ToolRegistry()
    registry.register(OpenAppTool())

    result = registry.execute("open_app", {"target": 123})
    assert result.success is False
    assert result.invalid is True
    assert "string" in result.error


# ----------------------------------------------------------------------
# 5. Tool dispatch delegates to the existing Sarthi execution path
# ----------------------------------------------------------------------


def test_open_app_delegates_to_existing_launcher(monkeypatch):
    """open_app reuses AppLauncherSkill (the existing Sarthi executor)."""
    registry = ToolRegistry()
    registry.register(OpenAppTool())

    captured = {}

    class FakeLauncher:
        def execute(self, intent: Intent) -> dict:
            captured["action"] = intent.action
            captured["target"] = intent.target
            return {
                "success": True,
                "status": "executed",
                "result": {"application": "Chrome", "path": "C:/apps/chrome.exe"},
            }

    monkeypatch.setattr("hermes.tools.open_app.AppLauncherSkill", lambda: FakeLauncher())

    result = registry.execute("open_app", {"target": "Chrome"})

    assert result.success is True
    assert result.tool == "open_app"
    assert "Chrome" in result.result
    assert captured["action"] == "open"
    assert captured["target"] == "Chrome"


def test_open_app_delegation_failure_is_graceful(monkeypatch):
    """A failed underlying skill produces a safe error — no exception leaks."""
    registry = ToolRegistry()
    registry.register(OpenAppTool())

    class FailingLauncher:
        def execute(self, intent: Intent) -> dict:
            return {
                "success": False,
                "status": "not_found",
                "error": "Application 'xyz' could not be found.",
            }

    monkeypatch.setattr("hermes.tools.open_app.AppLauncherSkill", lambda: FailingLauncher())

    result = registry.execute("open_app", {"target": "xyz"})

    assert result.success is False
    assert "could not be found" in result.error


# ----------------------------------------------------------------------
# 6. Hermes no-tool request
# ----------------------------------------------------------------------


def test_conversation_does_not_use_tools():
    """'Hello Hermes' is answered directly — no tool is executed."""
    planner, fake, spy = make_planner(["Hello! I'm Hermes."])

    response = planner.run(Task(prompt="Hello Hermes"))

    assert response.success is True
    assert response.text == "Hello! I'm Hermes."
    assert response.tool_used is None
    assert spy.calls == []
    assert len(fake.tasks) == 1  # only the decision call


# ----------------------------------------------------------------------
# 7. Hermes tool request
# ----------------------------------------------------------------------


def test_hermes_requests_tool_for_actionable_request():
    """'Open Chrome' produces an open_app tool request that is executed."""
    planner, fake, spy = make_planner([TOOL_CALL_JSON, "Chrome is open."], name="open_app")

    response = planner.run(Task(prompt="Open Chrome"))

    assert response.success is True
    assert response.text == "Chrome is open."
    assert response.tool_used == "open_app"
    assert spy.calls == [{"target": "Chrome"}]
    assert len(fake.tasks) == 2  # decision call + follow-up call


def test_tool_call_json_is_machine_readable():
    """The structured tool call format parses as expected."""
    parsed = parse_tool_call(TOOL_CALL_JSON)
    assert parsed == {"tool": "open_app", "arguments": {"target": "Chrome"}}

    # Plain conversation is not a tool call.
    assert parse_tool_call("Hello there!") is None
    # Code-fence-wrapped JSON is still parsed.
    fenced = f"```json\n{TOOL_CALL_JSON}\n```"
    assert parse_tool_call(fenced) == {"tool": "open_app", "arguments": {"target": "Chrome"}}


def test_tool_call_with_doubled_braces_is_parsed():
    """Models that double curly braces ({{ }}) still produce a tool call."""
    # Regression: hermes3:8b mimicked a double-brace example and emitted this.
    broken = (
        '{{"tool_call": {{"tool": "open_website", "arguments": '
        + '{{"url": "https://www.youtube.com/results?search_query=india%27s+got+latent"}}}}}}'
    )
    parsed = parse_tool_call(broken)
    assert parsed == {
        "tool": "open_website",
        "arguments": {"url": "https://www.youtube.com/results?search_query=india%27s+got+latent"},
    }


def test_decision_prompt_uses_single_braces():
    """The prompt example must not show doubled braces (the root cause)."""
    from hermes.tool_planner import build_decision_instructions

    registry = ToolRegistry()
    registry.register(OpenWebsiteTool())
    instructions = build_decision_instructions(
        'open youtube and search "india\'s got latent"', registry.list_tools()
    )
    # No doubled opening braces anywhere in the instructions.
    assert "{{" not in instructions


# ----------------------------------------------------------------------
# 8. Tool loop: tool call -> execution -> result -> final response
# ----------------------------------------------------------------------


def test_tool_loop_result_flows_back_to_hermes():
    """The tool result is fed back to Hermes for the final response."""
    spy_result = ToolResult(success=True, tool="open_app", result="Chrome launched")
    planner, fake, spy = make_planner(
        [TOOL_CALL_JSON, "Chrome is open."], name="open_app", result=spy_result
    )

    response = planner.run(Task(prompt="Open Chrome"))

    assert response.success is True
    assert response.text == "Chrome is open."
    assert response.tool_used == "open_app"
    assert spy.calls == [{"target": "Chrome"}]

    # The follow-up prompt carries the actual tool result back to Hermes.
    followup = fake.tasks[1]
    assert "Chrome launched" in followup.instructions
    assert "open_app" in followup.instructions


# ----------------------------------------------------------------------
# 9. Tool failure
# ----------------------------------------------------------------------


def test_tool_failure_produces_graceful_response():
    """A failed tool leads to a graceful Hermes response, not an exception."""
    spy_result = ToolResult(
        success=False, tool="open_app", error="Application 'Chrome' could not be found."
    )
    planner, fake, spy = make_planner(
        [TOOL_CALL_JSON, "I couldn't find Chrome on this system."],
        name="open_app",
        result=spy_result,
    )

    response = planner.run(Task(prompt="Open Chrome"))

    assert response.success is True  # Hermes still replied gracefully
    assert response.tool_used == "open_app"
    assert "couldn't find Chrome" in response.text
    assert "could not be found" in fake.tasks[1].instructions


def test_hermes_unknown_tool_is_graceful():
    """Hermes requesting an unregistered tool yields a graceful answer."""
    planner, fake, spy = make_planner(
        ['{"tool_call": {"tool": "nope", "arguments": {}}}', "unused"], name="open_app"
    )

    response = planner.run(Task(prompt="Do something odd"))

    assert response.success is True
    assert response.text == "That capability is not available."
    assert response.tool_used == "nope"
    assert spy.calls == []
    assert len(fake.tasks) == 1  # no follow-up call needed


# ----------------------------------------------------------------------
# 10. Tool-call limit
# ----------------------------------------------------------------------


def test_tool_call_limit_prevents_infinite_loop():
    """A model that keeps requesting tools is stopped at the hard limit."""
    many_calls = [TOOL_CALL_JSON] * 20
    planner, fake, spy = make_planner(many_calls, name="open_app")

    response = planner.run(Task(prompt="Open Chrome"))

    assert response.success is True
    assert response.tool_used == "open_app"
    assert "too many steps" in response.text
    assert len(spy.calls) == MAX_TOOL_CALLS_PER_TASK
    assert len(fake.tasks) == 1 + MAX_TOOL_CALLS_PER_TASK


# ----------------------------------------------------------------------
# Orchestrator integration (fallback preserved, task fields preserved)
# ----------------------------------------------------------------------


def test_orchestrator_preserves_task_fields_and_keeps_fallback():
    """The orchestrator still preserves task fields and runs the planner."""
    manager = ProviderManager()
    fake = FakeProvider(["Hello there!"])
    manager.initialize(fake)

    orchestrator = HermesOrchestrator(manager, tool_registry=ToolRegistry())
    task = Task(prompt="Hello Hermes", id="task_abc", task_type="chat", context={"k": "v"})

    response = orchestrator.process(task)

    assert response.success is True
    assert response.text == "Hello there!"
    received = fake.tasks[0]
    assert received.id == "task_abc"
    assert received.prompt == "Hello Hermes"
    assert received.task_type == "chat"
    assert received.context == {"k": "v"}
    assert "Available tools" in received.instructions


# ----------------------------------------------------------------------
# API surface: /hermes/chat reports tool_used
# ----------------------------------------------------------------------


def test_hermes_api_reports_tool_used():
    """POST /hermes/chat includes tool_used when a tool was executed."""
    from api import app

    client = TestClient(app)
    with patch("hermes.routes._orchestrator", None):
        with patch("hermes.routes._get_orchestrator") as mock_get_orch:
            mock_orch = MagicMock()
            mock_response = ProviderResponse(
                success=True,
                provider="Ollama",
                model="hermes3:8b",
                text="Chrome is open.",
                tool_used="open_app",
            )
            mock_orch.process.return_value = mock_response
            mock_get_orch.return_value = mock_orch

            response = client.post("/hermes/chat", json={"message": "Open Chrome"})

            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert data["response"] == "Chrome is open."
            assert data["tool_used"] == "open_app"


def test_hermes_tools_endpoint_lists_registered_tools():
    """GET /hermes/tools lists the registered tools for the UI."""
    from api import app

    client = TestClient(app)
    response = client.get("/hermes/tools")

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["error"] is None

    names = [tool["name"] for tool in data["tools"]]
    assert "open_app" in names
    assert "open_website" in names
    assert "github" in names
    for tool in data["tools"]:
        assert tool["name"]
        assert tool["description"]
        assert isinstance(tool["parameters"], dict)
        assert "properties" in tool["parameters"]


# ----------------------------------------------------------------------
# 11. GitHub tool
# ----------------------------------------------------------------------


def _fake_github_skill(client):
    """A GitHubProjectSkill stand-in that resolves a username and exposes a client."""

    class FakeSkill:
        def __init__(self):
            self.github = client

        def _ensure_github(self):
            return "octocat"

    return FakeSkill()


class FakeGitHubClient:
    """Records calls and returns canned GitHub data."""

    def __init__(self, **results):
        self.results = results
        self.calls = []

    def _record(self, name, *args):
        self.calls.append((name, args))
        return self.results.get(name)

    def get_repositories(self):
        return self._record("get_repositories")

    def get_repository_summary(self, repository):
        return self._record("get_repository_summary", repository)

    def get_issues(self, repository):
        return self._record("get_issues", repository)

    def get_pull_requests(self, repository):
        return self._record("get_pull_requests", repository)

    def get_latest_commit(self, repository):
        return self._record("get_latest_commit", repository)

    def search_repositories(self, query, sort="stars", order="desc"):
        return self._record("search_repositories", query)

    def get_branches(self, repository):
        return self._record("get_branches", repository)

    def get_releases(self, repository):
        return self._record("get_releases", repository)


def test_github_unknown_operation_is_invalid():
    """An unsupported operation is rejected before any GitHub call."""
    registry = ToolRegistry()
    registry.register(GitHubTool())

    result = registry.execute("github", {"operation": "delete_all"})

    assert result.success is False
    assert result.invalid is True
    assert "Unknown GitHub operation" in result.error


def test_github_repository_required_for_repo_operations():
    """repo-scoped operations require a repository argument."""
    registry = ToolRegistry()
    registry.register(GitHubTool())

    result = registry.execute("github", {"operation": "issues"})

    assert result.success is False
    assert result.invalid is True
    assert "repository name is required" in result.error


def test_github_search_requires_query():
    """The search operation requires a query argument."""
    registry = ToolRegistry()
    registry.register(GitHubTool())

    result = registry.execute("github", {"operation": "search"})

    assert result.success is False
    assert result.invalid is True
    assert "search query is required" in result.error


def test_github_not_configured_is_graceful(monkeypatch):
    """No configured username produces a helpful setup message."""
    registry = ToolRegistry()
    registry.register(GitHubTool())

    class UnconfiguredSkill:
        github = None

        def _ensure_github(self):
            return ""

    monkeypatch.setattr(
        "hermes.tools.github.GitHubTool._get_skill", lambda self: UnconfiguredSkill()
    )

    result = registry.execute("github", {"operation": "repositories"})

    assert result.success is False
    assert "not configured" in result.error


def test_github_repositories_delegates_to_existing_skill(monkeypatch):
    """The github tool reuses GitHubProjectSkill's client, not a new integration."""
    client = FakeGitHubClient(
        get_repositories=[
            {
                "name": "sarthi",
                "description": "AI assistant",
                "language": "Python",
                "private": False,
                "html_url": "https://github.com/octocat/sarthi",
            },
            {
                "name": "notes",
                "description": None,
                "language": None,
                "private": True,
                "html_url": "https://github.com/octocat/notes",
            },
        ]
    )
    monkeypatch.setattr(
        "hermes.tools.github.GitHubTool._get_skill", lambda self: _fake_github_skill(client)
    )
    registry = ToolRegistry()
    registry.register(GitHubTool())

    result = registry.execute("github", {"operation": "repositories"})

    assert result.success is True
    assert result.tool == "github"
    assert "2 repositories" in result.result
    assert "sarthi" in result.result
    assert "notes" in result.result
    assert client.calls == [("get_repositories", ())]
    assert len(result.data["repositories"]) == 2


def test_github_issues_passes_repository(monkeypatch):
    """Repo-scoped operations forward the repository name to the client."""
    client = FakeGitHubClient(
        get_issues=[
            {
                "number": 4,
                "title": "Fix the sidebar",
                "html_url": "https://github.com/octocat/sarthi/issues/4",
                "state": "open",
            },
        ]
    )
    monkeypatch.setattr(
        "hermes.tools.github.GitHubTool._get_skill", lambda self: _fake_github_skill(client)
    )
    registry = ToolRegistry()
    registry.register(GitHubTool())

    result = registry.execute("github", {"operation": "issues", "repository": "sarthi"})

    assert result.success is True
    assert "1 open issues" in result.result
    assert "#4 Fix the sidebar" in result.result
    assert client.calls == [("get_issues", ("sarthi",))]


def test_github_search_delegates_with_query(monkeypatch):
    """search forwards the query and reports star counts."""
    client = FakeGitHubClient(
        search_repositories=[
            {
                "full_name": "torvalds/linux",
                "stars": 190000,
                "html_url": "https://github.com/torvalds/linux",
                "private": False,
            },
            {
                "full_name": "microsoft/vscode",
                "stars": 160000,
                "html_url": "https://github.com/microsoft/vscode",
                "private": False,
            },
        ]
    )
    monkeypatch.setattr(
        "hermes.tools.github.GitHubTool._get_skill", lambda self: _fake_github_skill(client)
    )
    registry = ToolRegistry()
    registry.register(GitHubTool())

    result = registry.execute("github", {"operation": "search", "query": "linux kernel"})

    assert result.success is True
    assert "2 repositories found" in result.result
    assert "torvalds/linux (190000 stars)" in result.result
    assert "microsoft/vscode" in result.result
    assert client.calls == [("search_repositories", ("linux kernel",))]


def test_github_branches_delegates(monkeypatch):
    """branches forwards the repository and lists branch names."""
    client = FakeGitHubClient(
        get_branches=[{"name": "main"}, {"name": "dev"}, {"name": "feature/x"}]
    )
    monkeypatch.setattr(
        "hermes.tools.github.GitHubTool._get_skill", lambda self: _fake_github_skill(client)
    )
    registry = ToolRegistry()
    registry.register(GitHubTool())

    result = registry.execute("github", {"operation": "branches", "repository": "sarthi"})

    assert result.success is True
    assert "3 branches in sarthi" in result.result
    assert "main, dev, feature/x" in result.result
    assert client.calls == [("get_branches", ("sarthi",))]


def test_github_releases_delegates(monkeypatch):
    """releases forwards the repository and lists tags with dates."""
    client = FakeGitHubClient(
        get_releases=[
            {
                "tag_name": "v2.0.0",
                "published_at": "2026-01-15T00:00:00Z",
                "html_url": "https://github.com/octocat/sarthi/releases/tag/v2.0.0",
            },
            {
                "tag_name": "v1.5.0",
                "published_at": "2025-11-02T00:00:00Z",
                "html_url": "https://github.com/octocat/sarthi/releases/tag/v1.5.0",
            },
        ]
    )
    monkeypatch.setattr(
        "hermes.tools.github.GitHubTool._get_skill", lambda self: _fake_github_skill(client)
    )
    registry = ToolRegistry()
    registry.register(GitHubTool())

    result = registry.execute("github", {"operation": "releases", "repository": "sarthi"})

    assert result.success is True
    assert "2 releases in sarthi" in result.result
    assert "v2.0.0" in result.result
    assert "v1.5.0" in result.result
    assert client.calls == [("get_releases", ("sarthi",))]


def test_github_404_maps_to_friendly_error(monkeypatch):
    """A missing repository surfaces as a safe, helpful message."""

    class MissingRepoClient:
        def get_repository_summary(self, repository):
            raise _HttpError(404)

    monkeypatch.setattr(
        "hermes.tools.github.GitHubTool._get_skill",
        lambda self: _fake_github_skill(MissingRepoClient()),
    )
    registry = ToolRegistry()
    registry.register(GitHubTool())

    result = registry.execute("github", {"operation": "summary", "repository": "nope"})

    assert result.success is False
    assert "was not found" in result.error


class _HttpError(Exception):
    """Minimal requests.HTTPError stand-in with a response.status_code."""

    def __init__(self, status_code):
        self.response = type("Resp", (), {"status_code": status_code})()
