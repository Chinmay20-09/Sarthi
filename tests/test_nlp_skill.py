"""Tests for the Natural Language Processor skill.

The NLP skill is Sarthi's conversational fallback: it holds a plain
conversation (no tool fetching) and is tried last, after every real tool
or skill has had a chance at the intent.
"""

import json
from unittest.mock import patch

from brain.engine import BrainEngine
from brain.executor import BrainExecutor
from brain.intent import Intent
from hermes.models import Task
from hermes.orchestrator import HermesOrchestrator
from hermes.providers.base import AIProvider, ProviderResponse
from hermes.providers.manager import ProviderManager
from hermes.sandbox import TaskSandbox
from hermes.tool_registry import ToolRegistry
from skills.natural_language_processor.main import NaturalLanguageProcessorSkill


class FakeChatProvider(AIProvider):
    """Provider returning a canned conversational reply."""

    name = "Fake"

    def generate(self, task: Task) -> ProviderResponse:
        return ProviderResponse(
            success=True,
            provider=self.name,
            model="fake-model",
            text=f"Reply to: {task.prompt}",
        )


def make_orchestrator(sandbox=None):
    manager = ProviderManager()
    manager.initialize(FakeChatProvider())
    return HermesOrchestrator(manager, tool_registry=ToolRegistry(), sandbox=sandbox)


# ----------------------------------------------------------------------
# Skill behavior
# ----------------------------------------------------------------------


def test_skill_claims_conversational_intent(monkeypatch):
    """An 'unknown' (pure chat) intent is claimed and answered conversationally."""
    skill = NaturalLanguageProcessorSkill()

    with patch("hermes.service.chat") as mock_chat:
        mock_chat.return_value = ProviderResponse(
            success=True, provider="Fake", model="m", text="Hello there!"
        )
        result = skill.execute(Intent(action="unknown", target="hello", raw_text="hello"))

    assert result["success"] is True
    assert result["result"]["message"] == "Hello there!"
    assert result["result"]["provider"] == "Fake"
    # Marked as the NLP conversational fallback so the UI can badge it
    assert result["result"]["source"] == "nlp"
    mock_chat.assert_called_once_with("hello")


def test_skill_uses_raw_text_when_available(monkeypatch):
    """The original user message is passed to chat, not the parsed intent."""
    skill = NaturalLanguageProcessorSkill()

    with patch("hermes.service.chat") as mock_chat:
        mock_chat.return_value = ProviderResponse(
            success=True, provider="Fake", model="m", text="ok"
        )
        skill.execute(
            Intent(
                action="what",
                target="capital france",
                raw_text="What is the capital of France?",
            )
        )

    mock_chat.assert_called_once_with("What is the capital of France?")


def test_skill_leaves_imperative_commands_alone(monkeypatch):
    """Imperative actions are not claimed — their skills get first chance."""
    skill = NaturalLanguageProcessorSkill()

    result = skill.execute(Intent(action="open", target="chrome"))

    assert result["success"] is False
    assert result["status"] == "unknown"


def test_skill_reports_unreachable_model_gracefully(monkeypatch):
    """A failing chat call yields a handled error, not an exception."""
    skill = NaturalLanguageProcessorSkill()

    with patch("hermes.service.chat") as mock_chat:
        mock_chat.return_value = ProviderResponse(
            success=False, provider="Fake", model="m", text="", error="Connection timeout"
        )
        result = skill.execute(Intent(action="unknown", target="hi", raw_text="hi"))

    assert result["success"] is False
    assert result["handled"] is True
    assert "Connection timeout" in result["error"]


# ----------------------------------------------------------------------
# Orchestrator.chat — plain conversation, NO tool planning
# ----------------------------------------------------------------------


def test_orchestrator_chat_bypasses_tool_planner(tmp_path):
    """chat() replies directly — the tool registry is never consulted."""
    sandbox = TaskSandbox(tmp_path)
    orchestrator = make_orchestrator(sandbox=sandbox)

    response = orchestrator.chat(Task(id="chat_test", prompt="Hello Hermes"))

    assert response.success is True
    assert response.text == "Reply to: Hello Hermes"
    assert response.tool_used is None
    # Sandbox saved with the query index and a single chat trace step
    assert sandbox.lookup("hello hermes")
    trace = json.loads(
        (tmp_path / "tasks" / "chat_test" / "trace.json").read_text(encoding="utf-8")
    )
    assert trace[0]["step"] == "chat"
    assert trace[0]["provider"] == "Fake"


# ----------------------------------------------------------------------
# Registration: fallback skills are tried last
# ----------------------------------------------------------------------


def test_skill_is_registered_last_by_brain():
    """The executor tries the NLP skill after every other skill."""
    engine = BrainEngine(executor=BrainExecutor())
    names = [skill.name for skill in engine.executor._skills]
    assert "Natural Language Processor" in names
    assert names[-1] == "Natural Language Processor"


# ----------------------------------------------------------------------
# Executor: handled=True short-circuits so the fallback can't override
# ----------------------------------------------------------------------


class ClaimingSkill:
    """Skill that claims an intent it cannot fulfill (handled=True)."""

    name = "claimer"

    def execute(self, intent):
        return {
            "success": False,
            "status": "not_configured",
            "handled": True,
            "error": "Something is not configured.",
        }


