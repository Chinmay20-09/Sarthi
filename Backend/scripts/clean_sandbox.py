#!/usr/bin/env python3
"""
clean_sandbox.py — Clean up the Hermes sandbox.

Deletes successful task directories and keeps failed ones.
Logs failed tasks to sandbox/failed_tasks.log for review.

The clean/prune logic itself lives in TaskSandbox.clean() (hermes/sandbox.py),
shared with the in-app "/clean" slash command — this script only adds the
CLI, the preview output, and the failed-task log.

Usage:
    python scripts/clean_sandbox.py              # dry run (preview only)
    python scripts/clean_sandbox.py --apply      # actually delete
    python scripts/clean_sandbox.py --apply --log  # delete + write log
"""

import sys
from datetime import datetime
from pathlib import Path

# Make the project root importable when run as a plain script
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from hermes.sandbox import TaskSandbox  # noqa: E402

SANDBOX_ROOT = ROOT / "sandbox"
LOG_PATH = SANDBOX_ROOT / "failed_tasks.log"


def log_failed(failed_records: list[dict]) -> None:
    """Append failed task details to the log file."""
    if not failed_records:
        return
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(f"\n{'=' * 60}\n")
        f.write(f"Cleanup run: {datetime.now().isoformat()}\n")
        f.write(f"{'=' * 60}\n")
        for rec in failed_records:
            f.write(f"\n  Task ID : {rec.get('task_id', '?')}\n")
            f.write(f"  Prompt  : {rec.get('prompt', '?')}\n")
            f.write(f"  Provider: {rec.get('provider', '?')}\n")
            f.write(f"  Model   : {rec.get('model', '?')}\n")
            f.write(f"  Status  : {rec.get('status', '?')}\n")
            f.write(f"  Time    : {rec.get('timestamp', '?')}\n")
            f.write(f"  Duration: {rec.get('duration_ms', 0):.0f}ms\n")
            f.write(f"  Tool    : {rec.get('tool_used') or 'none'}\n")
            f.write(f"  {'-' * 40}\n")
        f.write(f"\nTotal failed: {len(failed_records)}\n")


def clean(dry_run: bool = True, write_log: bool = False) -> None:
    sandbox = TaskSandbox(SANDBOX_ROOT)
    result = sandbox.clean(dry_run=dry_run)

    deleted_count = result["deleted_count"]
    failed_records = result["failed_records"]

    if not deleted_count and not failed_records and not result["queries_remaining"]:
        print("No index.json found or index is empty. Nothing to clean.")
        return

    # Report each removed (or would-be-removed) successful task directory
    for task_id in result["removed_task_ids"]:
        task_dir = sandbox.tasks_dir / task_id
        if dry_run:
            print(f"  [DRY RUN] Would delete: {task_dir}")
        else:
            print(f"  Deleted: {task_dir}")

    # Report the failed tasks that were kept
    for rec in failed_records:
        print(f"  Kept (failed): {rec.get('task_id', '?')} — {rec.get('prompt', '?')[:60]}")

    print(f"\n{'=' * 50}")
    print(f"  Successful tasks deleted : {deleted_count}")
    print(f"  Failed tasks kept        : {result['failed_count']}")
    print(f"  Queries fully cleaned    : {result['queries_removed']}")
    print(f"  Queries with failures    : {result['queries_remaining']}")
    print(f"{'=' * 50}")

    if dry_run:
        print("\n  This was a DRY RUN. No files were modified.")
        print("  Run with --apply to actually delete files.")
    else:
        print(f"\n  Updated: {sandbox.index_path}")

    if write_log and failed_records:
        log_failed(failed_records)
        print(f"  Failed tasks logged to: {LOG_PATH}")
    elif failed_records:
        print(f"\n  Tip: run with --log to save failed tasks to {LOG_PATH}")


def main() -> None:
    args = sys.argv[1:]
    dry_run = "--apply" not in args
    write_log = "--log" in args

    print(f"Sandbox: {SANDBOX_ROOT}")
    print(f"Mode: {'DRY RUN' if dry_run else 'APPLY'}\n")

    clean(dry_run=dry_run, write_log=write_log)


if __name__ == "__main__":
    main()
