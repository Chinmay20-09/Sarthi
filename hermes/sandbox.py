import json
from datetime import UTC, datetime
from pathlib import Path

from .models import Task
from .providers.base import ProviderResponse


class TaskSandbox:
    """Stores task artifacts under sandbox/tasks/<task_id>/."""

    def __init__(self, root: str | Path = "sandbox"):
        self._tasks_dir = Path(root) / "tasks"

    def save(self, task: Task, response: ProviderResponse, duration_ms: float) -> Path:
        """Write prompt.md, response.md, and metadata.json for a task."""
        task_dir = self._tasks_dir / task.id
        task_dir.mkdir(parents=True, exist_ok=True)

        (task_dir / "prompt.md").write_text(task.prompt, encoding="utf-8")
        (task_dir / "response.md").write_text(response.text or response.error, encoding="utf-8")

        metadata = {
            "task_id": task.id,
            "provider": response.provider,
            "model": response.model,
            "status": "success" if response.success else "error",
            "timestamp": datetime.now(UTC).isoformat(),
            "duration_ms": duration_ms,
        }
        (task_dir / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        return task_dir
