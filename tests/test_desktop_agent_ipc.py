"""Brain ↔ Desktop Agent IPC tests.

Locks the contract of the IPC layer introduced to turn the "future
architecture" note in desktop_agent.py into a working transport:

    Brain ──DesktopRequest/HTTP──▶ Desktop Agent ──▶ DesktopHand ──▶ Windows

What is proven here:

  1. DesktopRequest / DesktopResult serialize over the wire (JSON).
  2. The DesktopAgentClient submits requests and shapes transport failures
     (unreachable agent, non-JSON replies) into structured results — never
     exceptions past the boundary.
  3. The agent server validates against the same models and dispatches
     ONLY registered DesktopHand actions (malformed requests, unknown
     actions, wrong argument types, oversized bodies, wrong methods and
     unknown paths are all rejected without touching Windows and without
     crashing the server).
  4. RemoteDesktopHand satisfies the existing Hand contract and delegates
     execution to the agent (Windows backends are faked; no real desktop).
  5. The server runs as a REAL separate process (subprocess) and a real
     client talks to it over TCP — the same-process-shortcut ban in the
     IPC brief does not apply to tests that prove the transport itself;
     the ban is on the *product* faking two machines in one process.
  6. Existing desktop_agent CLI modes (--capabilities/--self-test/--exec)
     keep working.
  7. Architecture: no Windows-only imports in the transport layer; the
     Brain keeps programming against the Hand interface; hands/ still
     imports no brain modules; the single DesktopHand implementation and
     the existing validation gate are untouched.

No test requires a real Windows desktop: OS backends are faked via
monkeypatch, and cross-process tests use the real server with a fake-hand
driver script.
"""

from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path

import pytest
from hands.desktop.hand import DesktopHand

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = REPO_ROOT / "Backend"

# ---------------------------------------------------------------------------
# Models: the wire contract
# ---------------------------------------------------------------------------


class TestWireModels:
    def test_desktop_request_serialization_roundtrip(self):
        from hands.desktop.models import DesktopRequest

        request = DesktopRequest(
            action="open_url", args={"url": "https://example.com"}, target="docs"
        )
        payload = request.model_dump(mode="json")
        assert payload == {
            "action": "open_url",
            "args": {"url": "https://example.com"},
            "target": "docs",
        }
        restored = DesktopRequest.model_validate(payload)
        assert restored == request

    def test_desktop_request_minimal(self):
        from hands.desktop.models import DesktopRequest

        request = DesktopRequest.model_validate({"action": "list_windows"})
        assert request.action == "list_windows"
        assert request.args == {}
        assert request.target is None

    def test_desktop_request_rejects_missing_action(self):
        from hands.desktop.models import DesktopRequest

        with pytest.raises(Exception):
            DesktopRequest.model_validate({"args": {}})

    def test_desktop_request_rejects_non_dict_args(self):
        from hands.desktop.models import DesktopRequest

        with pytest.raises(Exception):
            DesktopRequest.model_validate({"action": "x", "args": [1, 2]})

    def test_desktop_result_serialization_roundtrip(self):
        from hands.desktop.models import DesktopResult

        result = DesktopResult.ok("copy", "done", target="clip", extra=1)
        payload = result.model_dump(mode="json")
        restored = DesktopResult.model_validate(payload)
        assert restored.success is True
        assert restored.data == {"extra": 1}
        assert restored.to_dict()["action"] == "copy"

    def test_desktop_result_fail_shape(self):
        from hands.desktop.models import DesktopResult

        payload = DesktopResult.fail("x", "nope", error="boom").to_dict()
        assert payload["success"] is False
        assert payload["error"] == "boom"
        assert DesktopResult.model_validate(payload).error == "boom"


# ---------------------------------------------------------------------------
# Server logic (in-process handler against a fake hand)
# ---------------------------------------------------------------------------


