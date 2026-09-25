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

The same mapping pattern covers reading: ``read`` uses the pre-existing
``read_file`` action and ``list`` uses ``list_directory`` (both
FILESYSTEM_READ). ``tree`` composes those scoped ``list_directory`` calls
with a bounded depth and entry cap — still no new capability, no shell.

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

# Tree/listing bounds: one command must not walk the whole drive through
# repeated (scoped) list_directory calls.
TREE_MAX_DEPTH = 2
TREE_MAX_ENTRIES = 200
TREE_MAX_DIRS = 40

# A read's message carries the file content; cap it so a huge file cannot
# flood the reply/UI (the full content stays in result.content).
READ_MESSAGE_MAX_CHARS = 4000

# Directory listing preview: names shown in the reply before "… and N more".
_LISTING_PREVIEW = 30


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


def _size_label(size: int) -> str:
    """Human-readable byte size for a listing entry."""
    if size >= 1_048_576:
        return f"{size / 1_048_576:.1f} MB"
    if size >= 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size} B"


def _format_listing(path: str, entries: list[dict[str, Any]]) -> str:
    """One-line directory summary for the reply: dirs first, then files."""
    label = "the current directory" if path in (".", "") else path
    if not entries:
        return f"{label} is empty"
    parts = [f"{e.get('name', '?')}/" for e in entries if e.get("type") == "dir"]
    parts += [
        f"{e.get('name', '?')} ({_size_label(int(e.get('size') or 0))})"
        for e in entries
        if e.get("type") != "dir"
    ]
    shown = ", ".join(parts[:_LISTING_PREVIEW])
    hidden = len(parts) - _LISTING_PREVIEW
    if hidden > 0:
        shown += f" … and {hidden} more"
    return f"{len(entries)} entries in {label}: {shown}"


class TerminalSkill(BaseSkill):
    """
    Terminal-style file commands via the Desktop hand's TERMINAL capability.

    Usage:
        skill = TerminalSkill()
        skill.execute(Intent(action="cd", target="documents"))
        skill.execute(Intent(action="echo", target="hello to notes.txt"))
        skill.execute(Intent(action="create", target="file notes.txt"))
        skill.execute(Intent(action="write", target="hello world to notes.txt"))
        skill.execute(Intent(action="read", target="notes.txt"))
        skill.execute(Intent(action="list", target=""))          # current dir
        skill.execute(Intent(action="list", target="documents"))
        skill.execute(Intent(action="tree", target="projects"))
    """

    name = "terminal"
    description = (
        "Terminal-style file commands (cd, echo, create, write, read, list, tree) "
        "— scoped, structured, no shell"
    )
    version = "1.1.0"

    def execute(self, intent: Intent) -> dict[str, Any]:
        action = (intent.action or "").lower()
        target = (intent.target or "").strip()

        handlers = {
            "cd": self._cd,
            "echo": self._echo,
            "create": self._create,
            "write": self._write,
            "read": self._read,
            "list": self._list,
            "tree": self._tree,
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
        # A bare path ("create testing.txt") gets a fast structured hint —
        # never a silent default to "file" — so a mistyped command fails in
        # milliseconds instead of falling through to the slow model fallback.
        if not target:
            return {
                "success": False,
                "status": "error",
                "handled": True,
                "error": "Create what? Try: create file notes.txt",
            }
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
        else:
            return {
                "success": False,
                "status": "error",
                "handled": True,
                "error": (
                    f"Specify what to create. Try: create file {target} or create directory <name>"
                ),
            }

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

    def _read(self, target: str) -> dict[str, Any]:
        """read <path> — file content via the scoped read_file action.

        The reply message carries the content (capped to
        READ_MESSAGE_MAX_CHARS); the full content stays in the payload.
        """
        if not target:
            return {
                "success": False,
                "status": "error",
                "handled": True,
                "error": "Read what? Try: read notes.txt",
            }
        # "read file x" strips the kind word, mirroring create's shapes.
        if target.lower().startswith("file "):
            target = target[5:].strip()
        # "read" maps onto the existing read_file action (FILESYSTEM_READ);
        # relative paths resolve against the cwd tracked by "cd".
        result = _get_hand().execute("read_file", path=target)
        if not result.get("success"):
            return _from_result(result)
        content = str((result.get("data") or {}).get("content") or "")
        shown = (
            content[:READ_MESSAGE_MAX_CHARS] + "…"
            if len(content) > READ_MESSAGE_MAX_CHARS
            else content
        )
        return {
            "success": True,
            "status": "executed",
            "result": {
                "message": shown or "(empty file)",
                "path": target,
                "content": content,
                "chars": len(content),
            },
        }

    def _list(self, target: str) -> dict[str, Any]:
        """list [path] — one directory level via the scoped list_directory action.

        An empty target lists the tracked working directory.
        """
        path = target.strip()
        # "list" maps onto the existing list_directory action
        # (FILESYSTEM_READ); "." resolves to the cwd tracked by "cd".
        result = _get_hand().execute("list_directory", path=path or ".")
        if not result.get("success"):
            return _from_result(result)
        entries = (result.get("data") or {}).get("entries") or []
        return {
            "success": True,
            "status": "executed",
            "result": {
                "message": _format_listing(path, entries),
                "path": path or ".",
                "entries": entries,
            },
        }

    def _tree(self, target: str) -> dict[str, Any]:
        """tree [path] — bounded recursive listing.

        Composed from scoped list_directory calls (TREE_MAX_DEPTH levels,
        TREE_MAX_ENTRIES / TREE_MAX_DIRS caps) — no new capability, no
        backend recursion, no shell.
        """
        root = target.strip()
        lines: list[str] = []
        totals = {"entries": 0, "dirs": 0}

        def walk(prefix: str, rel: str, depth: int) -> None:
            if depth > TREE_MAX_DEPTH or totals["dirs"] >= TREE_MAX_DIRS:
                return
            if totals["entries"] >= TREE_MAX_ENTRIES:
                lines.append(f"{prefix}… (entry limit reached)")
                return
            result = _get_hand().execute("list_directory", path=rel or ".")
            if not result.get("success"):
                reason = result.get("message") or result.get("error") or "unavailable"
                lines.append(f"{prefix}! {rel or '.'}: {reason}")
                return
            totals["dirs"] += 1
            entries = (result.get("data") or {}).get("entries") or []
            for entry in sorted(entries, key=lambda e: (e.get("type") == "dir", e.get("name", ""))):
                if totals["entries"] >= TREE_MAX_ENTRIES:
                    lines.append(f"{prefix}… (entry limit reached)")
                    return
                name = entry.get("name", "?")
                if entry.get("type") == "dir":
                    lines.append(f"{prefix}{name}/")
                    totals["entries"] += 1
                    child = f"{rel}/{name}" if rel else name
                    walk(prefix + "    ", child, depth + 1)
                else:
                    size = _size_label(int(entry.get("size") or 0))
                    lines.append(f"{prefix}{name} ({size})")
                    totals["entries"] += 1

        walk("", root, 1)
        label = root or "the current directory"
        header = f"Tree of {label} ({totals['entries']} entries):"
        message = header + (("\n" + "\n".join(lines)) if lines else " (empty)")
        return {
            "success": True,
            "status": "executed",
            "result": {
                "message": message,
                "path": root or ".",
                "entries": totals["entries"],
            },
        }
