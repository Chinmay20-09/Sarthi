from dataclasses import dataclass, field
from uuid import uuid4


@dataclass
class Task:
    prompt: str
    id: str = field(default_factory=lambda: f"task_{uuid4().hex[:6]}")
    task_type: str = "general"
    context: dict | None = None
    # Optional system-level instructions (e.g. the tool-call decision prompt
    # built by the Tool Planner). Sent to the model as a system message when
    # present; the original prompt/fields stay untouched.
    instructions: str | None = None
