#!/usr/bin/env python3
"""
reset_runtime_state.py — Wipe sandbox + conversation history, keep /remember facts.

A maintenance script for starting fresh without losing durable user memory.

    Reset                                       Preserved
    ------------------------------------------  --------------------------
    Hermes sandbox: every task dir,             /remember facts
    index.json (-> {}), failed_tasks.log        (knowledge_memory table)
    in the canonical root AND stray roots       settings, projects,
    (repo-root sandbox/, sandbox_test/ —        connectors, browser
    leftovers of the old cwd-relative path)     profiles, command_history

    conversation_messages (Hermes sessions)
    chat_messages (UI transcript)

Unlike clean_sandbox.py (which keeps failed tasks for review), this wipes
ALL task records regardless of status — the "factory reset" counterpart.

Usage:
    python scripts/reset_runtime_state.py               # dry run (preview)
    python scripts/reset_runtime_state.py --apply       # actually delete
    python scripts/reset_runtime_state.py --apply --force
                                                        # skip running-server
                                                        # check

The script refuses to run while the API server is listening (deleting rows
under a live server races with its writes); --force overrides.
"""

from __future__ import annotations

import json
import shutil
import socket
import sys
from pathlib import Path

# Make Backend/ importable when run as a plain script (same as clean_sandbox.py)
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import API_HOST, API_PORT  # noqa: E402
from database.manager import DatabaseManager  # noqa: E402
from hermes.sandbox import TaskSandbox, resolve_sandbox_root  # noqa: E402

# Stray sandbox stores that predate AD-01 (one canonical sandbox root).
# They are artifacts, not live state — removed entirely when found.
STRAY_ROOTS = (ROOT.parent / "sandbox", ROOT.parent / "sandbox_test")

# Conversation tables cleared by this script. command_history is NOT
# conversation history and is deliberately left alone; knowledge_memory
# (/remember facts) is the whole point of this script — never touched.
CONVERSATION_TABLES = ("conversation_messages", "chat_messages")


def server_is_running() -> bool:
    """True when something accepts connections on the API bind address."""
    try:
        with socket.create_connection((API_HOST, API_PORT), timeout=0.5):
            return True
    except OSError:
        return False


def reset_sandbox_root(root: Path, dry_run: bool) -> dict[str, int]:
    """Wipe every task in one sandbox root; reset index, drop failure log."""
    sandbox = TaskSandbox(str(root))
    stats = {"task_dirs_removed": 0, "index_queries": 0}

    if sandbox.index_path.exists():
        try:
            index = json.loads(sandbox.index_path.read_text(encoding="utf-8"))
            stats["index_queries"] = len(index)
        except (OSError, ValueError):
            stats["index_queries"] = 0

    if sandbox.tasks_dir.is_dir():
        task_dirs = [d for d in sandbox.tasks_dir.iterdir() if d.is_dir()]
        stats["task_dirs_removed"] = len(task_dirs)
        if not dry_run:
            for task_dir in task_dirs:
                shutil.rmtree(task_dir)

    if dry_run:
        return stats

    # Reset the index and clear the failure log; keep the directory
    # structure so the next task run indexes normally.
    root.mkdir(parents=True, exist_ok=True)
    sandbox.tasks_dir.mkdir(exist_ok=True)
    sandbox.index_path.write_text("{}", encoding="utf-8")
    failure_log = root / "failed_tasks.log"
    if failure_log.exists():
        failure_log.unlink()
    return stats


def reset_database(dry_run: bool) -> dict[str, int]:
    """Delete conversation rows; report the /remember facts kept."""
    db = DatabaseManager()
    stats: dict[str, int] = {}

    for table in CONVERSATION_TABLES:
        row = db.fetch_one(f"SELECT COUNT(*) AS n FROM {table}")
        stats[table] = row["n"] if row else 0
        if not dry_run and stats[table]:
            db.execute(f"DELETE FROM {table}")

    row = db.fetch_one("SELECT COUNT(*) AS n FROM knowledge_memory")
    stats["knowledge_memory_kept"] = row["n"] if row else 0
    return stats


def main() -> int:
    args = sys.argv[1:]
    dry_run = "--apply" not in args
    force = "--force" in args

    canonical = resolve_sandbox_root()
    strays = [s for s in STRAY_ROOTS if s.exists() and s.resolve() != canonical]

    print("Sarthi runtime-state reset")
    print(f"  Sandbox (canonical) : {canonical}")
    if strays:
        print(f"  Stray sandbox roots : {', '.join(str(p) for p in strays)}")
    print(f"  Database            : {DatabaseManager().db_path}")
    print(f"  Mode                : {'DRY RUN' if dry_run else 'APPLY'}\n")

    if not force and server_is_running():
        print(
            f"ABORTED: something is listening on {API_HOST}:{API_PORT} "
            "(the API server?). Stop it first, or re-run with --force."
        )
        return 1

    # --- Sandbox --------------------------------------------------------
    total_tasks = 0
    stats = reset_sandbox_root(canonical, dry_run)
    total_tasks += stats["task_dirs_removed"]
    print(
        f"Canonical sandbox: {stats['task_dirs_removed']} task dir(s), "
        f"{stats['index_queries']} index query/ies "
        f"{'[would reset]' if dry_run else 'reset'}"
    )

    for stray in strays:
        size = sum(1 for _ in stray.rglob("*"))
        print(f"Stray root {stray}: {size} item(s) {'[would remove]' if dry_run else 'removed'}")
        if not dry_run:
            shutil.rmtree(stray)

    # --- Conversation history -------------------------------------------
    db_stats = reset_database(dry_run)
    verb = "would delete" if dry_run else "deleted"
    for table in CONVERSATION_TABLES:
        print(f"{table}: {db_stats[table]} row(s) {verb}")

    kept = db_stats["knowledge_memory_kept"]
    print(f"\nknowledge_memory (/remember facts): {kept} row(s) KEPT")
    if kept == 0:
        print("  Note: no /remember facts exist — nothing to preserve.")

    if dry_run:
        print("\nThis was a DRY RUN. Run with --apply to reset for real.")
    else:
        print("\nDone. Sandbox and conversation history are empty; /remember facts intact.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