class _FakeHand:
    """DesktopHand-shaped stand-in: records execute() calls."""

    def __init__(self):
        self.calls: list[tuple[str, dict]] = []
        self._actions = {"open_application": object(), "get_processes": object()}

    def execute(self, action, target=None, **kwargs):
        self.calls.append((action, {"target": target, **kwargs}))
        return {
            "success": True,
            "action": action,
            "target": target,
            "message": f"fake {action}",
            "data": {"pid": 4242},
        }

    def capabilities(self):
        return {"implemented": [{"id": "FAKE", "description": "", "actions": ["x"]}], "planned": []}


def _post_execute(port: int, payload, timeout: float = 5.0):
    import httpx2

    return httpx2.post(f"http://127.0.0.1:{port}/execute", json=payload, timeout=timeout)


def _running_server(fake_hand) -> tuple[int, object]:
    """Start the real handler stack on an ephemeral port with a fake hand."""
    import threading
    from http.server import ThreadingHTTPServer

    sys.path.insert(0, str(BACKEND_DIR))
    from desktop_agent import build_server_handler

    handler = build_server_handler(fake_hand)
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server.server_address[1], server


class TestServerBehaviour:
    def test_valid_request_reaches_the_hand_and_returns_result(self):
        fake = _FakeHand()
        port, server = _running_server(fake)
        try:
            response = _post_execute(
                port,
                {"action": "open_application", "args": {"path": "C:/x.exe"}, "target": "chrome"},
            )
            assert response.status_code == 200
            body = response.json()
            assert body["success"] is True
            assert body["action"] == "open_application"
            assert body["data"]["pid"] == 4242
            assert fake.calls == [("open_application", {"target": "chrome", "path": "C:/x.exe"})]
        finally:
            server.shutdown()

    def test_malformed_body_is_structured_rejection(self):
        fake = _FakeHand()
        port, server = _running_server(fake)
        try:
            body = _post_execute(port, {"no_action": True}).json()
            assert body["success"] is False
            assert body["error"] == "malformed_request"
            assert fake.calls == []
        finally:
            server.shutdown()

    def test_unknown_action_is_rejected_by_validation_gate(self):
        """Rejection comes from the REAL DesktopHand gate (subclass below) —
        the hand's allow-list, reached through the server, nothing else."""
        hand = DesktopHandForServer()
        port, server = _running_server(hand)
        try:
            body = _post_execute(port, {"action": "format_everything"}).json()
            assert body["success"] is False
            assert body["error"] == "unknown_action"
        finally:
            server.shutdown()

    def test_invalid_arguments_are_rejected_by_validation_gate(self):
        hand = DesktopHandForServer()
        port, server = _running_server(hand)
        try:
            body = _post_execute(
                port, {"action": "open_application", "args": {"path": "C:/x.exe", "shell": True}}
            ).json()
            assert body["success"] is False
            assert body["error"] == "invalid_arguments"
        finally:
            server.shutdown()

    def test_wrong_argument_type_rejected(self):
        hand = DesktopHandForServer()
        port, server = _running_server(hand)
        try:
            body = _post_execute(
                port, {"action": "close_application", "args": {"pid": "not-a-pid"}}
            ).json()
            assert body["success"] is False
            assert body["error"] == "invalid_arguments"
        finally:
            server.shutdown()

    def test_oversized_body_rejected(self):
        fake = _FakeHand()
        port, server = _running_server(fake)
        try:
            import httpx2

            response = httpx2.post(
                f"http://127.0.0.1:{port}/execute",
                content=b"x" * 3_000_000,
                headers={"Content-Type": "application/json"},
                timeout=5.0,
            )
            body = response.json()
            assert body["success"] is False
            assert body["error"] == "malformed_request"
        finally:
            server.shutdown()

    def test_wrong_method_and_unknown_path(self):
        fake = _FakeHand()
        port, server = _running_server(fake)
        try:
            import httpx2

            assert httpx2.get(f"http://127.0.0.1:{port}/execute", timeout=5.0).status_code == 405
            assert httpx2.post(f"http://127.0.0.1:{port}/health", timeout=5.0).status_code == 405
            assert httpx2.get(f"http://127.0.0.1:{port}/nope", timeout=5.0).status_code == 404
            assert (
                httpx2.post(f"http://127.0.0.1:{port}/nope", json={}, timeout=5.0).status_code
                == 404
            )
        finally:
            server.shutdown()

    def test_server_survives_repeated_bad_requests(self):
        fake = _FakeHand()
        port, server = _running_server(fake)
        try:
            for payload in (None, {}, {"action": ""}, {"action": 5}, {"action": "x", "args": 1}):
                response = _post_execute(port, payload)
                assert response.status_code == 200
                assert response.json()["success"] is False
            # still alive and serving
            assert _post_execute(port, {"action": "get_processes"}).json()["success"] is True
        finally:
            server.shutdown()

    def test_health_and_capabilities(self):
        fake = _FakeHand()
        port, server = _running_server(fake)
        try:
            import httpx2

            health = httpx2.get(f"http://127.0.0.1:{port}/health", timeout=5.0).json()
            assert health["status"] == "ok"
            assert health["agent"] == "sarthi-desktop-agent"
            assert "open_application" in health["actions"]

            caps = httpx2.get(f"http://127.0.0.1:{port}/capabilities", timeout=5.0).json()
            assert caps["implemented"][0]["id"] == "FAKE"
        finally:
            server.shutdown()