class ChattySkill:
    """Skill that would answer anything conversationally."""

    name = "chatty"

    def execute(self, intent):
        return {"success": True, "status": "executed", "result": {"message": "chat"}}


def test_brain_pipeline_conversation_end_to_end(monkeypatch):
    """'hello sarthi' flows through the brain and gets a conversational reply."""
    # Point hermes.service.chat at a deterministic fake so no model is needed.
    monkeypatch.setattr(
        "hermes.service.chat",
        lambda message: ProviderResponse(
            success=True, provider="Fake", model="m", text="Hello! How can I help?"
        ),
    )

    engine = BrainEngine()
    response = engine.process("hello sarthi")

    assert response.success is True
    assert response.action_result["message"] == "Hello! How can I help?"


def test_api_dict_lifts_nlp_source_and_provider():
    """to_api_dict surfaces source/provider/model so the UI can badge it."""
    from brain.response import BrainResponse

    response = BrainResponse(
        intent=Intent(action="unknown", target="hello", raw_text="hello"),
        success=True,
        status="executed",
        action_result={
            "source": "nlp",
            "message": "Hello there!",
            "provider": "OpenRouter",
            "model": "openai/gpt-5",
        },
    )

    data = response.to_api_dict()
    assert data["source"] == "nlp"
    assert data["provider"] == "OpenRouter"
    assert data["model"] == "openai/gpt-5"
    assert data["text"] == "Hello there!"


def test_api_dict_omits_lifted_fields_when_absent():
    """Non-skill replies don't get NLP metadata at the top level."""
    from brain.response import BrainResponse

    response = BrainResponse(
        intent=Intent(action="open", target="chrome"),
        success=True,
        status="executed",
        action_result={"message": "Opened"},
    )

    data = response.to_api_dict()
    assert data["source"] is None
    assert data["provider"] is None
    assert data["model"] is None


def test_brain_pipeline_imperative_still_works():
    """A real command ('check github') is not hijacked by the NLP fallback."""
    engine = BrainEngine()
    response = engine.process("check github")

    # Either github is configured (tracked) or the skill surfaces its
    # not_configured message — never a generic no_handler or conversation.
    assert response.status != "no_handler"
    assert response.action_result is None or "message" not in (response.action_result or {})


def test_casual_what_question_reaches_nlp_not_project_tracker(monkeypatch):
    """A casual 'what' question is answered by the NLP skill, never a GitHub dump."""
    monkeypatch.setattr(
        "hermes.service.chat",
        lambda message, session_id=None: ProviderResponse(
            success=True,
            provider="Fake",
            model="m",
            text="Paris is the capital of France.",
        ),
    )

    engine = BrainEngine()
    response = engine.process("What is the capital of France?")

    assert response.success is True
    assert response.to_api_dict()["source"] == "nlp"
    assert response.action_result["message"] == "Paris is the capital of France."


def test_casual_how_question_reaches_nlp_not_project_tracker(monkeypatch):
    """A casual 'how' question is answered by the NLP skill, never a GitHub dump."""
    monkeypatch.setattr(
        "hermes.service.chat",
        lambda message, session_id=None: ProviderResponse(
            success=True, provider="Fake", model="m", text="I am doing great, thanks!"
        ),
    )

    engine = BrainEngine()
    response = engine.process("how are you today")

    assert response.success is True
    assert response.to_api_dict()["source"] == "nlp"


def test_project_context_question_stays_with_project_tracker(monkeypatch):
    """A 'what/how' question about projects still goes to the project tracker."""
    from skills.project_tracker.main import GitHubProjectSkill

    # Deterministic: no GitHub lookup, no local-DB dependency.
    monkeypatch.setattr(GitHubProjectSkill, "_ensure_github", lambda self: "test-user")
    monkeypatch.setattr(
        GitHubProjectSkill, "project_status", lambda self, repositories=None: "2 projects tracked."
    )

    engine = BrainEngine()
    response = engine.process("how are my repos doing")

    # project_tracker owns it — the NLP fallback must NOT have been reached.
    assert response.success is True
    assert response.to_api_dict()["source"] is None
    assert response.status == "2 projects tracked."


def test_executor_handled_short_circuits_before_fallback():
    """A claiming skill's handled=True stops later fallback skills."""
    executor = BrainExecutor()
    executor.register_skill(ClaimingSkill())
    executor.register_skill(ChattySkill())  # would override if reached

    result = executor.execute(Intent(action="check", target="github"))

    assert result["success"] is False
    assert result["status"] == "not_configured"
    assert "not configured" in result["error"]


def test_executor_uses_fallback_when_nobody_claims():
    """When no skill claims or handles, the fallback (last) skill answers."""
    executor = BrainExecutor()

    class DecliningSkill:
        name = "decliner"

        def execute(self, intent):
            return {"success": False, "status": "unknown"}

    executor.register_skill(DecliningSkill())
    executor.register_skill(ChattySkill())

    result = executor.execute(Intent(action="unknown", target="hello"))

    assert result["success"] is True
    assert result["result"]["message"] == "chat"
