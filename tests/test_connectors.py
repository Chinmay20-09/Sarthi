"""Tests for the connector architecture and Google Calendar connector.

Uses mocks for Google API calls — no real OAuth credentials needed.
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Connector models
# ---------------------------------------------------------------------------


class TestConnectorModels:
    def test_metadata_to_dict(self):
        from connectors.models import AuthType, ConnectorMetadata, ConnectorTool

        meta = ConnectorMetadata(
            id="test_connector",
            name="Test Connector",
            type="calendar",
            service="Test Service",
            auth_type=AuthType.OAUTH2,
            description="A test connector",
            icon="calendar_today",
            tools=[ConnectorTool(name="list_events", description="List events")],
        )
        d = meta.to_dict()
        assert d["id"] == "test_connector"
        assert d["auth_type"] == "oauth2"
        assert len(d["tools"]) == 1
        assert d["tools"][0]["name"] == "list_events"

    def test_status_enum(self):
        from connectors.models import ConnectorStatus

        assert ConnectorStatus.DISCONNECTED.value == "disconnected"
        assert ConnectorStatus.CONNECTED.value == "connected"
        assert ConnectorStatus.CONNECTING.value == "connecting"
        assert ConnectorStatus.ERROR.value == "error"

    def test_instance_to_dict(self):
        from connectors.models import ConnectorInstance, ConnectorStatus

        inst = ConnectorInstance(
            id=1,
            name="My Calendar",
            type="calendar",
            service="google_calendar",
            status=ConnectorStatus.CONNECTED,
        )
        d = inst.to_dict()
        assert d["id"] == 1
        assert d["status"] == "connected"


# ---------------------------------------------------------------------------
# Connector registry
# ---------------------------------------------------------------------------


class TestConnectorRegistry:
    def test_registry_singleton(self):
        from connectors.registry import get_registry

        r1 = get_registry()
        r2 = get_registry()
        assert r1 is r2

    def test_registry_registers_connector(self):
        from connectors.registry import ConnectorRegistry
        from connectors.models import AuthType, ConnectorMetadata
        from connectors.base import BaseConnector

        class MockConnector(BaseConnector):
            @property
            def metadata(self):
                return ConnectorMetadata(
                    id="mock", name="Mock", type="test", service="Mock",
                    auth_type=AuthType.NONE,
                )
            def get_auth_url(self): return ""
            def handle_auth_callback(self, url): return {"success": True}
            def disconnect(self): return {"success": True}
            def is_connected(self): return False
            def execute_tool(self, name, params=None): return {"success": True}

        registry = ConnectorRegistry()
        conn = MockConnector()
        registry.register(conn)
        # Mark as discovered so list_all doesn't try to auto-discover
        registry._discovered = True

        assert registry.get("mock") is conn
        assert registry.count == 1

    def test_registry_list_all(self):
        from connectors.registry import ConnectorRegistry
        from connectors.models import AuthType, ConnectorMetadata
        from connectors.base import BaseConnector

        class MockConnector2(BaseConnector):
            @property
            def metadata(self):
                return ConnectorMetadata(
                    id="mock2", name="Mock2", type="test", service="Mock2",
                    auth_type=AuthType.NONE,
                )
            def get_auth_url(self): return ""
            def handle_auth_callback(self, url): return {"success": True}
            def disconnect(self): return {"success": True}
            def is_connected(self): return False
            def execute_tool(self, name, params=None): return {"success": True}

        registry = ConnectorRegistry()
        registry.register(MockConnector2())
        registry._discovered = True
        all_connectors = registry.list_all()
        assert len(all_connectors) == 1
        assert all_connectors[0]["id"] == "mock2"


# ---------------------------------------------------------------------------
# Google Calendar connector (mocked)
# ---------------------------------------------------------------------------


class TestGoogleCalendarConnector:
    def test_metadata(self):
        from connectors.google_calendar.connector import GoogleCalendarConnector

        gc = GoogleCalendarConnector()
        meta = gc.metadata
        assert meta.id == "google_calendar"
        assert meta.auth_type.value == "oauth2"
        assert meta.type == "calendar"
        assert len(meta.tools) >= 1

    def test_not_connected_without_credentials(self):
        from connectors.google_calendar.connector import GoogleCalendarConnector

        gc = GoogleCalendarConnector()
        # Without credentials file, should not be connected
        with patch("connectors.google_calendar.auth.CREDENTIALS_FILE") as mock_file:
            mock_file.exists.return_value = False
            assert gc.is_connected() is False

    def test_not_connected_without_token(self):
        from connectors.google_calendar.connector import GoogleCalendarConnector

        gc = GoogleCalendarConnector()
        with patch("connectors.google_calendar.auth.CREDENTIALS_FILE") as mock_creds, \
             patch("connectors.google_calendar.auth.TOKEN_FILE") as mock_token:
            mock_creds.exists.return_value = True
            mock_token.exists.return_value = False
            with patch.object(gc, "_load_client_config", return_value={"installed": {"client_id": "test"}}):
                assert gc.is_connected() is False

    def test_connect_without_credentials_returns_error(self):
        from connectors.google_calendar.connector import GoogleCalendarConnector

        gc = GoogleCalendarConnector()
        with patch.object(gc, "_load_client_config", return_value=None):
            result = gc.connect()
            assert result["success"] is False
            assert "credentials" in result["error"].lower()

    def test_disconnect_removes_token(self):
        from connectors.google_calendar.connector import GoogleCalendarConnector

        gc = GoogleCalendarConnector()
        with patch("connectors.google_calendar.auth.delete_token", return_value=True):
            result = gc.disconnect()
            assert result["success"] is True

    def test_execute_tool_not_connected(self):
        from connectors.google_calendar.connector import GoogleCalendarConnector

        gc = GoogleCalendarConnector()
        with patch.object(gc, "_load_client_config", return_value=None):
            result = gc.execute_tool("list_events")
            assert result["success"] is False
            assert "not configured" in result["error"].lower()

    def test_execute_unknown_tool(self):
        from connectors.google_calendar.connector import GoogleCalendarConnector

        gc = GoogleCalendarConnector()
        with patch.object(gc, "_load_client_config", return_value={"installed": {"client_id": "x"}}), \
             patch("connectors.google_calendar.connector.get_valid_credentials", return_value={"access_token": "fake"}):
            result = gc.execute_tool("nonexistent_tool")
            assert result["success"] is False
            assert "unknown" in result["error"].lower()


# ---------------------------------------------------------------------------
# Auth token management (mocked)
# ---------------------------------------------------------------------------


class TestAuthTokenManagement:
    def test_store_and_load_token(self):
        from connectors.google_calendar import auth

        with tempfile.TemporaryDirectory() as tmpdir:
            token_path = Path(tmpdir) / "token.json"
            with patch.object(auth, "TOKEN_FILE", token_path), \
                 patch.object(auth, "TOKEN_DIR", Path(tmpdir)):
                token_data = {"access_token": "test_token", "refresh_token": "test_refresh"}
                result = auth.store_token(token_data)
                assert result is True

                loaded = auth.load_stored_token()
                assert loaded is not None
                assert loaded["access_token"] == "test_token"

    def test_delete_token(self):
        from connectors.google_calendar import auth

        with tempfile.TemporaryDirectory() as tmpdir:
            token_path = Path(tmpdir) / "token.json"
            token_path.write_text(json.dumps({"access_token": "x"}))
            with patch.object(auth, "TOKEN_FILE", token_path):
                assert auth.has_valid_token() is True
                result = auth.delete_token()
                assert result is True
                assert auth.has_valid_token() is False

    def test_has_credentials_false_when_missing(self):
        from connectors.google_calendar import auth

        with patch.object(auth, "CREDENTIALS_FILE") as mock_file:
            mock_file.exists.return_value = False
            assert auth.has_credentials() is False


# ---------------------------------------------------------------------------
# FastAPI endpoints (using TestClient)
# ---------------------------------------------------------------------------


class TestConnectorAPIEndpoints:
    def test_list_connectors(self):
        from fastapi.testclient import TestClient
        from api import app

        client = TestClient(app)
        response = client.get("/connectors")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "connectors" in data

    def test_connector_registry_endpoint(self):
        from fastapi.testclient import TestClient
        from api import app

        client = TestClient(app)
        response = client.get("/connectors/registry")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        # Should list at least the Google Calendar connector
        ids = [c["id"] for c in data["connectors"]]
        assert "google_calendar" in ids

    def test_google_calendar_status(self):
        from fastapi.testclient import TestClient
        from api import app

        client = TestClient(app)
        response = client.get("/connectors/google_calendar/status")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "connected" in data
        assert "status" in data

    def test_google_calendar_events_not_connected(self):
        from fastapi.testclient import TestClient
        from api import app

        client = TestClient(app)
        response = client.get("/connectors/google_calendar/events")
        assert response.status_code == 200
        data = response.json()
        # Should return error since not connected
        assert data["success"] is False

    def test_google_calendar_disconnect(self):
        from fastapi.testclient import TestClient
        from api import app

        client = TestClient(app)
        response = client.post("/connectors/google_calendar/disconnect")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    def test_add_and_delete_connector(self):
        from fastapi.testclient import TestClient
        from api import app

        client = TestClient(app)

        # Add
        response = client.post("/connectors", json={
            "name": "Test Calendar",
            "type": "calendar",
            "service": "google_calendar",
            "config": {},
        })
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        connector_id = data["connector"]["id"]

        # List — should appear
        response = client.get("/connectors")
        ids = [c["id"] for c in response.json()["connectors"]]
        assert connector_id in ids

        # Delete
        response = client.delete(f"/connectors/{connector_id}")
        assert response.status_code == 200
        assert response.json()["success"] is True

    def test_existing_command_still_works(self):
        from fastapi.testclient import TestClient
        from api import app

        client = TestClient(app)
        response = client.post("/command", json={"text": "hello"})
        assert response.status_code == 200
        data = response.json()
        assert "success" in data
