"""
Desktop agent — standalone entry point for the Desktop hand.

Runs the physical execution layer without the Brain: useful for
diagnostics, and the separately-running process on the Windows machine
in the Brain ↔ Desktop Agent architecture:

    Sarthi Brain  ↔  (IPC: DesktopRequest / DesktopResult)  ↔  Desktop Agent  →  Windows

Modes (exactly one required):

    --capabilities          print the implemented/planned capability report
    --self-test             run read-only actions (active window, clipboard,
                            process list) and print the structured results
    --exec ACTION [k=v ..]  run one explicit action
                            (e.g. ``--exec open_url url=https://example.com``)
    --server [--host H --port P]
                            serve the Desktop hand over HTTP IPC: accept
                            structured DesktopRequest actions, validate
                            them through ``DesktopHand.execute()`` — the
                            same gate as every other caller — and return
                            a structured DesktopResult. Endpoints:
                                POST /execute        one DesktopRequest
                                GET  /health         liveness + agent info
                                GET  /capabilities   the capability report

SECURITY BOUNDARY (explicit):
    The server dispatches ONLY through the DesktopHand action registry
    (hands/desktop/capabilities.py). There is no shell execution, no
    eval/exec, no arbitrary Python, and no arbitrary subprocess endpoint
    — unknown actions and invalid arguments are rejected as structured
    failures without touching Windows. One bad request can never crash
    the server: every handler is wrapped and returns an error result.
    This is a LAN/local development feature, not a public service.

Usage:
    python desktop_agent.py --capabilities
    python desktop_agent.py --self-test
    python desktop_agent.py --exec get_active_window
    python desktop_agent.py --server --host 0.0.0.0 --port 8765
"""

from __future__ import annotations

import argparse
import json
import sys

# ---------------------------------------------------------------------------
# Server mode (stdlib HTTP server — no framework dependency; the agent must
# start on a bare Windows Python with only the hand's own extras installed).
# ---------------------------------------------------------------------------

SERVER_SOFTWARE_NAME = "sarthi-desktop-agent"

# Requests larger than this are rejected (the hand's biggest legal payload —
# write_file content — is capped at 1 MB by the filesystem backend; 2 MB
# leaves generous headroom for JSON overhead). Oversized bodies are drained
# (bounded by MAX_DRAIN_BYTES) before answering, so well-behaved clients get
# the structured rejection instead of a connection reset.
MAX_BODY_BYTES = 2_000_000
MAX_DRAIN_BYTES = 16_000_000


def build_server_handler(desktop):
    """Build the request handler class bound to one DesktopHand.

    Kept as a factory (not a module-level class) so tests can bind a
    fake hand and run the real handler logic in-process.
    """

    from http.server import BaseHTTPRequestHandler  # noqa: E402

    class DesktopAgentHandler(BaseHTTPRequestHandler):
        """One endpoint family: /execute, /health, /capabilities.

        Dispatch rules (the security boundary in code):
          - only these three paths exist; anything else → 404
          - only POST /execute accepts actions, and it forwards the
            parsed DesktopRequest to ``desktop.execute()`` — the hand's
            own validation gate is the only execution path
          - GET on /execute → 405 (actions are never fetched)
        """

        server_version = SERVER_SOFTWARE_NAME

        # -- helpers ---------------------------------------------------

        def _send_json(self, status: int, payload: dict) -> None:
            body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _fail(self, action: str, error: str, message: str) -> None:
            from hands.desktop.models import DesktopResult

            self._send_json(
                200,
                DesktopResult.fail(action=action, message=message, error=error).to_dict(),
            )

        def _parse_body(self) -> dict | None:
            """Read and JSON-parse the request body (None on any problem)."""
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                return None
            if length <= 0:
                return None
            if length > MAX_BODY_BYTES:
                self._drain(length)
                return None
            try:
                raw = self.rfile.read(length)
                parsed = json.loads(raw.decode("utf-8"))
            except (OSError, ValueError, UnicodeDecodeError):
                return None
            return parsed if isinstance(parsed, dict) else None

        def _drain(self, length: int) -> None:
            """Discard a rejected body (bounded) so the client can read the reply."""
            remaining = min(length, MAX_DRAIN_BYTES)
            try:
                while remaining > 0:
                    chunk = self.rfile.read(min(65536, remaining))
                    if not chunk:
                        break
                    remaining -= len(chunk)
            except OSError:
                pass  # client hung up mid-body — nothing left to do

        def _drain_request_body(self) -> None:
            """Discard an unread request body before an error reply.

            ``send_error`` closes the connection without reading the body;
            unread POST data then triggers a TCP reset that can kill the
            client's read of the error response. Draining first keeps the
            structured rejection readable (same bounded-drain policy as
            oversized bodies).
            """
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                return
            if length > 0:
                self._drain(length)

        # -- endpoint: POST /execute -----------------------------------

        def _handle_execute(self) -> None:
            from hands.desktop.models import DesktopRequest, DesktopResult

            body = self._parse_body()
            if body is None:
                self._fail(
                    "",
                    "malformed_request",
                    "Request body must be a JSON object (DesktopRequest).",
                )
                return

            try:
                request = DesktopRequest.model_validate(body)
            except Exception:
                self._fail(
                    str(body.get("action", ""))[:80],
                    "malformed_request",
                    "Request is not a valid DesktopRequest (action/args/target).",
                )
                return

            # The single execution path: the hand's validation gate.
            # DesktopRequest.target is the display label; execute() takes
            # it as a named kwarg and never routes on it.
            result = desktop.execute(request.action, target=request.target, **request.args)

            # Re-materialize through the model so the wire response is
            # always a clean DesktopResult (drops unknown keys).
            payload = DesktopResult.model_validate(result).to_dict()
            self._send_json(200, payload)

        # -- endpoint: GET /health --------------------------------------

        def _handle_health(self) -> None:
            actions = sorted(desktop._actions) if hasattr(desktop, "_actions") else []
            self._send_json(
                200,
                {
                    "status": "ok",
                    "agent": SERVER_SOFTWARE_NAME,
                    "actions": actions,
                    "count": len(actions),
                },
            )

        # -- endpoint: GET /capabilities --------------------------------

        def _handle_capabilities(self) -> None:
            self._send_json(200, desktop.capabilities())

        # -- HTTP plumbing ----------------------------------------------

        def do_GET(self) -> None:  # noqa: N802 (stdlib naming)
            path = self.path.split("?", 1)[0]
            try:
                if path == "/health":
                    self._handle_health()
                elif path == "/capabilities":
                    self._handle_capabilities()
                elif path == "/execute":
                    self.send_error(405, "Actions are submitted with POST /execute")
                else:
                    self.send_error(404, f"Unknown endpoint: {path}")
            except BrokenPipeError:
                pass  # client gave up (timeout) — nothing to answer
            except Exception:
                # One bad handler must never kill the serving loop.
                self.send_error(500, "Internal agent error")

        def do_POST(self) -> None:  # noqa: N802 (stdlib naming)
            path = self.path.split("?", 1)[0]
            try:
                if path == "/execute":
                    self._handle_execute()
                elif path in ("/health", "/capabilities"):
                    self._drain_request_body()
                    self.send_error(405, "Use GET for this endpoint")
                else:
                    self._drain_request_body()
                    self.send_error(404, f"Unknown endpoint: {path}")
            except BrokenPipeError:
                pass
            except Exception:
                self.send_error(500, "Internal agent error")

        def log_message(self, format: str, *args) -> None:  # noqa: A002
            # Compact one-line access log with the stdlib format.
            sys.stderr.write(f"[agent] {self.address_string()} - {format % args}\n")

    return DesktopAgentHandler


