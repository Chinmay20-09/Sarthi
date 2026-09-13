"""Tests for the Hermes complexity router (Backend/hermes/router.py).

Phase 3a contract:
- Simple deterministic commands ("open youtube", "play lost in love") stay on
  the fast path — routing must never invoke Hermes, the 8B model, embeddings,
  database retrieval, or the agent loop.
- Multi-step / context-dependent / data-flow requests route to Hermes.
- Existing command behavior (interpreter shapes) is unaffected.
"""

import builtins
import subprocess
import sys
from unittest.mock import patch

import pytest
from hermes.router import Route, is_compound, looks_like_url, route_command

# ---------------------------------------------------------------------------
# Required fast-path cases
# ---------------------------------------------------------------------------


class TestFastPathRequired:
    """The four commands the architecture locks to the fast path."""

    @pytest.mark.parametrize(
        "command",
        [
            "open youtube",
            "open chrome",
            "play lost in love",
            "close spotify",
        ],
    )
    def test_simple_commands_route_fast(self, command):
        route = route_command(command)
        assert route.route == "fast"
        assert route.reason == "simple_command"
        assert route.score < 1
        assert route.signals, "fast verdicts should still record their signals"

    def test_slash_prefix_behaves_like_plain_command(self):
        assert route_command("/open youtube").route == "fast"

    def test_empty_input_routes_fast_without_crashing(self):
        for text in ("", "   "):
            route = route_command(text)
            assert route.route == "fast"
            assert route.reason == "empty_input"


# ---------------------------------------------------------------------------
# Required hermes-path cases
# ---------------------------------------------------------------------------


class TestHermesPathRequired:
    """Multi-step, context-dependent, and data-flow requests go to Hermes."""

    @pytest.mark.parametrize(
        "command",
        [
            "open ChatGPT and ask it to solve my Sarthi latency problem",
            "take this response and paste it into my project",
            "find what I worked on last week and summarize it",
            "open my Sarthi project and ask ChatGPT to analyze the backend",
            "copy the response from ChatGPT and paste it into the terminal",
        ],
    )
    def test_complex_commands_route_hermes(self, command):
        route = route_command(command)
        assert route.route == "hermes"
        assert route.score >= 1
        assert route.signals

    def test_route_reason_is_stable_machine_readable(self):
        route = route_command("copy this and paste it into the terminal")
        assert route.route == "hermes"
        assert route.reason in {
            "multi_step_task",
            "no_action_word",
            "simple_action_word",
            "compound_connector",
            "dataflow_verb",
            "research_noun",
            "ai_interaction",
            "deixis_reference",
            "multiple_questions",
            "long_command",
            "complex_task",
        }

    def test_signals_are_machine_readable(self):
        route = route_command("copy the response and paste it into the project")
        assert "dataflow_verb" in ",".join(route.signals)
        assert "research_noun" in ",".join(route.signals)


# ---------------------------------------------------------------------------
# Interpreter-shape alignment (existing command behavior unaffected)
# ---------------------------------------------------------------------------


