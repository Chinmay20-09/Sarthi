"""Consolidation characterization tests (Phase B of the consolidation pass).

These tests lock the architectural boundaries the consolidation established,
so they cannot silently drift back later:

1. Routing      — simple commands stay deterministic; Hermes is never woken
                  for a plain command.
2. Chain intent — ordinary requests that merely mention an AI are NOT chains.
3. Escalation   — a task-shaped sentence the interpreter can only mis-read as
                  a web search is handed to Hermes BEFORE anything executes.
4. One Hermes   — there is exactly one model-driven tool loop.
5. Sandbox      — one canonical root, identical from any working directory.
6. Browser      — semantic element targeting; coordinate guessing is opt-in.

No real browser, model or network access happens here.
"""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from api import _is_task_shaped_search, app
from brain.interpreter import interpret, interpret_many
from fastapi.testclient import TestClient
from hermes.router import looks_like_task_instruction, route_command

client = TestClient(app)

# The request that used to be answered by literally searching the web for its
# own words (see docs/CONSOLIDATION_PLAN.md, finding V4).
PDF_TASK = "Find all assignment PDFs and rename them according to subject"


# ----------------------------------------------------------------------
# 1. Simple commands stay deterministic
# ----------------------------------------------------------------------


class TestDeterministicRouting:
    def test_open_chrome_is_deterministic(self):
        assert [(i.action, i.target) for i in interpret_many("Open Chrome")] == [
            ("open", "Chrome")
        ]
        assert route_command("Open Chrome").route == "fast"

    def test_open_youtube_is_deterministic(self):
        assert [(i.action, i.target) for i in interpret_many("Open YouTube")] == [
            ("open", "youtube")
        ]
        assert route_command("Open YouTube").route == "fast"

    def test_polite_prefix_still_opens_deterministically(self):
        # The router may call "please open chrome" complex (its first word is
        # not an action word), but the interpreter understands it and the
        # escalation gate never fires for open-family commands.
        assert interpret("please open chrome").action == "open"
        assert _is_task_shaped_search("please open chrome") is False

    def test_compound_open_and_search_is_not_a_task_instruction(self):
        assert [i.action for i in interpret_many("open youtube and search lofi")] == [
            "open",
            "search",
        ]
        assert _is_task_shaped_search("open youtube and search lofi") is False
        assert route_command("open youtube and search lofi").route == "fast"

    def test_play_and_close_shapes_stay_fast(self):
        assert route_command("play lost in love").route == "fast"
        assert route_command("close spotify").route == "fast"


# ----------------------------------------------------------------------
# 2. Chain-intent detection does not collide with ordinary requests
# ----------------------------------------------------------------------


class TestChainIntentCollision:
    def test_search_for_openai_is_not_a_chain(self):
        assert interpret("search for OpenAI").action == "search"
        assert interpret("search for OpenAI").action != "chain"

    def test_browser_task_mentioning_openai_is_not_a_chain(self):
        # The sandbox-proven misfire: this must stay an open + search command.
        intents = interpret_many('Open Google, search for "OpenAI", copy the URL')
        assert [i.action for i in intents] == ["open", "search"]

    def test_use_chatgpt_to_write_a_script_is_not_a_chain(self):
        intent = interpret("Use ChatGPT to write a script")
        assert intent.action != "chain"
        # It is genuinely complex (AI interaction) but not a chain, so it is
        # never executed as a deterministic AI chain.
        assert route_command("Use ChatGPT to write a script").route == "hermes"

    def test_open_chain_with_two_known_ais_is_a_chain(self):
        intent = interpret(
            "open chatgpt and get a prompt for a birthday invitation and send it to gemini"
        )
        assert intent.action == "chain"
        assert intent.target.startswith("open chatgpt")

    def test_trigger_word_and_two_known_ais_is_a_chain(self):
        intent = interpret("run translate this from chatgpt to gemini")
        assert intent.action == "chain"

    def test_from_to_with_unknown_names_is_not_a_chain(self):
        assert interpret("run from home to office").action != "chain"

    def test_slash_chain_keeps_the_documented_default_ais(self):
        # Explicit /chain requests keep the chatgpt -> gemini default; this is
        # deliberate (see docs/ARCHITECTURAL_DECISIONS.md, decision D3).
        from skills.automation_engine.ai_chain.parsing import parse_chain_command

        assert interpret("/chain make a logo").action == "chain"
        request = parse_chain_command("/chain make a logo")
        assert (request.ai1, request.ai2) == ("chatgpt", "gemini")
        assert request.query == "make a logo"


