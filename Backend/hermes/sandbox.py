"""
TaskSandbox — the durable record of every Hermes execution, indexed by query.

Hermes is the orchestrator: for each user query it creates a task, executes
it through the provider/tool pipeline, and saves the full story to the
sandbox so it can be referenced later (gap-filling, debugging, retries).

Layout:
    sandbox/
      index.json                  # query -> task records (the query index)
      tasks/<task_id>/
        prompt.md                 # the user query
        response.md               # final response text
        trace.json                # ordered execution steps (optional)
        metadata.json             # provider, model, status, timing, etc.

The query index maps a normalized query string to every task record that
handled it, so "what did we do the last time the user asked X?" is a single
lookup — no scanning, no guessing task ids.
"""

import json
import re
import shutil
from datetime import UTC, datetime
from pathlib import Path

from .models import Task
from .providers.base import ProviderResponse


def normalize_query(query: str) -> str:
    """Normalize a query for stable indexing: lowercase, collapse whitespace."""
    return re.sub(r"\s+", " ", (query or "").strip().lower())


class TaskSandbox:
    """Stores task artifacts under sandbox/tasks/<task_id>/ with a query index."""

    def __init__(self, root: str | Path = "sandbox"):
        self._root = Path(root)
        self._tasks_dir = self._root / "tasks"
        self._index_path = self._root / "index.json"

    # ------------------------------------------------------------------
    # Indexing
    # ------------------------------------------------------------------

    @property
    def index_path(self) -> Path:
        """Path to the query index file (sandbox/index.json)."""
        return self._index_path

    @property
    def tasks_dir(self) -> Path:
        """Directory holding task artifacts (sandbox/tasks)."""
        return self._tasks_dir

    def _load_index(self) -> dict:
        """Load the query index, tolerating a missing/corrupt file."""
        if not self._index_path.exists():
            return {}
        try:
            return json.loads(self._index_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}

    def lookup(self, query: str) -> list[dict]:
        """
        Return every saved task record that handled a normalized query.

        Args:
            query: The user query (any casing/whitespace).

        Returns:
            List of metadata dicts for matching tasks, newest last, or [].
        """
        return self._load_index().get(normalize_query(query), [])

    # ------------------------------------------------------------------
    # Reading (for the sandbox viewer)
    # ------------------------------------------------------------------

    def query_groups(self) -> list[dict]:
        """
        Return every indexed query as {query, records}, newest first.

        Each record is the compact metadata stored in index.json. Groups
        are sorted by their most recent record's timestamp (descending).
        """
        groups = []
        for query, records in self._load_index().items():
            groups.append({"query": query, "records": records})
        groups.sort(
            key=lambda g: max((r.get("timestamp") or "" for r in g["records"]), default=""),
            reverse=True,
        )
        return groups

    def get_task(self, task_id: str) -> dict | None:
        """
        Load a task's full artifacts (prompt, response, trace, metadata).

        Args:
            task_id: The task id (directory name under sandbox/tasks/).

        Returns:
            Dict with prompt, response, trace (list or None), metadata
            (dict or None), or None when the task does not exist.
        """
        task_dir = self._tasks_dir / task_id
        if not task_dir.is_dir():
            return None

        result = {"task_id": task_id}
        result["prompt"] = _read_text(task_dir / "prompt.md")
        result["response"] = _read_text(task_dir / "response.md")
        result["trace"] = _read_json(task_dir / "trace.json")
        result["metadata"] = _read_json(task_dir / "metadata.json")
        return result

    def _index_record(self, task: Task, response: ProviderResponse, duration_ms: float) -> dict:
        """Build the compact record stored in the query index."""
        return {
            "task_id": task.id,
            "prompt": task.prompt,
            "provider": response.provider,
            "model": response.model,
            "status": "success" if response.success else "error",
            "tool_used": response.tool_used,
            "timestamp": datetime.now(UTC).isoformat(),
            "duration_ms": duration_ms,
        }

    # ------------------------------------------------------------------
    # Saving
    # ------------------------------------------------------------------

    def save(
        self,
        task: Task,
        response: ProviderResponse,
        duration_ms: float,
        trace: list[dict] | None = None,
    ) -> Path:
        """
        Write prompt.md, response.md, trace.json, metadata.json for a task
        and append its record to the query index.

        Args:
            task: The executed task (prompt is the query).
            response: The provider response produced for the task.
            duration_ms: Execution time in milliseconds.
            trace: Optional ordered execution steps recorded by the pipeline.

        Returns:
            The task directory that was written.
        """
        task_dir = self._tasks_dir / task.id
        task_dir.mkdir(parents=True, exist_ok=True)

        (task_dir / "prompt.md").write_text(task.prompt, encoding="utf-8")
        (task_dir / "response.md").write_text(response.text or response.error, encoding="utf-8")

        if trace:
            (task_dir / "trace.json").write_text(json.dumps(trace, indent=2), encoding="utf-8")

        metadata = {
            "task_id": task.id,
            "query": task.prompt,
            "provider": response.provider,
            "model": response.model,
            "status": "success" if response.success else "error",
            "tool_used": response.tool_used,
            "timestamp": datetime.now(UTC).isoformat(),
            "duration_ms": duration_ms,
        }
        (task_dir / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")

        # Append to the query index so this task is findable by query.
        index = self._load_index()
        index.setdefault(normalize_query(task.prompt), []).append(
            self._index_record(task, response, duration_ms)
        )
        self._root.mkdir(parents=True, exist_ok=True)
        self._index_path.write_text(json.dumps(index, indent=2), encoding="utf-8")

        return task_dir

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def clean(self, dry_run: bool = False) -> dict:
        """Delete successful task dirs/records, keeping failed ones for review.

        Successful task directories are removed and their index records
        dropped. Queries that end up with no remaining records are removed
        entirely; queries that still hold failures keep only their failed
        records, so the index never points at deleted directories.

        Args:
            dry_run: When True nothing is deleted or rewritten (preview only).

        Returns:
            Dict with deleted_count, removed_task_ids, failed_count,
            failed_records, queries_removed, and queries_remaining.
        """
        index = self._load_index()
        deleted_count = 0
        removed_task_ids: list[str] = []
        failed_records: list[dict] = []
        queries_to_remove: list[str] = []

        for query, records in list(index.items()):
            still_has_failed = False
            kept_records: list[dict] = []

            for rec in records:
                task_id = rec.get("task_id", "")
                if rec.get("status") == "success":
                    # Delete the successful task directory and its index record
                    task_dir = self._tasks_dir / task_id
                    if task_dir.is_dir():
                        removed_task_ids.append(task_id)
                        if not dry_run:
                            shutil.rmtree(task_dir)
                    deleted_count += 1
                else:
                    # Keep failed tasks for review
                    kept_records.append(rec)
                    failed_records.append(rec)
                    still_has_failed = True

            if not still_has_failed:
                queries_to_remove.append(query)
            elif len(kept_records) != len(records):
                # Query still has failures — drop records of deleted successes
                # so the index never references removed directories.
                index[query] = kept_records

        # Remove queries that had no remaining failures
        for query in queries_to_remove:
            del index[query]

        # Rewrite the index with only the remaining (failed) entries
        if not dry_run and (index or deleted_count):
            self._root.mkdir(parents=True, exist_ok=True)
            self._index_path.write_text(json.dumps(index, indent=2), encoding="utf-8")

        return {
            "deleted_count": deleted_count,
            "removed_task_ids": removed_task_ids,
            "failed_count": len(failed_records),
            "failed_records": failed_records,
            "queries_removed": len(queries_to_remove),
            "queries_remaining": len(index),
        }


def _read_text(path: Path) -> str:
    """Read a text file, returning "" when missing/unreadable."""
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def _read_json(path: Path):
    """Read a JSON file, returning None when missing/corrupt."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return None
