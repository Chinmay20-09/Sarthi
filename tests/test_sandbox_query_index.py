"""Tests for the query-indexed TaskSandbox and orchestrator persistence.

Hermes is an orchestrator: every task it processes is saved to the sandbox
indexed by the user's query, with the full execution trace, so it can be
referenced later. These tests verify that contract deterministically.
"""

import json
from unittest.mock import patch

from fastapi.testclient import TestClient

from hermes.models import Task
from hermes.orchestrator import HermesOrchestrator
from hermes.providers.base import AIProvider, ProviderResponse
from hermes.providers.manager import ProviderManager
from hermes.sandbox import TaskSandbox, normalize_query
from hermes.tool_registry import ToolRegistry


def _response(success=True, provider="Ollama", text="Hello!", tool_used=None):
    return ProviderResponse(
        success=success,
        provider=provider,
        model="hermes3:8b",
        text=text,
        tool_used=tool_used,
    )


class FakeProvider(AIProvider):
    """Deterministic provider returning a canned response."""

    name = "Fake"

    def generate(self, task: Task) -> ProviderResponse:
        return _response(provider=self.name, text="Response to: " + task.prompt)


# ----------------------------------------------------------------------
# Query normalization
# ----------------------------------------------------------------------


def test_normalize_query_collapses_case_and_space():
    """Index keys are stable regardless of casing/whitespace."""
    assert normalize_query("  Show   My REPOS ") == "show my repos"
    assert normalize_query("show my repos") == normalize_query("SHOW MY REPOS")


# ----------------------------------------------------------------------
# Sandbox: query index + lookup
# ----------------------------------------------------------------------


def test_save_indexes_task_by_query(tmp_path):
    """Saving a task adds a record to index.json under the query key."""
    sandbox = TaskSandbox(tmp_path)
    task = Task(id="task_abc", prompt="Show my repos")

    sandbox.save(task, _response(tool_used="github"), 42.5)

    index = json.loads((tmp_path / "index.json").read_text(encoding="utf-8"))
    records = index["show my repos"]
    assert len(records) == 1
    assert records[0]["task_id"] == "task_abc"
    assert records[0]["tool_used"] == "github"
    assert records[0]["status"] == "success"
    assert records[0]["duration_ms"] == 42.5


def test_same_query_appends_multiple_records(tmp_path):
    """Repeated queries accumulate records under the same index key."""
    sandbox = TaskSandbox(tmp_path)
    sandbox.save(Task(id="task_1", prompt="show my repos"), _response(), 10.0)
    sandbox.save(Task(id="task_2", prompt="  SHOW MY REPOS "), _response(), 20.0)

    records = sandbox.lookup("show my repos")
    assert [r["task_id"] for r in records] == ["task_1", "task_2"]


def test_lookup_returns_empty_for_unknown_query(tmp_path):
    """Unknown queries yield an empty list, never an error."""
    sandbox = TaskSandbox(tmp_path)
    assert sandbox.lookup("nope") == []


