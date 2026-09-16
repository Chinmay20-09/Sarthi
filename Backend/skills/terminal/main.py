"""
Terminal Skill for Sarthi.

Terminal-style file commands — cd, echo, create, write — executed as
structured, allow-listed Desktop-hand actions. This skill does NOT spawn a
shell or subprocess: every operation goes through the hand's TERMINAL
capability (scoped to the filesystem backend's allowed roots, path
traversal impossible), which keeps the security boundary identical to every
other desktop action.

The ``write`` command maps onto the pre-existing ``write_file`` action
(FILESYSTEM_WRITE capability) with relative paths resolved against the
tracked working directory that ``cd`` maintains — file writing is not
duplicated at the hand level.

State: the working directory lives in the FilesystemBackend
(process-lifetime state, starts at the first allowed root). In remote mode
the cwd lives in the agent's hand, which is exactly where the files are.
"""

import logging
import re
from typing import Any

from brain.intent import Intent
from brain.modes import get_test_mode
from skills.base import BaseSkill

logger = logging.getLogger(__name__)

__all__ = ["TerminalSkill"]

# "echo hello to notes.txt" — everything from " to " onward is the target.
_ECHO_TO_RE = re.compile(r"^(?P<text>.*?)\s+to\s+(?P<path>\S.*)$", re.IGNORECASE)

# "write <content> to <path>" / "create file notes.txt with content <text>".
_WRITE_TO_RE = re.compile(
    r"^(?P<content>.*?)\s+to\s+(?P<path>\S.*?)(?:\s+with\s+content\s+.*)?$",
    re.IGNORECASE,
)
_CREATE_WITH_CONTENT_RE = re.compile(
    r"^(?P<path>\S.*?)(?:\s+with\s+content\s+(?P<content>.+))?$",
    re.IGNORECASE | re.DOTALL,
)


def _get_hand():
    """The configured desktop hand (local in-process or remote over IPC)."""
    from hands.local import get_desktop_hand

    return get_desktop_hand()


def _from_result(result: dict[str, Any]) -> dict[str, Any]:
    """Shape a hand result into the skill result contract.

    The hand carries action payloads under ``data``; they are merged into
    the skill's ``result`` so callers (UI, tools) read ``cwd``/``path``/
    ``bytes_written`` directly.
    """
    if result.get("success"):
        payload = {k: v for k, v in result.items() if k not in ("success", "action", "target")}
        payload.update(result.get("data") or {})
        return {"success": True, "status": "executed", "result": payload}
    return {
        "success": False,
        "status": "error",
        "handled": True,
        "error": result.get("message") or result.get("error") or "The hand refused the action.",
    }


class TerminalSkill(BaseSkill):
    """
    Terminal-style file commands via the Desktop hand's TERMINAL capability.

    Usage:
        skill = TerminalSkill()
        skill.execute(Intent(action="cd", target="documents"))
        skill.execute(Intent(action="echo", target="hello to notes.txt"))
        skill.execute(Intent(action="create", target="file notes.txt"))
        skill.execute(Intent(action="write", target="hello world to notes.txt"))
    """

    name = "terminal"
    description = (
        "Terminal-style file commands (cd, echo, create, write) — scoped, structured, no shell"
    )
    version = "1.0.0"

    def execute(self, intent: Intent) -> dict[str, Any]:
        action = (intent.action or "").lower()
        target = (intent.target or "").strip()

        handlers = {
            "cd": self._cd,
            "echo": self._echo,
            "create": self._create,
            "write": self._write,
        }
        handler = handlers.get(action)
        if handler is None:
            return {
                "success": False,
                "status": "unknown_action",
                "error": f"Terminal does not support action: {action}",
            }

        if get_test_mode():
            logger.info(f"[TEST] Would run terminal {action}: {target}")
            return {
                "success": True,
                "status": "test_mode",
                "result": {"action": action, "target": target, "test_mode": True},
            }

        try:
            return handler(target)
        except Exception as e:  # defensive: mirror other skills' contract
            logger.error(f"Terminal {action} failed: {e}")
            return {"success": False, "status": "error", "handled": True, "error": str(e)}

    # ------------------------------------------------------------------
    # Command implementations (hand delegation only)
    # ------------------------------------------------------------------

    def _cd(self, target: str) -> dict[str, Any]:
        if not target:
            return {
                "success": False,
                "status": "error",
                "handled": True,
                "error": "Change to which directory? Try: cd documents",
            }
        return _from_result(_get_hand().execute("cd", path=target))

    def _echo(self, target: str) -> dict[str, Any]:
        if not target:
            return {
                "success": False,
                "status": "error",
                "handled": True,
                "error": "Echo what? Try: echo hello  (or: echo hello to notes.txt)",
            }
        match = _ECHO_TO_RE.match(target)
        if match:
            return _from_result(
                _get_hand().execute(
                    "echo", text=match.group("text").strip(), path=match.group("path").strip()
                )
            )
        return _from_result(_get_hand().execute("echo", text=target))

    def _create(self, target: str) -> dict[str, Any]:
        # Shapes: "create file notes.txt", "create directory projects",
        #         "create file notes.txt with content hello"
        kind = "file"
        rest = target
        lowered = target.lower()
        if lowered.startswith("file "):
            rest = target[5:]
        elif lowered.startswith("directory "):
            kind = "directory"
            rest = target[10:]
        elif lowered.startswith("dir "):
            kind = "directory"
            rest = target[4:]

        match = _CREATE_WITH_CONTENT_RE.match(rest.strip())
        if match is None or not (match.group("path") or "").strip():
            return {
                "success": False,
                "status": "error",
                "handled": True,
                "error": "Create what? Try: create file notes.txt",
            }
        path = match.group("path").strip()
        content = (match.group("content") or "").strip()

        if kind == "file" and content:
            # create ... with content ... == create then write
            created = _get_hand().execute("create", path=path, type="file")
            if not created.get("success"):
                return _from_result(created)
            written = _get_hand().execute("write_file", path=path, content=content)
            if not written.get("success"):
                return _from_result(written)
            return {
                "success": True,
                "status": "executed",
                "result": {
                    "message": f"Created {path} with content",
                    "path": written.get("path") or path,
                    "type": "file",
                    "bytes_written": written.get("bytes_written"),
                },
            }
        return _from_result(_get_hand().execute("create", path=path, type=kind))

    def _write(self, target: str) -> dict[str, Any]:
        if not target:
            return {
                "success": False,
                "status": "error",
                "handled": True,
                "error": "Write what where? Try: write hello world to notes.txt",
            }
        match = _WRITE_TO_RE.match(target)
        if match is None or not (match.group("path") or "").strip():
            return {
                "success": False,
                "status": "error",
                "handled": True,
                "error": "Could not find the file. Try: write <content> to <file>",
            }
        path = match.group("path").strip()
        content = match.group("content").strip()
        # "write" maps onto the existing write_file action (FILESYSTEM_WRITE);
        # relative paths resolve against the cwd tracked by "cd".
        return _from_result(_get_hand().execute("write_file", path=path, content=content))