# ----------------------------------------------------------------------
# 3. Task-shaped instructions escalate to Hermes before executing
# ----------------------------------------------------------------------


class TestTaskShapedEscalation:
    def test_interpreter_still_misreads_the_pdf_task(self):
        # Known interpreter limitation (locked here, not hidden): the sentence
        # parses as a search. The gate below is what stops Sarthi from
        # executing that literal search.
        assert interpret(PDF_TASK).action == "search"

    def test_router_calls_it_complex(self):
        route = route_command(PDF_TASK)
        assert route.route == "hermes"
        assert "task_instruction" in ",".join(route.signals)

    def test_task_instruction_heuristic_is_narrow(self):
        assert looks_like_task_instruction(PDF_TASK) is True
        assert looks_like_task_instruction("download the invoices and convert them") is True
        # A short single-verb search query is not a task instruction.
        assert looks_like_task_instruction("search for OpenAI") is False
        assert looks_like_task_instruction("open youtube") is False

    def test_gate_fires_only_for_task_shaped_searches(self):
        assert _is_task_shaped_search(PDF_TASK) is True
        assert _is_task_shaped_search("search for OpenAI") is False
        assert _is_task_shaped_search("open youtube") is False
        assert _is_task_shaped_search("close spotify") is False
        assert _is_task_shaped_search("browse example.com") is False

    def test_task_shaped_request_is_handed_to_hermes_without_the_search(self):
        agent_result = {
            "success": True,
            "text": "I can't rename files yet — here is what I would need.",
            "tool_used": None,
            "iterations": 1,
            "timed_out": False,
            "reason": "final_answer",
            "provider": "Fake",
            "model": "fake-8b",
            "error": None,
        }
        with patch("hermes.service.run_task") as mock_run_task:
            mock_run_task.return_value = agent_result
            response = client.post("/command", json={"query": PDF_TASK})

        assert response.status_code == 200
        data = response.json()
        assert data["routing"] == "hermes"
        assert data["response"] == agent_result["text"]
        mock_run_task.assert_called_once()
        # The deterministic search is deliberately skipped: Hermes reasons
        # about the request instead of Sarthi literally searching the web.
        assert mock_run_task.call_args.kwargs.get("allow_fast_path") is False

    def test_simple_command_never_reaches_hermes(self):
        with patch("hermes.service.run_task") as mock_run_task:
            response = client.post("/command", json={"query": "open youtube"})

        assert response.status_code == 200
        assert response.json()["routing"] == "command"
        mock_run_task.assert_not_called()

    def test_gate_never_breaks_command_when_hermes_is_down(self):
        with patch("hermes.service.run_task", side_effect=RuntimeError("hermes down")):
            response = client.post("/command", json={"query": PDF_TASK})

        assert response.status_code == 200
        assert "success" in response.json()


# ----------------------------------------------------------------------
# 4. Exactly one Hermes reasoning loop
# ----------------------------------------------------------------------