class DesktopHandForServer(DesktopHand):
    """The REAL DesktopHand with OS backends recorded, not performed.

    Subclasses the production hand so the server path exercises the true
    validation gate (allow-list + argument spec). Backends are patched
    out per-call: valid actions return success without touching Windows;
    rejections come from the real gate.
    """

    def __init__(self):
        super().__init__()
        self.calls: list[tuple[str, dict]] = []

    def execute(self, action, target=None, **kwargs):
        import hands.desktop.browser as browser_backend
        import hands.desktop.input as input_backend
        import hands.desktop.processes as process_backend

        self.calls.append((action, {"target": target, **kwargs}))

        def fake_popen(args, **kw):
            return type("P", (), {"pid": 777})()

        saved = (
            process_backend.subprocess.Popen,
            process_backend.psutil.Process,
            input_backend.type_text,
            browser_backend.open_url,
        )
        process_backend.subprocess.Popen = fake_popen
        process_backend.psutil.Process = lambda pid: _FakePsutilProc(pid)
        input_backend.type_text = lambda text: None
        browser_backend.open_url = lambda url: url
        try:
            return super().execute(action, target=target, **kwargs)
        finally:
            (
                process_backend.subprocess.Popen,
                process_backend.psutil.Process,
                input_backend.type_text,
                browser_backend.open_url,
            ) = saved


class _FakePsutilProc:
    def __init__(self, pid):
        self.pid = pid

    def is_running(self):
        return True

    def terminate(self):
        pass

    def wait(self, timeout=None):
        return 0


# ---------------------------------------------------------------------------
# Client (transport) behaviour
# ---------------------------------------------------------------------------


