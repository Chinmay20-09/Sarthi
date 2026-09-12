"""Backend API tests for the client/backend architecture.

Locks the client-facing contract on ``POST /command``:

    - the API starts and reports health
    - {"query": ...} (client-independent schema) is accepted
    - {"text": ...} (legacy UI schema) still works — no duplicate pipeline
    - invalid requests are rejected (422 from validation, envelope for
      empty text)
    - the response carries the stable envelope: success / response / data
      while every legacy field is preserved for the web UI

These tests use the real FastAPI app with the TestClient — the brain
pipeline itself is exercised by the rest of the suite.
"""

from __future__ import annotations

from api import app
from fastapi.testclient import TestClient


class TestApiStarts:
    def test_health_endpoint(self):
        client = TestClient(app)
        response = client.get("/health")
        assert response.status_code == 200
        body = response.json()
        assert body["assistant"] == "Sarthi"
        assert body["status"] == "Running"

    def test_app_has_command_route(self):
        paths = {
            route.path
            for route in app.routes
            if hasattr(route, "path") and isinstance(getattr(route, "path"), str)
        }
        assert "/command" in paths


class TestCommandQuerySchema:
    def test_query_request_returns_envelope(self):
        client = TestClient(app)
        response = client.post("/command", json={"query": ""})
        assert response.status_code == 200
        body = response.json()
        # The client-facing envelope
        assert body["success"] is False
        assert body["response"] == "Please enter a command."
        assert body["data"] is None
        # Legacy fields preserved
        assert body["text"] == "Please enter a command."
        assert body["routing"] == "command"

    def test_unknown_field_rejected(self):
        client = TestClient(app)
        response = client.post("/command", json={"query": "hi", "nope": 1})
        assert response.status_code == 422  # extra="forbid"

    def test_missing_both_text_and_query_rejected(self):
        client = TestClient(app)
        response = client.post("/command", json={})
        assert response.status_code == 422


class TestCommandLegacySchema:
    def test_text_request_still_works(self):
        client = TestClient(app)
        response = client.post("/command", json={"text": ""})
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is False
        assert body["response"] == "Please enter a command."

    def test_text_and_query_both_accepted(self):
        client = TestClient(app)
        response = client.post("/command", json={"text": "", "query": ""})
        assert response.status_code == 200
        assert response.json()["success"] is False

    def test_empty_text_runs_pipeline_not_validation_error(self):
        """Empty (but present) text is a pipeline-level error, not 422."""
        client = TestClient(app)
        response = client.post("/command", json={"text": "   "})
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is False
        assert body["error"] == "empty input"


class TestCommandProcessing:
    def test_mode_command_processed(self):
        """A real query flows through the shared pipeline (mode switch)."""
        client = TestClient(app)
        response = client.post("/command", json={"query": "/exit"})
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["action"] == "mode"
        assert body["response"]
        # The envelope mirrors the human-readable text
        assert body["response"] == body["text"]
        # Ensure the mode is left in default for other tests
        client.post("/command", json={"query": "/exit"})

    def test_data_carries_structured_result(self):
        client = TestClient(app)
        response = client.post("/command", json={"query": "/exit"})
        body = response.json()
        assert isinstance(body["data"], dict)
        assert body["data"].get("mode") == "default"


class TestEnvelopeShape:
    def test_envelope_is_client_independent(self):
        """The response must not be tied to any one client type."""
        client = TestClient(app)
        body = client.post("/command", json={"query": "/exit"}).json()
        # Exactly the three fields every client can rely on...
        assert isinstance(body["success"], bool)
        assert isinstance(body["response"], str)
        assert body["data"] is None or isinstance(body["data"], dict)
        # ...plus the legacy payload, still present for the web UI.
        for legacy in ("action", "target", "status", "text", "mode", "routing"):
            assert legacy in body
        client.post("/command", json={"query": "/exit"})