class TestSingleHermesLoop:
    def test_the_duplicate_tool_loop_is_gone(self):
        import hermes.tool_planner as tool_planner

        assert not hasattr(tool_planner, "ToolPlanner")
        assert not hasattr(tool_planner, "MAX_TOOL_CALLS_PER_TASK")

    def test_tool_planner_keeps_only_the_protocol(self):
        import hermes.tool_planner as tool_planner

        for name in (
            "parse_tool_call",
            "build_decision_instructions",
            "build_followup_instructions",
        ):
            assert callable(getattr(tool_planner, name))

    def test_agent_is_the_only_loop_and_the_protocol_is_shared(self):
        import hermes.agent as agent_module

        # The agent uses the shared protocol helpers rather than its own copies.
        assert agent_module.build_decision_instructions is not None
        assert agent_module.parse_tool_call is not None

    def test_orchestrator_process_delegates_to_the_agent_without_fast_path(self):
        from hermes.models import Task
        from hermes.orchestrator import HermesOrchestrator
        from hermes.providers.manager import ProviderManager

        orchestrator = HermesOrchestrator(ProviderManager())
        fake_agent = MagicMock()
        fake_agent.run.return_value = {
            "success": True,
            "text": "done",
            "provider": "Fake",
            "model": "fake-8b",
            "tool_used": "open_app",
            "error": None,
        }
        with patch("hermes.orchestrator.HermesAgent", return_value=fake_agent):
            response = orchestrator.process(
                Task(
                    id="task_x",
                    prompt="do the thing",
                    task_type="chat",
                    history=[{"role": "user", "content": "earlier"}],
                    memory="remembered fact",
                )
            )

        # One loop, called once, with the caller's identity preserved.
        fake_agent.run.assert_called_once_with(
            "do the thing",
            history=[{"role": "user", "content": "earlier"}],
            memory="remembered fact",
            task_id="task_x",
            task_type="chat",
        )
        assert response.success is True
        assert response.provider == "Fake"
        assert response.tool_used == "open_app"

    def test_orchestrator_agent_disables_the_fast_path(self):
        from hermes.orchestrator import HermesOrchestrator
        from hermes.providers.manager import ProviderManager

        orchestrator = HermesOrchestrator(ProviderManager())
        with patch("hermes.orchestrator.HermesAgent") as mock_cls:
            mock_cls.return_value.run.return_value = {"success": False}
            orchestrator._get_agent()

        # The deterministic fast path is only for the /command fallback; the
        # explicit Hermes endpoint already ran Sarthi's pipeline.
        assert mock_cls.call_args.kwargs.get("fast_path") is False

    def test_retry_bound_defaults_to_three(self):
        from hermes.agent import DEFAULT_MAX_ITERATIONS
        from hermes.config.settings import HermesConfig

        assert DEFAULT_MAX_ITERATIONS == 3
        assert HermesConfig().agent_max_iterations == 3


# ----------------------------------------------------------------------
# 5. One canonical sandbox root
# ----------------------------------------------------------------------


class TestSandboxCanonicalRoot:
    def test_default_root_is_the_backend_sandbox(self):
        from hermes.sandbox import BACKEND_ROOT, DEFAULT_SANDBOX_ROOT, resolve_sandbox_root

        assert BACKEND_ROOT.name == "Backend"
        assert DEFAULT_SANDBOX_ROOT == BACKEND_ROOT / "sandbox"
        assert DEFAULT_SANDBOX_ROOT.is_absolute()
        assert resolve_sandbox_root(None) == DEFAULT_SANDBOX_ROOT
        assert resolve_sandbox_root("") == DEFAULT_SANDBOX_ROOT

    def test_relative_path_resolves_against_the_backend_root(self):
        from hermes.sandbox import BACKEND_ROOT, DEFAULT_SANDBOX_ROOT, resolve_sandbox_root

        assert resolve_sandbox_root("sandbox") == DEFAULT_SANDBOX_ROOT
        assert resolve_sandbox_root("custom_store") == (BACKEND_ROOT / "custom_store").resolve()

    def test_absolute_path_is_honoured(self, tmp_path):
        from hermes.sandbox import resolve_sandbox_root

        assert resolve_sandbox_root(tmp_path) == tmp_path

    def test_same_root_from_project_root_and_from_backend(self, monkeypatch):
        """The configured value "sandbox" must mean the same store from both

        launch directories — the divergence this pass removed.
        """
        from hermes.sandbox import BACKEND_ROOT, DEFAULT_SANDBOX_ROOT, resolve_sandbox_root

        monkeypatch.chdir(BACKEND_ROOT.parent)  # repo root (pytest, api.py)
        from_project_root = resolve_sandbox_root("sandbox")
        monkeypatch.chdir(BACKEND_ROOT)  # sarthi.bat / clean_sandbox.py
        from_backend = resolve_sandbox_root("sandbox")

        assert from_project_root == from_backend == DEFAULT_SANDBOX_ROOT
        # ...and it is NOT the cwd-relative store the divergence used to create
        assert from_project_root != (BACKEND_ROOT.parent / "sandbox")

    def test_task_sandbox_defaults_to_the_canonical_root(self):
        from hermes.sandbox import DEFAULT_SANDBOX_ROOT, TaskSandbox

        sandbox = TaskSandbox()
        assert sandbox.index_path == DEFAULT_SANDBOX_ROOT / "index.json"
        assert sandbox.tasks_dir == DEFAULT_SANDBOX_ROOT / "tasks"

    def test_explicit_absolute_root_is_used_as_given(self, tmp_path):
        from hermes.sandbox import TaskSandbox

        sandbox = TaskSandbox(tmp_path)
        assert sandbox.index_path == tmp_path / "index.json"

    def test_config_loader_resolves_the_configured_path(self, monkeypatch, tmp_path):
        from hermes.config.loader import ConfigLoader
        from hermes.sandbox import DEFAULT_SANDBOX_ROOT

        monkeypatch.setenv("HERMES_SANDBOX_PATH", "sandbox")
        monkeypatch.setattr(ConfigLoader, "_cached", None)
        assert Path(ConfigLoader().load().sandbox_path) == DEFAULT_SANDBOX_ROOT

        monkeypatch.setenv("HERMES_SANDBOX_PATH", str(tmp_path))
        monkeypatch.setattr(ConfigLoader, "_cached", None)
        assert Path(ConfigLoader().load().sandbox_path) == tmp_path


