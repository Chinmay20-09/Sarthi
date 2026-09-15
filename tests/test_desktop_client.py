"""Tests for the Sarthi Desktop client (Desktop/client/sarthi_client).

All network calls are mocked — no test contacts a real backend. The
tests lock the client-side contract:

    - request construction: {"query": ...} to POST /command
    - response handling: success, failure, malformed, non-JSON
    - backend unavailable → structured failure (never an exception)
    - controller translation of every result kind into display/status text
    - configuration: env var > config file > default backend URL
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from sarthi_client import backend as client_backend
from sarthi_client import config as client_config
from sarthi_client import controller as client_controller
from sarthi_client.controller import SarthiController

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class FakeHttpResponse:
    def __init__(self, status_code: int = 200, body: Any = None, not_json: bool = False):
        self.status_code = status_code
        self._body = body
        self._not_json = not_json

    def json(self) -> Any:
        if self._not_json:
            raise ValueError("not json")
        return self._body


def successful_body(**overrides: Any) -> dict[str, Any]:
    body = {"success": True, "response": "Opening Chrome.", "data": None}
    body.update(overrides)
    return body


# ---------------------------------------------------------------------------
# Request construction
# ---------------------------------------------------------------------------


class TestRequestConstruction:
    def test_payload_is_query_schema(self):
        assert client_backend.build_command_payload("open chrome") == {"query": "open chrome"}

    def test_send_posts_query_json_to_backend_command(self, monkeypatch):
        captured: dict[str, Any] = {}

        def fake_post(url, json=None, timeout=None):
            captured["url"] = url
            captured["json"] = json
            return FakeHttpResponse(200, successful_body())

        monkeypatch.setattr(client_backend.httpx2, "post", fake_post)
        result = client_backend.send_query("open chrome", base_url="http://127.0.0.1:8000")

        assert captured["url"] == "http://127.0.0.1:8000/command"
        assert captured["json"] == {"query": "open chrome"}
        assert result["success"] is True
        assert result["response"] == "Opening Chrome."

    def test_trailing_slash_base_url_does_not_double_the_path(self, monkeypatch):
        seen = {}

        def fake_post(url, json=None, timeout=None):
            seen["url"] = url
            return FakeHttpResponse(200, successful_body())

        monkeypatch.setattr(client_backend.httpx2, "post", fake_post)
        client_backend.send_query("hi", base_url="http://127.0.0.1:8000/")
        assert seen["url"] == "http://127.0.0.1:8000/command"


# ---------------------------------------------------------------------------
# Response handling
# ---------------------------------------------------------------------------


class TestResponseHandling:
    def test_success_envelope_fields(self, monkeypatch):
        monkeypatch.setattr(
            client_backend.httpx2,
            "post",
            lambda *a, **k: FakeHttpResponse(200, successful_body()),
        )
        result = client_backend.send_query("open chrome")
        assert result["success"] is True
        assert result["response"] == "Opening Chrome."
        assert "error" not in result

    def test_success_false_still_parsed(self, monkeypatch):
        body = successful_body(success=False, response="Please enter a command.")
        monkeypatch.setattr(
            client_backend.httpx2, "post", lambda *a, **k: FakeHttpResponse(200, body)
        )
        result = client_backend.send_query("")
        assert result["success"] is False
        assert result["response"] == "Please enter a command."

    def test_http_error_status_is_structured_failure(self, monkeypatch):
        monkeypatch.setattr(client_backend.httpx2, "post", lambda *a, **k: FakeHttpResponse(422))
        result = client_backend.send_query("open chrome")
        assert result["success"] is False
        assert result["error"] == "bad_response"
        assert "422" in result["detail"]

    def test_non_json_body_is_structured_failure(self, monkeypatch):
        monkeypatch.setattr(
            client_backend.httpx2,
            "post",
            lambda *a, **k: FakeHttpResponse(200, not_json=True),
        )
        result = client_backend.send_query("open chrome")
        assert result["success"] is False
        assert result["error"] == "bad_response"

    def test_non_object_json_is_structured_failure(self, monkeypatch):
        monkeypatch.setattr(
            client_backend.httpx2, "post", lambda *a, **k: FakeHttpResponse(200, ["nope"])
        )
        result = client_backend.send_query("open chrome")
        assert result["success"] is False
        assert result["error"] == "bad_response"

    def test_missing_fields_tolerated(self, monkeypatch):
        monkeypatch.setattr(client_backend.httpx2, "post", lambda *a, **k: FakeHttpResponse(200, {}))
        result = client_backend.send_query("open chrome")
        assert result["success"] is False  # bool({}.get("success", False))
        assert result["response"] == ""
        assert result["data"] is None

    def test_legacy_text_field_used_as_response_fallback(self, monkeypatch):
        body = {"success": True, "text": "Opening Chrome.", "result": None}
        monkeypatch.setattr(
            client_backend.httpx2, "post", lambda *a, **k: FakeHttpResponse(200, body)
        )
        result = client_backend.send_query("open chrome")
        assert result["response"] == "Opening Chrome."


# ---------------------------------------------------------------------------
# Backend unavailable
# ---------------------------------------------------------------------------


class TestBackendUnavailable:
    def test_connection_error_is_structured_failure(self, monkeypatch):
        import httpx2

        def refused(*_a, **_k):
            raise httpx2.ConnectError("connection refused")

        monkeypatch.setattr(client_backend.httpx2, "post", refused)
        result = client_backend.send_query("open chrome")
        assert result["success"] is False
        assert result["error"] == "unavailable"
        assert result["response"] == ""
        assert "127.0.0.1" in result["detail"] or "backend" in result["detail"].lower()

    def test_timeout_is_structured_failure(self, monkeypatch):
        import httpx2

        def slow(*_a, **_k):
            raise httpx2.ReadTimeout("timed out")

        monkeypatch.setattr(client_backend.httpx2, "post", slow)
        result = client_backend.send_query("open chrome")
        assert result["success"] is False
        assert result["error"] == "unavailable"

    def test_socket_error_is_structured_failure(self, monkeypatch):
        def broken(*_a, **_k):
            raise OSError("network is down")

        monkeypatch.setattr(client_backend.httpx2, "post", broken)
        result = client_backend.send_query("open chrome")
        assert result["success"] is False
        assert result["error"] == "unavailable"


# ---------------------------------------------------------------------------
# Controller translation
# ---------------------------------------------------------------------------


class TestController:
    def test_invalid_query_never_reaches_the_network(self, monkeypatch):
        def boom(*_a, **_k):  # pragma: no cover - must not be called
            raise AssertionError("network must not be used for an empty query")

        monkeypatch.setattr(client_backend.httpx2, "post", boom)
        result = SarthiController("http://x").send("   ")
        assert result.display_text == ""
        assert "enter a command" in result.status_text.lower()

    def test_none_query_is_invalid(self, monkeypatch):
        def boom(*_a, **_k):  # pragma: no cover
            raise AssertionError("network must not be used for None query")

        monkeypatch.setattr(client_backend.httpx2, "post", boom)
        result = SarthiController("http://x").send(None)
        assert result.display_text == ""

    def test_success_renders_backend_response(self, monkeypatch):
        def ok(url, json=None, timeout=None):
            assert json == {"query": "open chrome"}
            return FakeHttpResponse(200, successful_body())

        monkeypatch.setattr(client_backend.httpx2, "post", ok)
        result = SarthiController("http://x").send("open chrome")
        assert result.display_text == "Opening Chrome."
        assert result.status_text == "Backend: http://x"

    def test_unavailable_renders_offline_status(self, monkeypatch):
        def refused(*_a, **_k):
            raise OSError("no route")

        monkeypatch.setattr(client_backend.httpx2, "post", refused)
        result = SarthiController("http://x").send("open chrome")
        assert result.display_text == ""
        assert result.status_text == client_controller.STATUS_OFFLINE

    def test_bad_response_renders_invalid_response_status(self, monkeypatch):
        monkeypatch.setattr(
            client_backend.httpx2,
            "post",
            lambda *a, **k: FakeHttpResponse(200, not_json=True),
        )
        result = SarthiController("http://x").send("open chrome")
        assert result.display_text == ""
        assert client_controller.STATUS_BAD_RESPONSE in result.status_text

    def test_failed_command_renders_failure_text(self, monkeypatch):
        body = successful_body(success=False, response="No matching application.")
        monkeypatch.setattr(
            client_backend.httpx2, "post", lambda *a, **k: FakeHttpResponse(200, body)
        )
        result = SarthiController("http://x").send("open nosuchapp")
        assert result.display_text == "No matching application."
        assert result.status_text == "Failed"

    def test_query_is_stripped_before_sending(self, monkeypatch):
        seen = {}

        def ok(url, json=None, timeout=None):
            seen["json"] = json
            return FakeHttpResponse(200, successful_body())

        monkeypatch.setattr(client_backend.httpx2, "post", ok)
        SarthiController("http://x").send("   open chrome  ")
        assert seen["json"] == {"query": "open chrome"}


# ---------------------------------------------------------------------------
# Configuration (single mechanism for the backend URL)
# ---------------------------------------------------------------------------


class TestConfig:
    def test_default_is_local_backend(self, monkeypatch):
        monkeypatch.delenv(client_config.ENV_BACKEND_URL, raising=False)
        monkeypatch.setattr(client_config, "load_configured_backend_url", lambda: None)
        assert client_config.get_backend_url() == client_config.DEFAULT_BACKEND_URL

    def test_env_var_overrides_default(self, monkeypatch):
        monkeypatch.setenv(client_config.ENV_BACKEND_URL, "http://192.168.1.20:8000/")
        assert client_config.get_backend_url() == "http://192.168.1.20:8000"

    def test_config_file_used_when_no_env_var(self, monkeypatch, tmp_path):
        monkeypatch.delenv(client_config.ENV_BACKEND_URL, raising=False)
        cfg = tmp_path / client_config.CONFIG_FILE_NAME
        cfg.write_text(json.dumps({"backend_url": "http://10.0.0.5:8000"}), encoding="utf-8")
        monkeypatch.setattr(client_config, "config_file_candidates", lambda: [cfg])
        assert client_config.get_backend_url() == "http://10.0.0.5:8000"

    def test_malformed_config_file_is_ignored(self, monkeypatch, tmp_path):
        monkeypatch.delenv(client_config.ENV_BACKEND_URL, raising=False)
        cfg = tmp_path / client_config.CONFIG_FILE_NAME
        cfg.write_text("{not json", encoding="utf-8")
        monkeypatch.setattr(client_config, "config_file_candidates", lambda: [cfg])
        monkeypatch.setattr(client_config, "load_configured_backend_url", lambda: None)
        assert client_config.get_backend_url() == client_config.DEFAULT_BACKEND_URL

    def test_env_var_wins_over_config_file(self, monkeypatch, tmp_path):
        monkeypatch.setenv(client_config.ENV_BACKEND_URL, "http://env:1")
        cfg = tmp_path / client_config.CONFIG_FILE_NAME
        cfg.write_text(json.dumps({"backend_url": "http://file:2"}), encoding="utf-8")
        monkeypatch.setattr(client_config, "config_file_candidates", lambda: [cfg])
        assert client_config.get_backend_url() == "http://env:1"


# ---------------------------------------------------------------------------
# GUI (headless where possible — tkinter may be unavailable in CI)
# ---------------------------------------------------------------------------


class TestGui:
    def test_gui_module_imports_no_backend_intelligence(self):
        """gui.py must not import any backend intelligence package."""
        import inspect

        import sarthi_client.gui as gui

        source = inspect.getsource(gui)
        for forbidden in ("brain", "knowledge", "skills", "hermes", "executor"):
            assert forbidden not in source, f"gui.py must not reference {forbidden}"

    def test_send_disabled_while_sending(self):
        """The Send button is disabled during the send and re-enabled after."""
        try:
            import tkinter as tk

            root = tk.Tk()
            root.withdraw()
        except tk.TclError:
            pytest.skip("tkinter display unavailable")

        from sarthi_client.controller import SendResult
        from sarthi_client.gui import SarthiApp

        class StubController:
            backend_url = "http://stub"

            def send(self, _query):
                # The button is disabled while the controller runs.
                assert app.send_button["state"] == str(tk.DISABLED)
                return SendResult("Done.", "Backend: http://stub")

        app = SarthiApp(controller=StubController())
        app.query_entry.insert(0, "open chrome")
        app.on_send()
        assert app.send_button["state"] == str(tk.NORMAL)
        assert app.response_box.get("1.0", tk.END).strip() == "Done."
        assert app.status_var.get() == "Backend: http://stub"
        app.root.destroy()
        root.destroy()