class TestClientTransport:
    def test_client_config_defaults_from_config_module(self, monkeypatch):
        monkeypatch.delenv("SARTHI_DESKTOP_AGENT_HOST", raising=False)
        monkeypatch.delenv("SARTHI_DESKTOP_AGENT_PORT", raising=False)
        monkeypatch.delenv("SARTHI_DESKTOP_AGENT_TIMEOUT", raising=False)
        from hands.transport import DesktopAgentClient

        client = DesktopAgentClient()
        assert client.base_url().startswith("http://")
        assert client.port > 0
        assert client.timeout > 0

    def test_env_overrides(self, monkeypatch):
        monkeypatch.setenv("SARTHI_DESKTOP_AGENT_HOST", "192.168.1.50")
        monkeypatch.setenv("SARTHI_DESKTOP_AGENT_PORT", "9999")
        monkeypatch.setenv("SARTHI_DESKTOP_AGENT_TIMEOUT", "1.5")
        from hands.transport import DesktopAgentClient

        client = DesktopAgentClient()
        assert client.host == "192.168.1.50"
        assert client.port == 9999
        assert client.timeout == 1.5

    def test_execute_round_trip_against_real_server(self):
        fake = _FakeHand()
        port, server = _running_server(fake)
        try:
            from hands.transport import DesktopAgentClient

            client = DesktopAgentClient(host="127.0.0.1", port=port, timeout=5.0)
            result = client.execute("open_application", target="chrome", path="C:/x.exe")
            assert result["success"] is True
            assert result["data"]["pid"] == 4242
            assert fake.calls == [("open_application", {"target": "chrome", "path": "C:/x.exe"})]
        finally:
            server.shutdown()

    def test_execute_request_uses_the_wire_model(self):
        fake = _FakeHand()
        port, server = _running_server(fake)
        try:
            from hands.desktop.models import DesktopRequest
            from hands.transport import DesktopAgentClient

            client = DesktopAgentClient(host="127.0.0.1", port=port, timeout=5.0)
            result = client.execute_request(DesktopRequest(action="get_processes", target="procs"))
            assert result["success"] is True
        finally:
            server.shutdown()

    def test_unreachable_agent_is_structured_not_raised(self):
        from hands.transport import DesktopAgentClient

        client = DesktopAgentClient(host="127.0.0.1", port=1, timeout=0.2)
        result = client.execute("open_url", url="https://example.com")
        assert result["success"] is False
        assert result["error"] == "transport_unavailable"

    def test_bad_json_response_is_structured(self, monkeypatch):
        from hands import transport

        class _BadResponse:
            status_code = 200

            def json(self):
                raise ValueError("not json")

        monkeypatch.setattr(transport.httpx2, "post", lambda *a, **k: _BadResponse())
        client = transport.DesktopAgentClient(host="127.0.0.1", port=1, timeout=0.2)
        result = client.execute("open_url", url="https://example.com")
        assert result["success"] is False
        assert result["error"] == "transport_bad_response"

    def test_http_error_status_is_structured(self, monkeypatch):
        from hands import transport

        class _ErrResponse:
            status_code = 502
            reason_phrase = "Bad Gateway"

        monkeypatch.setattr(transport.httpx2, "post", lambda *a, **k: _ErrResponse())
        client = transport.DesktopAgentClient(host="127.0.0.1", port=1, timeout=0.2)
        result = client.execute("open_url", url="https://example.com")
        assert result["success"] is False
        assert result["error"] == "transport_bad_response"

    def test_timeout_maps_to_transport_unavailable(self, monkeypatch):
        import httpx2 as real_httpx2
        from hands import transport

        def _timeout(*a, **k):
            raise real_httpx2.TimeoutException("timed out")

        monkeypatch.setattr(transport.httpx2, "post", _timeout)
        client = transport.DesktopAgentClient(host="127.0.0.1", port=1, timeout=0.2)
        result = client.execute("open_url", url="https://example.com")
        assert result["success"] is False
        assert result["error"] == "transport_unavailable"

    def test_health_and_capabilities_on_unreachable_agent(self):
        from hands.transport import DesktopAgentClient

        client = DesktopAgentClient(host="127.0.0.1", port=1, timeout=0.2)
        assert client.health() is None
        assert client.capabilities() is None


# ---------------------------------------------------------------------------
# RemoteDesktopHand — the Hand contract over IPC
# ---------------------------------------------------------------------------