def serve(host: str, port: int) -> int:
    """Run the IPC server until interrupted. Returns a process exit code."""
    from http.server import ThreadingHTTPServer

    from hands.desktop import DesktopHand

    desktop = DesktopHand()
    handler = build_server_handler(desktop)
    httpd = ThreadingHTTPServer((host, port), handler)

    actions = sorted(desktop._actions)
    print(
        f"[agent] {SERVER_SOFTWARE_NAME} serving DesktopHand "
        f"({len(actions)} actions) on http://{host}:{port}",
        flush=True,
    )
    print("[agent] endpoints: POST /execute, GET /health, GET /capabilities", flush=True)
    print("[agent] security: dispatches only registered DesktopHand actions", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("[agent] shutting down", flush=True)
    finally:
        httpd.server_close()
    return 0


def _parse_exec_args(pairs: list[str]) -> dict:
    """Parse key=value pairs into action kwargs (values stay strings)."""
    kwargs: dict = {}
    for pair in pairs or []:
        if "=" not in pair:
            raise SystemExit(f"Invalid action argument (expected key=value): {pair!r}")
        key, value = pair.split("=", 1)
        kwargs[key] = value
    return kwargs


def build_parser() -> argparse.ArgumentParser:
    """CLI surface (argparse wiring split out for testability)."""
    parser = argparse.ArgumentParser(description="Sarthi Desktop hand — standalone agent")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--capabilities", action="store_true", help="print the capability report")
    group.add_argument("--self-test", action="store_true", help="run read-only actions")
    group.add_argument(
        "--exec",
        nargs="+",
        metavar=("ACTION", "KEY=VALUE"),
        help="run one explicit action with key=value arguments",
    )
    group.add_argument(
        "--server",
        action="store_true",
        help="serve the Desktop hand over HTTP IPC (POST /execute, GET /health, GET /capabilities)",
    )
    parser.add_argument("--host", default=None, help="server bind host (default: config/env)")
    parser.add_argument(
        "--port", type=int, default=None, help="server bind port (default: config/env)"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    # --server does not need the hand at parse time; serve() builds it.
    if args.server:
        from config import DESKTOP_AGENT_HOST, DESKTOP_AGENT_PORT

        host = args.host or _env_host() or DESKTOP_AGENT_HOST
        port = args.port or _env_port() or DESKTOP_AGENT_PORT
        return serve(host, port)

    # Import here so --help stays fast and dependency-free.
    from hands.desktop import DesktopHand

    desktop = DesktopHand()

    if args.capabilities:
        print(json.dumps(desktop.capabilities(), indent=2))
        return 0

    if args.self_test:
        checks = [
            ("get_active_window", {}),
            ("list_windows", {}),
            ("get_processes", {}),
            ("read_clipboard", {}),
        ]
        for action, kwargs in checks:
            result = desktop.execute(action, **kwargs)
            print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
        return 0

    action = args.exec[0]
    kwargs = _parse_exec_args(args.exec[1:])
    result = desktop.execute(action, **kwargs)
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    return 0 if result.get("success") else 1


def _env_host() -> str:
    import os

    return os.environ.get("SARTHI_DESKTOP_AGENT_HOST", "").strip()


def _env_port() -> int | None:
    import os

    raw = os.environ.get("SARTHI_DESKTOP_AGENT_PORT", "").strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


if __name__ == "__main__":
    sys.exit(main())
