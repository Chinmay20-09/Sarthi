"""
DesktopHand — Sarthi's physical execution layer for the local Windows desktop.

The hand executes explicit, validated operations. It never reasons: the
Brain decides what should happen, the hand performs it and reports a
structured result. Every call is logged and every outcome is a
``DesktopResult`` — failures are returned, never hidden and never raised
past the boundary for expected operational errors.

    Brain → Executor / Skill → DesktopHand → Windows

Safety model:
    - Actions are allow-listed per capability (hands/desktop/capabilities.py).
    - Arguments are validated against each action's spec; unknown
      arguments and wrong types are rejected before anything runs.
    - No shell execution, no arbitrary code execution, no coordinate
      guessing — callers pass explicit targets (paths, pids, keys, urls).
    - Filesystem operations are scoped to the configured roots.
"""

from __future__ import annotations

import logging
from typing import Any

from hands.desktop import browser as browser_backend
from hands.desktop import input as input_backend
from hands.desktop import processes as process_backend
from hands.desktop import windows as window_backend
from hands.desktop.capabilities import PLANNED_CAPABILITIES, action_spec, describe_capabilities
from hands.desktop.filesystem import FilesystemBackend, FilesystemScopeError
from hands.desktop.models import DesktopResult

logger = logging.getLogger(__name__)

__all__ = ["DesktopHand", "get_desktop_hand"]