# ----------------------------------------------------------------------
# 6. Browser: semantic targets first, coordinate guessing opt-in
# ----------------------------------------------------------------------


class TestBrowserSemanticTargeting:
    def test_coordinate_scan_is_off_by_default(self, monkeypatch):
        from skills.automation_engine.ai_chain import registry

        monkeypatch.delenv(registry.COORDINATE_SCAN_ENV, raising=False)
        assert registry.coordinate_scan_enabled() is False

    def test_coordinate_scan_can_be_opted_in(self, monkeypatch):
        from skills.automation_engine.ai_chain import registry

        monkeypatch.setenv(registry.COORDINATE_SCAN_ENV, "1")
        assert registry.coordinate_scan_enabled() is True

    def test_copy_affordance_is_a_semantic_element(self):
        from skills.automation_engine.ai_chain import registry

        actions = registry.get_actions("chatgpt")
        assert actions.copy.uses_button is True
        assert actions.copy.label == "Copy"

    def test_dom_matcher_finds_the_copy_button_by_label(self):
        from skills.automation_engine.ai_chain.dom import find_affordances

        matcher = SimpleNamespace(tag="button", attribute="aria-label", value_pattern="^copy$")
        html = (
            "<div><button aria-label='Regenerate'>Regenerate</button>"
            "<button aria-label='Copy'>Copy</button></div>"
        )
        assert find_affordances(html, matcher) == ["Copy"]
        assert find_affordances("<div><button aria-label='Stop'>Stop</button></div>", matcher) == []

    def test_semantic_pick_chooses_the_newest_matching_element(self):
        """The newest message's Copy button wins (chat UIs append at the end)."""
        from skills.automation_engine.ai_chain.dom import pick_element

        matcher = SimpleNamespace(tag="button", attribute="aria-label", value_pattern="^copy$")
        html = "<button aria-label='Copy'>Copy</button>"
        candidates = {
            "button|aria-label": [
                {"v": "Copy", "x": 10.0, "y": 10.0, "w": 4.0, "h": 4.0},
                {"v": "Copy", "x": 20.0, "y": 90.0, "w": 4.0, "h": 4.0},
            ]
        }

        picked = pick_element(html, candidates, [matcher])

        assert picked is not None
        _matcher, value, rect = picked
        assert value == "Copy"
        assert rect.x == 20.0  # the last (newest) matching element

    def test_semantic_pick_returns_none_when_the_label_is_absent(self):
        from skills.automation_engine.ai_chain.dom import pick_element

        matcher = SimpleNamespace(tag="button", attribute="aria-label", value_pattern="^copy$")
        assert pick_element("<div>nothing here</div>", {}, [matcher]) is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