class TestRemoteHand:
    def test_satisfies_hand_protocol(self):
        from hands.base import Hand
        from hands.remote import RemoteDesktopHand

        assert isinstance(RemoteDesktopHand(), Hand)

    def test_execute_delegates_to_agent(self):
        fake = _FakeHand()
        port, server = _running_server(fake)
        try:
            from hands.remote import RemoteDesktopHand
            from hands.transport import DesktopAgentClient

            hand = RemoteDesktopHand(DesktopAgentClient(host="127.0.0.1", port=port, timeout=5.0))
            result = hand.execute("open_application", target="chrome", path="C:/x.exe")
            assert result["success"] is True
            assert fake.calls == [("open_application", {"target": "chrome", "path": "C:/x.exe"})]
        finally:
            server.shutdown()

    def test_find_application_process_filters_client_side(self):
        fake = _FakeHand()
        port, server = _running_server(fake)
        try:
            from hands.remote import RemoteDesktopHand
            from hands.transport import DesktopAgentClient

            hand = RemoteDesktopHand(DesktopAgentClient(host="127.0.0.1", port=port, timeout=5.0))
            # _FakeHand returns success with no processes payload → None
            assert hand.find_application_process("chrome.exe") is None
        finally:
            server.shutdown()

    def test_find_application_process_none_when_agent_down(self):
        from hands.remote import RemoteDesktopHand
        from hands.transport import DesktopAgentClient

        hand = RemoteDesktopHand(DesktopAgentClient(host="127.0.0.1", port=1, timeout=0.2))
        assert hand.find_application_process("chrome.exe") is None

    def test_capabilities_unreachable_is_structured_failure(self):
        from hands.remote import RemoteDesktopHand
        from hands.transport import DesktopAgentClient

        hand = RemoteDesktopHand(DesktopAgentClient(host="127.0.0.1", port=1, timeout=0.2))
        report = hand.capabilities()
        assert report["success"] is False
        assert report["error"] == "transport_unavailable"


# ---------------------------------------------------------------------------
# Mode resolution (hands/local.py)
# ---------------------------------------------------------------------------


class TestModeResolution:
    def test_default_mode_is_local_in_process_hand(self, monkeypatch):
        monkeypatch.delenv("SARTHI_DESKTOP_AGENT_MODE", raising=False)
        from hands import local as hands_local
        from hands.desktop import DesktopHand

        hand = hands_local.get_desktop_hand()
        assert isinstance(hand, DesktopHand)

    def test_remote_mode_returns_remote_hand(self, monkeypatch):
        monkeypatch.setenv("SARTHI_DESKTOP_AGENT_MODE", "remote")
        from hands import local as hands_local
        from hands.remote import RemoteDesktopHand

        hand = hands_local.get_desktop_hand()
        assert isinstance(hand, RemoteDesktopHand)

    def test_unknown_mode_falls_back_to_local(self, monkeypatch):
        monkeypatch.setenv("SARTHI_DESKTOP_AGENT_MODE", "banana")
        from hands import local as hands_local
        from hands.desktop import DesktopHand

        assert isinstance(hands_local.get_desktop_hand(), DesktopHand)


# ---------------------------------------------------------------------------
# Real cross-process transport (server in its own OS process)
# ---------------------------------------------------------------------------

_AGENT_DRIVER = '''
import sys, json
sys.path.insert(0, r"{backend}")
from desktop_agent import build_server_handler

class ScriptedHand:
    """Fake hand for transport tests: real validation gate, scripted OS backends."""

    def __init__(self):
        from hands.desktop.hand import DesktopHand
        real = DesktopHand()
        self._actions = dict(real._actions)
        self.real = real
        self.performed = []

    def execute(self, action, target=None, **kwargs):
        # Patched backends: validate + record through the real hand logic.
        import hands.desktop.processes as p
        real = self.real

        def fake_popen(args, **kw):
            self.performed.append(("launch", list(args)))
            return type("P", (), {{"pid": 777}})()

        real_popen = p.subprocess.Popen
        p.subprocess.Popen = fake_popen
        try:
            result = real.execute(action, target=target, **kwargs)
        finally:
            p.subprocess.Popen = real_popen
        return result

    def capabilities(self):
        return self.real.capabilities()

import threading
from http.server import ThreadingHTTPServer

hand = ScriptedHand()
handler = build_server_handler(hand)
server = ThreadingHTTPServer(("127.0.0.1", {port}), handler)
print(json.dumps({{"port": server.server_address[1]}}), flush=True)
server.serve_forever()
'''


