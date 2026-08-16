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
            key=lambda g: max(
                (r.get("timestamp") or "" for r in g["records"]), default=""
            ),
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
            (task_dir / "trace.json").write_text(
                json.dumps(trace, indent=2), encoding="utf-8"
            )

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
        (task_dir / "metadata.json").write_text(
            json.dumps(metadata, indent=2), encoding="utf-8"
        )

        # Append to the query index so this task is findable by query.
        index = self._load_index()
        index.setdefault(normalize_query(task.prompt), []).append(
            self._index_record(task, response, duration_ms)
        )
        self._root.mkdir(parents=True, exist_ok=True)
        self._index_path.write_text(json.dumps(index, indent=2), encoding="utf-8")

        return task_dir


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
