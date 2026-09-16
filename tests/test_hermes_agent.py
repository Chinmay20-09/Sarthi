"""Tests for the Phase 3d bounded Hermes agent loop.

Deterministic: the model boundary, tool registry, fast path, and retriever
are injected fakes — no Ollama, no real tools, no real retrieval.
"""

import pytest
from hermes.agent import HermesAgent
from hermes.models import Task
from hermes.providers.base import ProviderResponse
from hermes.retriever import Retriever
from hermes.tools.base import BaseTool, ToolResult

TOOL_CALL = '{"tool_call": {"tool": "spy", "arguments": {"target": "Chrome"}}}'


class FakeModel:
    """Pre-queued responses; records the tasks it was given."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.tasks = []

    def __call__(self, task: Task) -> ProviderResponse:
        self.tasks.append(task)
        text = self.responses.pop(0) if self.responses else "All done."
        return ProviderResponse(success=True, provider="Fake", model="fake-8b", text=text)


class SpyTool(BaseTool):
    name = "spy"
    description = "spy tool"
    parameters = {
        "type": "object",
        "properties": {"target": {"type": "string"}},
        "required": ["target"],
    }

    def __init__(self, result=None):
        self.calls = []
        self.result = result or ToolResult(success=True, tool="spy", result="did the thing")

    def execute(self, arguments):
        self.calls.append(arguments)
        return self.result


def _registry(tool=None):
    from hermes.tool_registry import ToolRegistry

    registry = ToolRegistry()
    if tool is not None:
        registry.register(tool)
    return registry


def _no_fast_path(query):
    return None


class _EmptyRetriever(Retriever):
    """A retriever that reports empty sources without touching stores."""

    def retrieve(self, query, session_id=None):
        from hermes.retriever import Context

        return Context()


# ----------------------------------------------------------------------
# Fast path gating
# ----------------------------------------------------------------------


class TestFastPathGating:
    def test_deterministic_success_short_circuits(self):
        calls = []

        def fast_path(query):
            calls.append(query)
            return {"success": True, "status": "executed", "text": "Opened Chrome."}

        agent = HermesAgent(generate=FakeModel([]), fast_path=fast_path)
        result = agent.run("open chrome")

        assert result["success"] is True
        assert result["text"] == "Opened Chrome."
        assert result["reason"] == "deterministic_pipeline"
        assert result["iterations"] == 0
        assert calls == ["open chrome"]  # model never called

    def test_nlp_fallback_falls_through_to_agent(self):
        model = FakeModel(["Here is your answer."])

        def fast_path(query):
            # The NLP fallback marks source="nlp" — Hermes owns it.
            return {
                "success": True,
                "status": "executed",
                "text": "A conversational answer",
                "result": {"source": "nlp", "message": "A conversational answer"},
            }

        agent = HermesAgent(generate=model, fast_path=fast_path)
        result = agent.run("what is the capital of france")

        assert result["reason"] == "final_answer"
        assert len(model.tasks) == 1  # the agent answered, not the fallback

    def test_skill_refusal_falls_through(self):
        model = FakeModel(["Trying Hermes instead."])
        agent = HermesAgent(
            generate=model,
            fast_path=lambda q: {"success": False, "status": "error", "error": "nope"},
        )
        result = agent.run("do the complex thing")

        assert result["success"] is True
        assert result["text"] == "Trying Hermes instead."

    def test_fast_path_exception_does_not_kill_agent(self):
        model = FakeModel(["Recovered answer."])
        agent = HermesAgent(
            generate=model,
            fast_path=lambda q: (_ for _ in ()).throw(RuntimeError("boom")),
        )
        result = agent.run("anything")
        assert result["success"] is True
        assert result["text"] == "Recovered answer."


# ----------------------------------------------------------------------
# The bounded loop
# ----------------------------------------------------------------------


class TestBoundedLoop:
    def test_single_tool_call_then_answer(self):
        model = FakeModel([TOOL_CALL, "All finished with your request."])
        spy = SpyTool()
        agent = HermesAgent(generate=model, tool_registry=_registry(spy), fast_path=_no_fast_path)
        result = agent.run("do something complex")

        assert result["success"] is True
        assert result["text"] == "All finished with your request."
        assert result["tool_used"] == "spy"
        assert result["iterations"] == 1
        assert spy.calls == [{"target": "Chrome"}]

    def test_iteration_cap_stops_loop(self):
        # Model always demands another tool call.
        model = FakeModel([TOOL_CALL] * 10)
        spy = SpyTool()
        agent = HermesAgent(
            generate=model,
            tool_registry=_registry(spy),
            fast_path=_no_fast_path,
            max_iterations=3,
        )
        result = agent.run("loop forever")

        assert result["reason"] == "iteration_cap"
        assert result["iterations"] <= 3
        assert len(spy.calls) <= 3

    def test_timeout_stops_loop(self):
        import time as _time

        def slow_generate(task):
            _time.sleep(0.05)  # 50ms per model call
            return ProviderResponse(success=True, provider="Fake", model="fake-8b", text=TOOL_CALL)

        spy = SpyTool()
        agent = HermesAgent(
            generate=slow_generate,
            tool_registry=_registry(spy),
            fast_path=_no_fast_path,
            timeout_seconds=0.001,  # 1ms budget — expires during the first call
            max_iterations=10,
        )
        result = agent.run("take too long")

        assert result["timed_out"] is True
        assert result["reason"] == "timeout"
        assert spy.calls == []  # never executed

    def test_model_failure_is_graceful(self):
        def failing_generate(task):
            return ProviderResponse(
                success=False, provider="Fake", model="fake-8b", text="", error="down"
            )

        agent = HermesAgent(generate=failing_generate, fast_path=_no_fast_path)
        result = agent.run("anything")

        assert result["success"] is False
        assert result["reason"] == "model_error"
        assert "down" in result["text"] or result["error"] == "down"

    def test_generate_exception_is_graceful(self):
        def raising_generate(task):
            raise RuntimeError("connection refused")

        agent = HermesAgent(generate=raising_generate, fast_path=_no_fast_path)
        result = agent.run("anything")

        assert result["success"] is False
        assert result["reason"] == "model_error"

    def test_empty_query(self):
        agent = HermesAgent(generate=FakeModel([]), fast_path=_no_fast_path)
        result = agent.run("   ")
        assert result["success"] is False
        assert result["reason"] == "empty_input"


# ----------------------------------------------------------------------
# Validation gate integration (Phase 3c)
# ----------------------------------------------------------------------


class TestValidationGate:
    def test_unknown_tool_is_refused_and_reported(self):
        model = FakeModel(
            [
                '{"tool_call": {"tool": "not_registered", "arguments": {}}}',
                "I could not do that, sorry.",
            ]
        )
        spy = SpyTool()
        agent = HermesAgent(generate=model, tool_registry=_registry(spy), fast_path=_no_fast_path)
        result = agent.run("delete everything")

        assert result["success"] is True
        assert result["tool_used"] is None  # never executed
        assert spy.calls == []
        validation_steps = [t for t in result["trace"] if t.get("step") == "validation"]
        assert validation_steps and validation_steps[0]["valid"] is False

    def test_injection_arguments_never_reach_tools(self):
        model = FakeModel(
            [
                '{"tool_call": {"tool": "spy", "arguments": {"target": "DROP TABLE users; --"}}}',
                "That did not work.",
            ]
        )
        spy = SpyTool()
        agent = HermesAgent(generate=model, tool_registry=_registry(spy), fast_path=_no_fast_path)
        result = agent.run("clean the database")

        assert spy.calls == []
        validation_steps = [t for t in result["trace"] if t.get("step") == "validation"]
        assert validation_steps and validation_steps[0]["valid"] is False

    def test_validated_call_executes(self):
        model = FakeModel([TOOL_CALL, "Done."])
        spy = SpyTool()
        agent = HermesAgent(generate=model, tool_registry=_registry(spy), fast_path=_no_fast_path)
        agent.run("open chrome please")
        assert len(spy.calls) == 1


# ----------------------------------------------------------------------
# Retrieval integration
# ----------------------------------------------------------------------


class TestRetrieval:
    def test_retrieved_context_reaches_the_model(self):
        class _ContextRetriever(Retriever):
            """Returns a small non-empty context block."""

            def retrieve(self, query, session_id=None):
                from hermes.retriever import Context

                return Context(text="Remembered facts (/remember):\n- user_project: Sarthi")

        model = FakeModel(["Answer with context."])
        agent = HermesAgent(
            generate=model,
            tool_registry=_registry(),
            fast_path=_no_fast_path,
            retriever=_ContextRetriever(),
        )
        agent.run("complex question")

        instructions = model.tasks[0].instructions or ""
        assert "Retrieved Sarthi context" in instructions
        assert "user_project: Sarthi" in instructions

    def test_empty_context_omits_block(self):
        model = FakeModel(["Answer."])
        agent = HermesAgent(
            generate=model,
            tool_registry=_registry(),
            fast_path=_no_fast_path,
            retriever=_EmptyRetriever(),
        )
        agent.run("complex question")

        instructions = model.tasks[0].instructions or ""
        assert "Retrieved Sarthi context" not in instructions

    def test_retrieval_failure_does_not_kill_task(self):
        class BrokenRetriever:
            def retrieve(self, query, session_id=None):
                raise RuntimeError("db down")

        model = FakeModel(["Still answering."])
        agent = HermesAgent(
            generate=model,
            tool_registry=_registry(),
            fast_path=_no_fast_path,
            retriever=BrokenRetriever(),
        )
        result = agent.run("complex question")
        assert result["success"] is True


# ----------------------------------------------------------------------
# History + persistence
# ----------------------------------------------------------------------


class TestHistoryAndPersistence:
    def test_session_history_attached(self, tmp_path, monkeypatch):
        from hermes.sandbox import TaskSandbox

        model = FakeModel(["Final."])
        agent = HermesAgent(
            generate=model,
            tool_registry=_registry(),
            fast_path=_no_fast_path,
            retriever=_EmptyRetriever(),
            sandbox=TaskSandbox(tmp_path / "sb"),
        )

        # No real conversation store needed — _session_history tolerates
        # absence gracefully.
        result = agent.run("complex question", session_id="sess1")
        assert result["success"] is True

    def test_result_shape_is_stable(self):
        model = FakeModel(["Answer."])
        agent = HermesAgent(generate=model, tool_registry=_registry(), fast_path=_no_fast_path)
        result = agent.run("question")

        expected_keys = {
            "success",
            "text",
            "tool_used",
            "iterations",
            "duration_ms",
            "timed_out",
            "route",
            "reason",
            "provider",
            "model",
            "trace",
            "error",
        }
        assert expected_keys <= set(result)
        assert result["route"] == "hermes"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