class DesktopHand:
    """Deterministic executor for validated desktop operations."""

    def __init__(
        self,
        filesystem: FilesystemBackend | None = None,
        allowed_roots: list[str] | None = None,
    ):
        """Create a hand. ``allowed_roots`` scopes filesystem actions."""
        self.fs = filesystem or FilesystemBackend(allowed_roots=allowed_roots)
        # Action name -> bound implementation. Populated once; static by design.
        self._actions: dict[str, Any] = {
            "open_application": self._open_application,
            "close_application": self._close_application,
            "open_url": self._open_url,
            "type_text": self._type_text,
            "press_key": self._press_key,
            "hotkey": self._hotkey,
            "move_mouse": self._move_mouse,
            "click": self._click,
            "copy": self._copy,
            "paste": self._paste,
            "read_clipboard": self._read_clipboard,
            "list_windows": self._list_windows,
            "get_active_window": self._get_active_window,
            "get_processes": self._get_processes,
            "launch_process": self._launch_process,
            "terminate_process": self._terminate_process,
            "read_file": self._read_file,
            "write_file": self._write_file,
            "delete_file": self._delete_file,
            "list_directory": self._list_directory,
        }

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def execute(self, action: str, target: str | None = None, **kwargs: Any) -> dict[str, Any]:
        """Run one validated Desktop action and return a structured result.

        Args:
            action: Registered action name (see capabilities.py).
            target: Optional human-facing target, carried into the result
                for logging/display (e.g. "chrome"); never used for
                routing — backends receive explicit arguments only.
            **kwargs: Action arguments, validated against the action spec.

        Returns:
            DesktopResult-shaped dict: success, action, target, message,
            error (on failure), data (action-specific payload).
        """
        # 1. Action must be registered.
        impl = self._actions.get(action)
        if impl is None:
            return DesktopResult.fail(
                action=action,
                message=f"Unknown desktop action: {action!r}",
                error="unknown_action",
            ).to_dict()

        # 2. Arguments must match the capability spec. ``target`` is a
        #    display field and never reaches a backend.
        args = dict(kwargs)
        error = self._validate_args(action, args)
        if error:
            return DesktopResult.fail(
                action=action,
                message=f"Invalid arguments for {action}: {error}",
                target=target,
                error="invalid_arguments",
            ).to_dict()

        # 3. Execute and shape every outcome into a structured result.
        logger.info(f"[Desktop] action={action} target={target or '-'} status=start")
        try:
            outcome = impl(**args)
        except FileNotFoundError as e:
            return self._failure(action, target, str(e), "not_found")
        except FilesystemScopeError as e:
            return self._failure(action, target, str(e), "outside_scope")
        except (RuntimeError, ValueError, OSError) as e:
            return self._failure(action, target, str(e), "execution_failed")
        except Exception as e:  # defensive: never leak a raw traceback
            logger.exception(f"[Desktop] unexpected failure in {action}")
            return self._failure(action, target, f"Unexpected failure: {e}", "unexpected_error")

        logger.info(f"[Desktop] action={action} status=success")
        return self._normalize(action, target, outcome)

    def capabilities(self) -> dict[str, Any]:
        """Implemented capabilities plus the planned-but-unregistered list."""
        return {
            "implemented": describe_capabilities(),
            "planned": list(PLANNED_CAPABILITIES),
        }

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_args(action: str, args: dict[str, Any]) -> str | None:
        """Check args against the capability spec. Returns an error or None."""
        spec = action_spec(action)
        for name, value in args.items():
            if name not in spec:
                return f"unexpected argument {name!r}"
        for name, rule in spec.items():
            if rule == "required":
                if name not in args or args[name] is None:
                    return f"missing required argument {name!r}"
            elif isinstance(rule, tuple) and len(rule) == 2:
                kind, param = rule
                if kind == "required":
                    if name not in args or args[name] is None:
                        return f"missing required argument {name!r}"
                    if isinstance(param, type) and not isinstance(args[name], param):
                        return f"argument {name!r} must be {param.__name__}"
                    if isinstance(param, tuple) and not isinstance(args[name], param):
                        return f"argument {name!r} must be one of type {param}"
                    if param is str and isinstance(args[name], str) and not args[name].strip():
                        return f"argument {name!r} must be a non-empty string"
                elif kind == "optional":
                    args.setdefault(name, param)
                elif kind == "choices" and args.get(name) not in param:
                    return f"argument {name!r} must be one of {sorted(param)}"
        return None

    # ------------------------------------------------------------------
    # Result shaping
    # ------------------------------------------------------------------

    @staticmethod
    def _failure(action: str, target: str | None, message: str, error: str) -> dict[str, Any]:
        logger.info(f"[Desktop] action={action} status=failure error={error}")
        return DesktopResult.fail(
            action=action, message=message, target=target, error=error
        ).to_dict()

    @staticmethod
    def _normalize(action: str, target: str | None, outcome: Any) -> dict[str, Any]:
        """Turn a backend return value into a DesktopResult dict.

        Backends return either a dict (``message`` plus payload keys) or
        a DesktopResult (for actions that decide their own failure, like
        get_active_window).
        """
        if isinstance(outcome, DesktopResult):
            result = outcome
            result.action = action
            if target is not None:
                result.target = target
            return result.to_dict()
        if isinstance(outcome, dict):
            success = outcome.pop("success", True)
            message = outcome.pop("message", f"{action} completed")
            if success:
                return DesktopResult.ok(
                    action=action, message=message, target=target, **outcome
                ).to_dict()
            return DesktopResult.fail(
                action=action, message=message, target=target, error="not_found", **outcome
            ).to_dict()
        return DesktopResult.ok(
            action=action, message=f"{action} completed", target=target
        ).to_dict()

    # ------------------------------------------------------------------
    # Application launch / close
    # ------------------------------------------------------------------

    def _open_application(self, path: str, name: str | None = None) -> dict[str, Any]:
        """Launch an application by explicit path (resolution happens upstream)."""
        pid = process_backend.launch_process(path)
        return {"message": f"Application launched: {name or path}", "pid": pid, "path": path}

    def _close_application(self, pid: int, name: str | None = None) -> dict[str, Any]:
        """Close an application by explicit process id."""
        existed = process_backend.terminate_process(pid)
        label = name or str(pid)
        if not existed:
            return {"success": False, "message": f"No running process with pid {pid} ({label})"}
        return {"message": f"Application closed: {label}"}

    # ------------------------------------------------------------------
    # Browser
    # ------------------------------------------------------------------

    def _open_url(self, url: str) -> dict[str, Any]:
        opened = browser_backend.open_url(url)
        return {"message": f"URL opened: {opened}", "url": opened}

    # ------------------------------------------------------------------
    # Keyboard / mouse
    # ------------------------------------------------------------------

    def _type_text(self, text: str) -> dict[str, Any]:
        input_backend.type_text(text)
        return {"message": f"Typed {len(text)} character(s)"}

    def _press_key(self, key: str) -> dict[str, Any]:
        input_backend.press_key(key)
        return {"message": f"Key pressed: {key}"}

    def _hotkey(self, keys: list[str]) -> dict[str, Any]:
        input_backend.hotkey(keys)
        return {"message": f"Hotkey pressed: {'+'.join(keys)}"}

    def _move_mouse(self, x: int, y: int) -> dict[str, Any]:
        input_backend.move_mouse(x, y)
        return {"message": f"Mouse moved to ({x}, {y})"}

    def _click(self, x: int, y: int) -> dict[str, Any]:
        input_backend.click(x, y)
        return {"message": f"Clicked ({x}, {y})"}

    # ------------------------------------------------------------------
    # Clipboard
    # ------------------------------------------------------------------

    def _copy(self, text: str) -> dict[str, Any]:
        input_backend.copy_to_clipboard(text)
        return {"message": f"Copied {len(text)} character(s) to clipboard"}

    def _paste(self) -> dict[str, Any]:
        input_backend.paste()
        return {"message": "Pasted clipboard into foreground window"}

    def _read_clipboard(self) -> dict[str, Any]:
        text = input_backend.read_clipboard()
        return {"message": "Clipboard read", "text": text}

    # ------------------------------------------------------------------
    # Windows
    # ------------------------------------------------------------------

    def _list_windows(self) -> dict[str, Any]:
        wins = window_backend.list_windows()
        return {"message": f"{len(wins)} window(s) found", "windows": wins}

    def _get_active_window(self) -> dict[str, Any]:
        win = window_backend.get_active_window()
        if win is None:
            return DesktopResult.fail(
                action="get_active_window",
                message="No active window available",
                error="unavailable",
            )
        return {"message": f"Active window: {win.get('title', '')}", "window": win}

    # ------------------------------------------------------------------
    # Processes
    # ------------------------------------------------------------------

    def _get_processes(self) -> dict[str, Any]:
        procs = process_backend.list_processes()
        return {"message": f"{len(procs)} process(es) found", "processes": procs}

    def _launch_process(self, path: str) -> dict[str, Any]:
        pid = process_backend.launch_process(path)
        return {"message": f"Process launched: {path}", "pid": pid, "path": path}

    def _terminate_process(self, pid: int) -> dict[str, Any]:
        existed = process_backend.terminate_process(pid)
        if not existed:
            return {"success": False, "message": f"No running process with pid {pid}"}
        return {"message": f"Process {pid} terminated"}

    # ------------------------------------------------------------------
    # Filesystem (scoped)
    # ------------------------------------------------------------------

    def _read_file(self, path: str) -> dict[str, Any]:
        content = self.fs.read_file(path)
        return {"message": f"Read {len(content)} character(s)", "content": content}

    def _write_file(self, path: str, content: str) -> dict[str, Any]:
        written = self.fs.write_file(path, content)
        return {"message": f"Wrote {written} byte(s)", "bytes_written": written}

    def _delete_file(self, path: str) -> dict[str, Any]:
        deleted = self.fs.delete_file(path)
        if not deleted:
            return {"success": False, "message": f"File not found: {path}"}
        return {"message": f"Deleted {path}"}

    def _list_directory(self, path: str) -> dict[str, Any]:
        entries = self.fs.list_directory(path)
        return {"message": f"{len(entries)} entries", "entries": entries}

    # ------------------------------------------------------------------
    # Brain-facing lookup helper (read-only; no reasoning lives here)
    # ------------------------------------------------------------------

    def find_application_process(self, exe_name: str) -> list[dict[str, Any]] | None:
        """Running processes whose executable name matches ``exe_name``.

        Read-only bridge used by the executor's close flow: the Brain
        resolves a friendly name to an executable via the knowledge layer,
        then asks the hand which running processes match. Returns None
        when nothing matches; callers then terminate by explicit pid.
        """
        wanted = (exe_name or "").lower()
        if not wanted:
            return None
        matches = [
            proc
            for proc in process_backend.list_processes(limit=1000)
            if (proc.get("name") or "").lower() == wanted
        ]
        return matches or None


# ----------------------------------------------------------------------
# Process-wide singleton (used by the executor's built-in close handler)
# ----------------------------------------------------------------------

_hand: DesktopHand | None = None


def get_desktop_hand() -> DesktopHand:
    """Return the shared DesktopHand instance (created on first use)."""
    global _hand
    if _hand is None:
        _hand = DesktopHand()
    return _hand
