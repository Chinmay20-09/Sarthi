"""Process operations for the Desktop hand (stdlib + psutil).

The callers above this file pass explicit paths and pids; nothing here
resolves names or guesses targets. Path-shaped inputs never go through a
shell: .exe files start via CreateProcess (list-form Popen), everything
else (.lnk shortcuts, etc.) via ShellExecute — mirroring the safe-launch
rules already used by the app launcher skill.
"""

from __future__ import annotations

import logging
import os
import subprocess

import psutil

logger = logging.getLogger(__name__)

__all__ = ["launch_process", "terminate_process", "list_processes", "startfile"]


def launch_process(path: str) -> int:
    """Start an executable by absolute path (CreateProcess, no shell).

    Returns the new process id. Raises on failure so the hand can shape
    the error into a structured result.
    """
    if not path.lower().endswith(".exe"):
        raise ValueError(f"launch_process requires a .exe path, got: {path!r}")
    proc = subprocess.Popen([path])  # noqa: S603 — list-form, shell=False
    logger.debug(f"[Desktop] launch_process pid={proc.pid}")
    return proc.pid


def terminate_process(pid: int) -> bool:
    """Terminate the process with the given pid. True when it was running."""
    proc = psutil.Process(pid)
    if not proc.is_running():
        return False
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except psutil.TimeoutExpired:
        proc.kill()
    return True


def list_processes(limit: int = 200) -> list[dict]:
    """Snapshot of running processes (pid, name, memory in MB), capped."""
    procs: list[dict] = []
    for proc in psutil.process_iter(["pid", "name", "memory_info"]):
        try:
            info = proc.info
            pid = info.get("pid")
            if pid is None:
                continue
            mem = info.get("memory_info")
            procs.append(
                {
                    "pid": pid,
                    "name": info.get("name") or "",
                    "memory_mb": round(mem.rss / (1024 * 1024), 1) if mem else 0.0,
                }
            )
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
        if len(procs) >= limit:
            break
    return procs


def startfile(path: str) -> None:
    """Open a document/shortcut via ShellExecute (no shell parsing)."""
    os.startfile(path)  # noqa: S606 — ShellExecute, no cmd.exe
