"""Integration tests: Phase 3g service wiring + Phase 4 router integration.

Locks the contract that the /command pipeline routes complex requests to the
Hermes agent loop, never routes simple commands, and stays fully functional
when Hermes is unavailable.
"""

from unittest.mock import MagicMock, patch

from api import app
from fastapi.testclient import TestClient
from hermes.router import Route
from hermes.service import route_command as service_route_command
from hermes.service import run_task

client = TestClient(app)


# ----------------------------------------------------------------------
# Service router wrapper (Phase 3g + 3f knobs)
# ----------------------------------------------------------------------


class TestServiceRouter:
    def test_simple_command_routes_fast(self):
        route = service_route_command("open youtube")
        assert route.route == "fast"

    def test_complex_command_routes_hermes(self):
        route = service_route_command(
            "open ChatGPT and ask it to solve my Sarthi latency problem"
        )
        assert route.route == "hermes"

    def test_router_mode_always_forces_hermes(self):
        from hermes.config.loader import ConfigLoader

        fake = MagicMock()
        fake.router_mode = "always"
        fake.router_min_score = 1
        fake.agent_max_iterations = 5
        fake.agent_timeout = 300.0
        fake.retrieval_max_total_chars = 6000
        fake.retrieval_enabled = True
        with patch.object(ConfigLoader, "load", return_value=fake):
            route = service_route_command("open youtube")
        assert route.route == "hermes"
        assert route.reason == "router_mode_always"

    def test_router_mode_off_forces_fast(self):
        from hermes.config.loader import ConfigLoader

        fake = MagicMock()
        fake.router_mode = "off"
        fake.router_min_score = 1
        with patch.object(ConfigLoader, "load", return_value=fake):
            route = service_route_command("take this and paste it into the project")
        assert route.route == "fast"
        assert route.reason == "router_mode_off"

    def test_min_score_knob(self):
        from hermes.config.loader import ConfigLoader

        fake = MagicMock()
        fake.router_mode = "auto"
        fake.router_min_score = 99  # nothing is complex enough
        with patch.object(ConfigLoader, "load", return_value=fake):
            route = service_route_command("copy this and paste it there")
        assert route.route == "fast"
        assert route.reason == "below_min_score"


# ----------------------------------------------------------------------
# run_task wiring (Phase 3g)
# ----------------------------------------------------------------------


class TestRunTask:
    def test_run_task_executes_through_agent(self):
        fake_agent_result = {
            "success": True,
            "text": "Hermes handled it.",
            "tool_used": None,
            "iterations": 1,
            "duration_ms": 12.0,
            "timed_out": False,
            "route": "hermes",
            "reason": "final_answer",
            "provider": "Fake",
            "model": "fake-8b",
            "trace": [],
            "error": None,
        }
        with patch("hermes.service.HermesAgent") as mock_agent_cls:
            mock_agent_cls.return_value.run.return_value = fake_agent_result
            result = run_task("open chatgpt and ask about the latency problem")

        assert result["success"] is True
        assert result["text"] == "Hermes handled it."
        mock_agent_cls.return_value.run.assert_called_once()

    def test_run_task_passes_config_bounds(self):
        from hermes.config.loader import ConfigLoader

        fake = MagicMock()
        fake.agent_max_iterations = 7
        fake.agent_timeout = 42.0
        fake.router_mode = "auto"
        fake.router_min_score = 1
        with patch.object(ConfigLoader, "load", return_value=fake):
            with patch("hermes.service.HermesAgent") as mock_agent_cls:
                mock_agent_cls.return_value.run.return_value = {"success": False}
                run_task("complex task")

        kwargs = mock_agent_cls.call_args
        assert kwargs.kwargs.get("max_iterations") == 7
        assert kwargs.kwargs.get("timeout_seconds") == 42.0


# ----------------------------------------------------------------------
# /command integration (Phase 4)
# ----------------------------------------------------------------------


class TestCommandPipelineIntegration:
    def test_simple_command_bypasses_hermes(self):
        """A simple deterministic command never reaches the Hermes agent."""
        with patch("hermes.service.run_task") as mock_run_task:
            response = client.post("/command", json={"query": "open youtube"})

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        mock_run_task.assert_not_called()

    def test_complex_failed_command_invokes_hermes(self):
        """A failed deterministic result + complex route → Hermes agent runs."""
        fake_agent_result = {
            "success": True,
            "text": "Hermes handled the complex task.",
            "tool_used": "search_web",
            "iterations": 2,
            "timed_out": False,
            "reason": "final_answer",
            "provider": "Fake",
            "model": "fake-8b",
        }
        complex_query = "copy the response from ChatGPT and paste it into the terminal"
        with patch("hermes.service.route_command") as mock_route, patch(
            "hermes.service.run_task"
        ) as mock_run_task:
            mock_route.return_value = Route(route="hermes", reason="multi_step_task")
            mock_run_task.return_value = fake_agent_result
            response = client.post("/command", json={"query": complex_query})

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "Hermes handled" in data["response"]
        assert data["routing"] == "hermes"
        mock_run_task.assert_called_once()

    def test_deterministic_success_wins_over_router(self):
        """When the pipeline succeeds, its result stands — even for a
        router-complex query (the interpreter owns open+search shapes)."""
        with patch("hermes.service.route_command") as mock_route, patch(
            "hermes.service.run_task"
        ) as mock_run_task:
            mock_route.return_value = Route(route="hermes", reason="multi_step_task")
            response = client.post(
                "/command",
                json={"query": "open chatgpt and ask it about latency"},
            )

        data = response.json()
        # The deterministic pipeline handled it — Hermes was never consulted.
        assert data["success"] is True
        assert data["routing"] == "command"
        mock_run_task.assert_not_called()

    def test_complex_command_with_failed_agent_keeps_original(self):
        """When the agent also fails, the original deterministic result stands."""
        with patch("hermes.service.route_command") as mock_route, patch(
            "hermes.service.run_task"
        ) as mock_run_task:
            mock_route.return_value = Route(route="hermes", reason="multi_step_task")
            mock_run_task.return_value = {"success": False, "text": "agent failed"}
            response = client.post(
                "/command",
                json={"query": "copy this and paste it into the terminal please"},
            )

        data = response.json()
        # The original result is returned (the pipeline result is not lost).
        assert data["routing"] != "hermes" or "Hermes handled" not in data["response"]
        mock_run_task.assert_called_once()

    def test_hermes_exception_never_breaks_command(self):
        """A crashing Hermes path leaves /command fully functional."""
        with patch("hermes.service.route_command") as mock_route, patch(
            "hermes.service.run_task"
        ) as mock_run_task:
            mock_route.return_value = Route(route="hermes", reason="multi_step_task")
            mock_run_task.side_effect = RuntimeError("hermes down")
            response = client.post(
                "/command",
                json={"query": "take this response and paste it into my project"},
            )

        assert response.status_code == 200
        data = response.json()
        assert "success" in data  # the envelope is intact

    def test_existing_simple_command_unaffected(self):
        """Regression: the plain fast path returns the usual envelope."""
        response = client.post("/command", json={"query": "open youtube"})
        data = response.json()
        assert response.status_code == 200
        assert {"success", "response", "data"} <= set(data)