@pytest.fixture(scope="class")
def agent_process():
    """One agent process shared by the cross-process tests (module scope
    avoids the deprecated class-scoped instance-method fixture form)."""
    driver = _AGENT_DRIVER.format(backend=str(BACKEND_DIR), port=0)
    proc = subprocess.Popen(
        [sys.executable, "-c", driver],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=str(REPO_ROOT),
    )
    try:
        # The driver prints its ephemeral port as its first line.
        line = proc.stdout.readline()
        info = json.loads(line)
        yield int(info["port"]), proc
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


class TestCrossProcessTransport:
    """The Desktop Agent in a *separate OS process*, client in this one.

    This is the honest version of the two-machine test for CI: two Python
    processes, one TCP socket, real HTTP serialization — only the final
    OS touch (Windows backends) is scripted.
    """

    def test_request_travels_between_processes(self, agent_process):
        port, proc = agent_process
        assert proc.poll() is None, proc.stderr.read() if proc.poll() is not None else "died"

        from hands.transport import DesktopAgentClient

        client = DesktopAgentClient(host="127.0.0.1", port=port, timeout=10.0)
        assert client.health()["status"] == "ok"

        result = client.execute("open_application", target="calc", path="C:/Windows/calc.exe")
        assert result["success"] is True
        assert result["data"]["pid"] == 777

    def test_unknown_action_between_processes(self, agent_process):
        port, _ = agent_process
        from hands.transport import DesktopAgentClient

        client = DesktopAgentClient(host="127.0.0.1", port=port, timeout=10.0)
        result = client.execute("format_everything")
        assert result["success"] is False
        assert result["error"] == "unknown_action"


# ---------------------------------------------------------------------------
# Existing CLI behaviour is preserved
# ---------------------------------------------------------------------------


class TestDesktopAgentCLI:
    def test_capabilities_cli(self, capsys):
        from desktop_agent import main

        assert main(["--capabilities"]) == 0
        report = json.loads(capsys.readouterr().out)
        assert {"implemented", "planned"} <= set(report)

    def test_self_test_cli(self, capsys):
        from desktop_agent import main

        assert main(["--self-test"]) == 0
        # Sequential JSON objects — decode stream-tolerantly (CRLF-safe).
        decoder = json.JSONDecoder()
        out = capsys.readouterr().out.strip()
        objects, idx = [], 0
        while idx < len(out):
            while idx < len(out) and out[idx] in " \t\r\n":
                idx += 1
            if idx >= len(out):
                break
            obj, end = decoder.raw_decode(out, idx)
            objects.append(obj)
            idx = end
        assert len(objects) == 4
        assert all(obj.get("action") for obj in objects)

    def test_exec_cli_valid_action(self, monkeypatch, capsys):
        import hands.desktop.processes as processes_backend

        monkeypatch.setattr(processes_backend, "launch_process", lambda path: 31337)
        from desktop_agent import main

        code = main(["--exec", "open_application", "path=C:/Windows/notepad.exe", "name=Notepad"])
        assert code == 0
        body = json.loads(capsys.readouterr().out)
        assert body["success"] is True

    def test_exec_cli_unknown_action_exits_nonzero(self, capsys):
        from desktop_agent import main

        assert main(["--exec", "no_such_action"]) == 1

    def test_exec_cli_rejects_malformed_pairs(self):
        from desktop_agent import main

        with pytest.raises(SystemExit):
            main(["--exec", "open_url", "url-no-separator"])

    def test_server_flag_needs_the_config_defaults(self, monkeypatch):
        """--server reads host/port from config (no hardcoding at call sites)."""
        from desktop_agent import build_parser

        args = build_parser().parse_args(["--server"])
        assert args.server is True
        assert args.host is None and args.port is None


# ---------------------------------------------------------------------------
# Architecture guards
# ---------------------------------------------------------------------------

