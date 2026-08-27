"""Tests for Hermes chat API endpoint."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from api import app
from hermes.providers.base import ProviderResponse

client = TestClient(app)


class TestHermesChatEndpoint:
    """Test the /hermes/chat endpoint."""

    def test_chat_valid_message(self):
        """Test valid chat request."""
        # Mock the LocalHermesProvider to avoid needing actual Ollama
        with patch("hermes.routes._orchestrator", None):
            with patch("hermes.routes._get_orchestrator") as mock_get_orch:
                mock_orch = MagicMock()
                mock_response = ProviderResponse(
                    success=True,
                    provider="Ollama",
                    model="hermes3:8b",
                    text="Hello, I am Hermes.",
                )
                mock_orch.process.return_value = mock_response
                mock_get_orch.return_value = mock_orch

                response = client.post(
                    "/hermes/chat",
                    json={"message": "Hello Hermes"},
                )

                assert response.status_code == 200
                data = response.json()
                assert data["success"] is True
                assert data["provider"] == "Ollama"
                assert data["model"] == "hermes3:8b"
                assert data["response"] == "Hello, I am Hermes."
                assert data.get("error") is None

    def test_chat_empty_message(self):
        """Test empty message returns validation error."""
        response = client.post(
            "/hermes/chat",
            json={"message": ""},
        )
        # Pydantic validates min_length, returns 422
        assert response.status_code == 422

    def test_chat_whitespace_only(self):
        """Test whitespace-only message is trimmed and processed."""
        with patch("hermes.routes._orchestrator", None):
            with patch("hermes.routes._get_orchestrator") as mock_get_orch:
                mock_orch = MagicMock()
                mock_response = ProviderResponse(
                    success=False,
                    provider="Hermes",
                    model="",
                    text="",
                    error="Message cannot be empty",
                )
                mock_orch.process.return_value = mock_response
                mock_get_orch.return_value = mock_orch

                # After stripping "   " becomes "", which should be caught
                response = client.post(
                    "/hermes/chat",
                    json={"message": "   "},
                )

                # The message passes Pydantic validation (min_length=1 is "   ")
                # but our code strips it and returns error
                assert response.status_code == 200
                data = response.json()
                assert data["success"] is False

    def test_chat_missing_message(self):
        """Test missing message field returns validation error."""
        response = client.post(
            "/hermes/chat",
            json={},
        )
        assert response.status_code == 422  # Unprocessable Entity

    def test_chat_provider_failure(self):
        """Test provider failure returns graceful error."""
        with patch("hermes.routes._orchestrator", None):
            with patch("hermes.routes._get_orchestrator") as mock_get_orch:
                mock_orch = MagicMock()
                mock_response = ProviderResponse(
                    success=False,
                    provider="Ollama",
                    model="hermes3:8b",
                    text="",
                    error="Connection timeout",
                )
                mock_orch.process.return_value = mock_response
                mock_get_orch.return_value = mock_orch

                response = client.post(
                    "/hermes/chat",
                    json={"message": "Hello"},
                )

                assert response.status_code == 200
                data = response.json()
                assert data["success"] is False
                assert data["provider"] == "Ollama"
                assert "Connection timeout" in data["error"]

    def test_chat_orchestrator_exception(self):
        """Test exception during processing returns graceful error."""
        with patch("hermes.routes._orchestrator", None):
            with patch("hermes.routes._get_orchestrator") as mock_get_orch:
                mock_orch = MagicMock()
                mock_orch.process.side_effect = Exception("Unexpected error")
                mock_get_orch.return_value = mock_orch

                response = client.post(
                    "/hermes/chat",
                    json={"message": "Hello"},
                )

                assert response.status_code == 200
                data = response.json()
                assert data["success"] is False
                assert data["provider"] == "Hermes"
                assert "unavailable" in data["error"].lower()

    def test_chat_message_preserved(self):
        """Test that the message prompt is preserved in task."""
        with patch("hermes.routes._orchestrator", None):
            with patch("hermes.routes._get_orchestrator") as mock_get_orch:
                mock_orch = MagicMock()
                mock_response = ProviderResponse(
                    success=True,
                    provider="Ollama",
                    model="hermes3:8b",
                    text="Response",
                )
                mock_orch.process.return_value = mock_response
                mock_get_orch.return_value = mock_orch

                test_message = "Introduce yourself in one sentence"
                response = client.post(
                    "/hermes/chat",
                    json={"message": test_message},
                )

                assert response.status_code == 200
                # Verify the orchestrator was called with the message
                mock_orch.process.assert_called_once()
                task = mock_orch.process.call_args[0][0]
                assert task.prompt == test_message

    def test_chat_response_schema(self):
        """Test response schema matches HermesChatResponse."""
        with patch("hermes.routes._orchestrator", None):
            with patch("hermes.routes._get_orchestrator") as mock_get_orch:
                mock_orch = MagicMock()
                mock_response = ProviderResponse(
                    success=True,
                    provider="Ollama",
                    model="hermes3:8b",
                    text="Test response",
                )
                mock_orch.process.return_value = mock_response
                mock_get_orch.return_value = mock_orch

                response = client.post(
                    "/hermes/chat",
                    json={"message": "test"},
                )

                assert response.status_code == 200
                data = response.json()

                # Verify all expected fields exist
                assert "success" in data
                assert "provider" in data
                assert "model" in data
                assert "response" in data
                # error is optional in success case
                assert isinstance(data.get("error"), (str, type(None)))

    def test_health_endpoint(self):
        """Test that existing /health endpoint still works."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert "assistant" in data
        assert "status" in data


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
