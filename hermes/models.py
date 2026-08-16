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
    # Prior conversation turns from the session, oldest first. Each entry is
    # {"role": "user"|"assistant", "content": ...}. Providers inject them
    # between the system message and the current prompt so Hermes remembers
    # earlier turns in the conversation.
    history: list[dict] | None = None
    # Facts the user saved with /remember, formatted as a system prompt block.
    # Providers inject it as an extra system message so the model actually
    # remembers what the user told it to remember.
    memory: str | None = None