class TestInterpreterShapeAlignment:
    """Shapes the deterministic interpreter already parses stay fast."""

    @pytest.mark.parametrize(
        "command",
        [
            "open youtube and search python",
            "open youtube.com and play lost in love",
            "open spotify",
            "search weather today",
            "check status",
            "check pending projects",
            "pending",
            "what pending",
            "scan",
            "refresh",
            "set github username",
            "clean",
            "browse example.com",
            "visit github.com",
            "hello",
            "hi",
        ],
    )
    def test_known_single_action_shapes_stay_fast(self, command):
        assert route_command(command).route == "fast"

    def test_deterministic_ai_chain_shape_stays_fast(self):
        # "run X from chatgpt to gemini" is parsed by the automation engine —
        # the router must not send it to Hermes even though it is long and
        # contains research-ish nouns.
        route = route_command("run summarize this bug report from chatgpt to gemini")
        assert route.route == "fast"
        assert route.reason == "deterministic_ai_chain"

        route = route_command("chain translate the doc from chatgpt to claude")
        assert route.route == "fast"

    def test_ask_ai_without_chain_still_routes_hermes(self):
        # The chain veto must not swallow genuine AI-interaction requests.
        route = route_command("run a check on my project and ask chatgpt for a fix")
        assert route.route == "hermes"

    def test_open_chain_with_second_action_routes_hermes(self):
        # "open X and <imperative> ..." is a dependent two-step open chain.
        route = route_command("open chrome and check my email")
        assert route.route == "hermes"

    def test_two_app_imperatives_route_hermes(self):
        # "close X and open Y" is two imperative clauses the interpreter
        # cannot decompose — a genuine two-step task.
        route = route_command("close chrome and open firefox")
        assert route.route == "hermes"
        assert "dependent_open_chain" in ",".join(route.signals)

    def test_followup_clause_routes_hermes(self):
        # "after/once/when it <verb>" marks dependency between steps.
        route = route_command("open github and after it loads copy the readme")
        assert route.route == "hermes"
        assert "followup_clause" in ",".join(route.signals)

    def test_sequencing_connectors_route_hermes(self):
        route = route_command("open youtube then search python tutorials")
        assert route.route == "hermes"
        assert "compound_connector" in ",".join(route.signals)


# ---------------------------------------------------------------------------
# Router must never initialize Hermes / model / DB
# ---------------------------------------------------------------------------


class TestRouterIsLightweight:
    """Routing adds microseconds — it must not touch heavy machinery."""

    def test_router_does_not_import_hermes_model_stack(self):
        # A fresh interpreter must be able to import the router without any
        # of the heavy modules (providers, orchestrator, database, agents).
        code = (
            "import sys; from hermes.router import route_command;"
            "assert 'hermes.orchestrator' not in sys.modules;"
            "assert 'hermes.providers' not in sys.modules;"
            "assert 'database.manager' not in sys.modules;"
            "assert 'hermes.agent' not in sys.modules;"
            "print('clean')"
        )
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert result.returncode == 0, result.stderr
        assert "clean" in result.stdout

    def test_route_command_is_fast(self):
        import time

        # One routed command must stay well below the ~10ms fast-path budget.
        start = time.perf_counter()
        for _ in range(200):
            route_command("open youtube")
            route_command("take this response and paste it into my project")
        elapsed_ms = (time.perf_counter() - start) * 1000
        # 400 routings in well under 100ms total (~0.25ms each).
        assert elapsed_ms < 100, f"routing too slow: {elapsed_ms:.1f}ms"

    def test_route_command_never_imports_model_stacks(self):
        # Even in a warm interpreter where heavy packages may already be
        # cached, routing a command must not trigger any new import of an
        # inference/agent stack.
        blocked = {"ollama", "torch", "transformers", "sentence_transformers"}
        real_import = builtins.__import__

        def guarded_import(name, *args, **kwargs):
            if name in blocked:
                raise AssertionError(f"router must not import {name}")
            return real_import(name, *args, **kwargs)

        with patch.object(builtins, "__import__", guarded_import):
            assert route_command("open youtube").route == "fast"
            assert route_command("close spotify").route == "fast"


# ---------------------------------------------------------------------------
# Route dataclass + helpers
# ---------------------------------------------------------------------------


class TestRouteHelpers:
    def test_route_defaults(self):
        route = Route(route="fast", reason="simple_command")
        assert route.score == 0
        assert route.signals == []

    def test_route_as_dict_shape(self):
        route = route_command("close spotify")
        data = {"route": route.route, "reason": route.reason}
        assert data == {"route": "fast", "reason": "simple_command"}

    def test_is_compound_detects_sequencing_words(self):
        assert is_compound("open youtube then search ai")
        assert is_compound("first do x, afterwards do y")
        assert is_compound("while that runs, open notepad")
        assert not is_compound("open youtube and search python")
        assert not is_compound("play lost in love")

    def test_looks_like_url(self):
        assert looks_like_url("youtube.com")
        assert looks_like_url("https://github.com/sarthi")
        assert not looks_like_url("open youtube")
        assert not looks_like_url("")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