HANDS_TRANSPORT_FILES = ("hands/transport.py", "hands/remote.py", "hands/local.py")
WINDOWS_ONLY_MODULES = (
    "pywin32",
    "win32gui",
    "win32api",
    "win32con",
    "pyautogui",
    "pygetwindow",
    "keyboard",
    "pyperclip",
)


class TestArchitectureGuards:
    @pytest.mark.parametrize("relpath", HANDS_TRANSPORT_FILES)
    def test_transport_layer_imports_no_windows_only_modules(self, relpath):
        """The Brain-side transport must import cleanly on Linux/Android.
        Checks actual import statements (AST) and import occurrences in
        source — docstring *mentions* of forbidden modules are fine."""
        source = (BACKEND_DIR / relpath).read_text(encoding="utf-8")
        for module in WINDOWS_ONLY_MODULES:
            assert f"import {module}" not in source, f"{relpath} imports {module}"

        tree = ast.parse(source)
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported |= {a.name.split(".")[0] for a in node.names}
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                imported.add(node.module.split(".")[0])
        forbidden = {
            "win32gui",
            "win32api",
            "win32con",
            "pyautogui",
            "pygetwindow",
            "pyperclip",
            "psutil",
            "keyboard",
        }
        assert imported & forbidden == set(), f"{relpath} imports {imported & forbidden}"

    def test_transport_imports_on_this_interpreter(self):
        """Smoke: the modules import (config-lazy by design)."""
        import hands.local  # noqa: F401
        import hands.remote  # noqa: F401
        import hands.transport  # noqa: F401

    def test_server_has_no_arbitrary_execution_endpoints(self):
        """The agent serves only the three contract endpoints and dispatches
        solely through DesktopHand.execute — no shell/eval/exec path.
        Source-level, ignoring docstring prose (mentions are documentation,
        not code)."""
        source = (BACKEND_DIR / "desktop_agent.py").read_text(encoding="utf-8")
        assert "import subprocess" not in source  # the agent never spawns processes itself
        assert "os.system" not in source
        assert "shell=True" not in source
        tree = ast.parse(source)
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported |= {a.name.split(".")[0] for a in node.names}
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                imported.add(node.module.split(".")[0])
        assert imported & {"subprocess", "pty"} == set()
        # No eval/exec calls anywhere in the AST.
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                assert node.func.id not in {"eval", "exec", "compile", "__import__"}

    def test_server_dispatches_only_through_desktop_hand(self):
        source = (BACKEND_DIR / "desktop_agent.py").read_text(encoding="utf-8")
        # The only execution call is the hand's gate.
        assert "desktop.execute(" in source

    def test_brain_does_not_reach_past_the_hand_interface(self):
        """The executor keeps programming against Hand via hands.local."""
        source = (BACKEND_DIR / "brain" / "executor.py").read_text(encoding="utf-8")
        assert "from hands.local import get_desktop_hand" in source
        assert "hands.transport" not in source  # transport stays below the boundary

    def test_skills_layer_uses_the_mode_seam_not_the_transport(self):
        source = (BACKEND_DIR / "skills" / "app_launcher" / "main.py").read_text(encoding="utf-8")
        assert "hands.transport" not in source
        assert "SARTHI_DESKTOP_AGENT_MODE" in source

    def test_single_desktop_hand_implementation_still_holds(self):
        hand_files = [
            p.name
            for p in (BACKEND_DIR / "hands").rglob("*.py")
            if "class DesktopHand" in p.read_text(encoding="utf-8", errors="replace")
        ]
        assert hand_files == ["hand.py"]

    def test_remote_hand_is_not_a_second_implementation_of_windows_automation(self):
        """RemoteDesktopHand must not contain OS primitives — it forwards."""
        source = (BACKEND_DIR / "hands" / "remote.py").read_text(encoding="utf-8")
        for forbidden in (
            "subprocess",
            "os.system",
            "pyautogui",
            "psutil",
            "startfile",
            "eval(",
            "exec(",
        ):
            assert forbidden not in source


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])
