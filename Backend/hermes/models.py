from dataclasses import dataclass, field, replace
from typing import Any
from uuid import uuid4


@dataclass
class Task:
    """One Hermes execution unit (chat turn, tool task, ...).

    ``Task`` is the *orchestration* record: it carries identity (id,
    task_type), the user prompt, and any context Hermes needs to route,
    trace, and persist the execution to the sandbox.

    Provider-neutral model calls are derived from it with
    ``Task.to_request()`` — providers never see ``Task`` itself.
    """

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

    def to_request(self) -> "ModelRequest":
        """Build the provider-neutral request for this task's model call.

        Execution metadata (id, task_type, context) deliberately stays on
        the Task — the model only needs the prompt, instructions, session
        history, and memory block.
        """
        return ModelRequest(
            prompt=self.prompt,
            instructions=self.instructions,
            history=self.history,
            memory=self.memory,
        )


@dataclass
class ModelRequest:
    """Provider-neutral request — the ONLY object Hermes hands to providers.

    Hermes core builds a ModelRequest for every model call. Provider
    adapters convert it into their own wire format (Ollama /api/chat,
    OpenAI chat-completions, ...); provider-specific request objects never
    leave the adapter.

    Fields:
        prompt: The user message / primary instruction.
        instructions: Optional system-level instructions (tool decision
            prompt, persona, ...). Sent as a system message when present.
        history: Prior {"role", "content"} turns, oldest first.
        memory: Optional /remember facts, injected as a system message.
        tools: Registered tool descriptors (name/description/parameters)
            Hermes may reference in this call. Adapters that support native
            tool schemas may translate them; the prompt-based tool protocol
            already embeds them in ``instructions``.
        structured_output: True when the caller REQUIRES a JSON object back.
            Adapters whose model capability ``structured_output`` is true
            enforce it (e.g. Ollama ``format=json``); others ignore the flag
            and Hermes' own validation/parsing fallback applies.
        images: Optional image inputs (URLs or base64 data). Sent only when
            the model capability ``vision`` is true.
        temperature: Optional generation temperature override.
    """

    prompt: str
    instructions: str | None = None
    history: list[dict] | None = None
    memory: str | None = None
    tools: list[dict[str, Any]] | None = None
    structured_output: bool = False
    images: list[str] = field(default_factory=list)
    temperature: float | None = None

    def with_instructions(self, instructions: str) -> "ModelRequest":
        """Copy with new system instructions (used by the Tool Planner)."""
        return replace(self, instructions=instructions)

    def without_tools(self) -> "ModelRequest":
        """Copy that does not advertise tools (plain conversational calls)."""
        return replace(self, tools=None)
