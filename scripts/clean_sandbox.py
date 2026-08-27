#!/usr/bin/env python3
"""
clean_sandbox.py — Clean up the Hermes sandbox.

Deletes successful task directories and keeps failed ones.
Logs failed tasks to sandbox/failed_tasks.log for review.

Usage:
    python scripts/clean_sandbox.py              # dry run (preview only)
    python scripts/clean_sandbox.py --apply      # actually delete
    python scripts/clean_sandbox.py --apply --log  # delete + write log
"""

import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

SANDBOX_ROOT = Path(__file__).resolve().parents[1] / "sandbox"
INDEX_PATH = SANDBOX_ROOT / "index.json"
TASKS_DIR = SANDBOX_ROOT / "tasks"
LOG_PATH = SANDBOX_ROOT / "failed_tasks.log"


def load_index() -> dict:
    if not INDEX_PATH.exists():
        return {}
    try:
        return json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def write_index(index: dict) -> None:
    INDEX_PATH.write_text(json.dumps(index, indent=2), encoding="utf-8")


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
    index = load_index()
    if not index:
        print("No index.json found or index is empty. Nothing to clean.")
        return

    deleted_count = 0
    kept_count = 0
    failed_records: list[dict] = []
    queries_to_remove: list[str] = []

    for query, records in index.items():
        still_has_failed = False

        for rec in records:
            task_id = rec.get("task_id", "")
            status = rec.get("status", "")

            if status == "success":
                # Delete successful task directory
                task_dir = TASKS_DIR / task_id
                if task_dir.is_dir():
                    if dry_run:
                        print(f"  [DRY RUN] Would delete: {task_dir}")
                    else:
                        shutil.rmtree(task_dir)
                        print(f"  Deleted: {task_dir}")
                deleted_count += 1
            else:
                # Keep failed tasks
                kept_count += 1
                failed_records.append(rec)
                still_has_failed = True
                print(f"  Kept (failed): {task_id} — {rec.get('prompt', '?')[:60]}")

        if not still_has_failed:
            queries_to_remove.append(query)

    # Remove queries that had no failed tasks
    for query in queries_to_remove:
        del index[query]

    print(f"\n{'=' * 50}")
    print(f"  Successful tasks deleted : {deleted_count}")
    print(f"  Failed tasks kept        : {kept_count}")
    print(f"  Queries fully cleaned    : {len(queries_to_remove)}")
    print(f"  Queries with failures    : {len(index)}")
    print(f"{'=' * 50}")

    if dry_run:
        print("\n  This was a DRY RUN. No files were modified.")
        print("  Run with --apply to actually delete files.")
    else:
        write_index(index)
        print(f"\n  Updated: {INDEX_PATH}")

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