def test_save_writes_artifacts_and_trace(tmp_path):
    """Task dir contains prompt, response, trace and metadata."""
    sandbox = TaskSandbox(tmp_path)
    task = Task(id="task_xyz", prompt="What branches does sarthi have?")
    trace = [
        {
            "step": "decision",
            "provider": "Fake",
            "success": True,
            "text": '{"tool_call": {"tool": "github", "arguments": {"operation": "branches", "repository": "sarthi"}}}',
        },
        {
            "step": "tool_call",
            "tool": "github",
            "arguments": {"operation": "branches", "repository": "sarthi"},
        },
        {
            "step": "tool_result",
            "tool": "github",
            "success": True,
            "result": "3 branches in sarthi: main, dev, feature/x",
        },
        {"step": "response", "provider": "Fake", "success": True, "text": "sarthi has 3 branches."},
    ]

    sandbox.save(task, _response(tool_used="github"), 123.0, trace=trace)

    task_dir = tmp_path / "tasks" / "task_xyz"
    assert (task_dir / "prompt.md").read_text(encoding="utf-8") == task.prompt
    assert (task_dir / "response.md").read_text(encoding="utf-8") == "Hello!"
    assert (task_dir / "trace.json").exists()
    assert json.loads((task_dir / "trace.json").read_text(encoding="utf-8")) == trace
    metadata = json.loads((task_dir / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["query"] == task.prompt
    assert metadata["tool_used"] == "github"


def test_save_without_trace_skips_trace_file(tmp_path):
    """trace.json is only written when a trace is provided."""
    sandbox = TaskSandbox(tmp_path)
    sandbox.save(Task(id="task_no_trace", prompt="hi"), _response(), 5.0)
    assert not (tmp_path / "tasks" / "task_no_trace" / "trace.json").exists()


# ----------------------------------------------------------------------
# Orchestrator: sandbox persistence + trace recording
# ----------------------------------------------------------------------


def _orchestrator_with_sandbox(tmp_path):
    manager = ProviderManager()
    manager.initialize(FakeProvider())
    sandbox = TaskSandbox(tmp_path)
    orchestrator = HermesOrchestrator(manager, tool_registry=ToolRegistry(), sandbox=sandbox)
    return orchestrator, sandbox


def test_orchestrator_saves_task_indexed_by_query(tmp_path):
    """process() persists the task to the sandbox under the query key."""
    orchestrator, sandbox = _orchestrator_with_sandbox(tmp_path)

    response = orchestrator.process(Task(prompt="Hello Hermes"))

    assert response.success is True
    records = sandbox.lookup("hello hermes")
    assert len(records) == 1
    assert records[0]["provider"] == "Fake"


def test_orchestrator_records_decision_trace(tmp_path):
    """The saved trace contains the decision step from the planner."""
    orchestrator, sandbox = _orchestrator_with_sandbox(tmp_path)

    orchestrator.process(Task(id="task_trace", prompt="Hello Hermes"))

    trace = json.loads(
        (tmp_path / "tasks" / "task_trace" / "trace.json").read_text(encoding="utf-8")
    )
    assert trace[0]["step"] == "decision"
    assert trace[0]["provider"] == "Fake"
    assert trace[0]["success"] is True


def test_orchestrator_without_sandbox_does_not_write(tmp_path):
    """No sandbox configured: no files written, behavior unchanged."""
    manager = ProviderManager()
    manager.initialize(FakeProvider())
    orchestrator = HermesOrchestrator(manager, tool_registry=ToolRegistry())

    response = orchestrator.process(Task(id="task_ns", prompt="hi"))

    assert response.success is True
    assert not (tmp_path / "tasks").exists()


# ----------------------------------------------------------------------
# API: sandbox viewer endpoints
# ----------------------------------------------------------------------


def _sandbox_with_tasks(tmp_path):
    sandbox = TaskSandbox(tmp_path)
    trace = [
        {"step": "decision", "provider": "Fake", "success": True, "text": "plain answer"},
        {"step": "response", "provider": "Fake", "success": True, "text": "Hello there."},
    ]
    sandbox.save(
        Task(id="task_older", prompt="hello hermes"),
        _response(text="Hello there."),
        15.0,
        trace=trace,
    )
    sandbox.save(Task(id="task_newer", prompt="Show my repos"), _response(tool_used="github"), 42.5)
    return sandbox


def test_sandbox_endpoint_lists_queries(tmp_path):
    """GET /hermes/sandbox groups records by query, newest group first."""
    from api import app

    client = TestClient(app)
    with patch("hermes.routes._get_sandbox", return_value=_sandbox_with_tasks(tmp_path)):
        response = client.get("/hermes/sandbox")

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["error"] is None
    # Most recent query first
    assert data["queries"][0]["query"] == "show my repos"
    assert data["queries"][1]["query"] == "hello hermes"
    # Records carry the full metadata
    record = data["queries"][0]["records"][0]
    assert record["task_id"] == "task_newer"
    assert record["tool_used"] == "github"
    assert record["status"] == "success"


def test_sandbox_endpoint_empty(tmp_path):
    """An empty sandbox returns success with no queries."""
    from api import app

    client = TestClient(app)
    with patch("hermes.routes._get_sandbox", return_value=TaskSandbox(tmp_path)):
        response = client.get("/hermes/sandbox")

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["queries"] == []


def test_sandbox_task_endpoint_returns_artifacts(tmp_path):
    """GET /hermes/sandbox/tasks/{id} returns prompt, response, trace, metadata."""
    from api import app

    client = TestClient(app)
    with patch("hermes.routes._get_sandbox", return_value=_sandbox_with_tasks(tmp_path)):
        response = client.get("/hermes/sandbox/tasks/task_older")

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["task_id"] == "task_older"
    assert data["prompt"] == "hello hermes"
    assert data["response"] == "Hello there."
    assert data["trace"] == [
        {"step": "decision", "provider": "Fake", "success": True, "text": "plain answer"},
        {"step": "response", "provider": "Fake", "success": True, "text": "Hello there."},
    ]
    assert data["metadata"]["task_id"] == "task_older"
    assert data["error"] is None


def test_sandbox_task_endpoint_missing(tmp_path):
    """A task that does not exist returns a graceful error."""
    from api import app

    client = TestClient(app)
    with patch("hermes.routes._get_sandbox", return_value=TaskSandbox(tmp_path)):
        response = client.get("/hermes/sandbox/tasks/task_missing")

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is False
    assert data["error"] == "Task not found."
