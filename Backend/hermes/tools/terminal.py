"""
terminal tool — terminal-style file operations (cd, echo, create, write)
through Sarthi's existing TerminalSkill, which delegates to the Desktop
hand's scoped TERMINAL capability.

This tool does NOT spawn a second executor and does NOT run a shell: it
delegates to the exact skill the Brain's executor uses, and every operation
is a structured, allow-listed hand action (no subprocess, no eval, no
arbitrary code execution).
"""

import logging
from typing import Any

from brain.intent import Intent
from skills.terminal.main import TerminalSkill

from .base import BaseTool, ToolResult

logger = logging.getLogger(__name__)


class TerminalTool(BaseTool):
    """Run one terminal-style file operation (cd / echo / create / write /
    read / list / tree)."""

    name = "terminal"
    description = (
        "Terminal-style file operations on the user's machine: cd (change "
        "directory), echo (print text or write it to a file), create (new "
        "file or directory), write (write text to a file), read (read a "
        "file's content), list (list a directory), tree (recursive listing). "
        "Scoped to allowed roots; no shell commands."
    )
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "One of: cd, echo, create, write, read, list, tree.",
            },
            "target": {
                "type": "string",
                "description": (
                    "Operation argument. cd: the directory path. echo: the "
                    "text, optionally 'to <file>'. create: '[file|directory] "
                    "<path>'. write: '<text> to <file>'. read: the file path. "
                    "list/tree: the directory path (empty = current)."
                ),
            },
        },
        "required": ["action", "target"],
    }

    def execute(self, arguments: dict[str, Any]) -> ToolResult:
        action = str(arguments.get("action") or "").strip().lower()
        target = str(arguments.get("target") or "").strip()

        if action not in ("cd", "echo", "create", "write", "read", "list", "tree"):
            return ToolResult(
                success=False,
                tool=self.name,
                error=(
                    f"Unknown terminal action '{action}'. "
                    "Use cd, echo, create, write, read, list or tree."
                ),
                invalid=True,
            )
        if not target and action not in ("list", "tree"):
            # list/tree legitimately take no target: they list the tracked
            # working directory. Everything else needs an explicit target.
            return ToolResult(
                success=False,
                tool=self.name,
                error="No target was specified for the terminal operation.",
                invalid=True,
            )

        try:
            result = TerminalSkill().execute(Intent(action=action, target=target))
        except Exception as e:  # never leak internals upward
            logger.error("terminal failed unexpectedly (%s %s): %s", action, target, e)
            return ToolResult(
                success=False,
                tool=self.name,
                error="The terminal operation could not be completed.",
            )

        if result.get("success"):
            info = result.get("result") or {}
            summary = info.get("message") or f"{action} completed"
            payload = {
                k: v
                for k, v in info.items()
                if k
                in ("cwd", "path", "bytes_written", "text", "type", "content", "entries", "chars")
            }
            return ToolResult(
                success=True,
                tool=self.name,
                result=str(summary),
                data={"action": action, **payload} if payload else {"action": action},
            )

        if result.get("status") == "test_mode":
            return ToolResult(
                success=True,
                tool=self.name,
                result=f"[test mode] would run: {action} {target}",
                data={"action": action, "test_mode": True},
            )
        return ToolResult(
            success=False,
            tool=self.name,
            error=result.get("error") or f"The terminal operation '{action}' failed.",
        )
