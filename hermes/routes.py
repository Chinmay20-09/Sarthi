"""Hermes chat endpoint for local AI integration."""

import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from hermes.conversation import DEFAULT_SESSION, get_conversation_store
from hermes.models import Task
from hermes.orchestrator import HermesOrchestrator
from hermes.sandbox import TaskSandbox
from hermes.service import get_orchestrator as _service_get_orchestrator
from hermes.service import get_sandbox as _service_get_sandbox
from knowledge.memory import build_memory_prompt

router = APIRouter(prefix="/hermes", tags=["hermes"])

# Kept for test compatibility — the real singletons live in hermes.service
_orchestrator: HermesOrchestrator | None = None
_sandbox: TaskSandbox | None = None


def _get_sandbox() -> TaskSandbox:
    """Get the shared TaskSandbox from hermes.service."""
    return _service_get_sandbox()


def _get_orchestrator() -> HermesOrchestrator:
    """Get the shared Hermes orchestrator from hermes.service."""
    return _service_get_orchestrator()


class HermesChatRequest(BaseModel):
    """Request model for Hermes chat."""
    message: str = Field(..., min_length=1, max_length=10000, description="User message")
    # Optional conversation session id. When omitted, a shared default
    # session is used so the conversation still remembers earlier turns.
    session_id: str | None = Field(
        default=None, max_length=200, description="Conversation session id"
    )


class HermesChatResponse(BaseModel):
    """Response model for Hermes chat."""
    success: bool
    provider: str
    model: str
    response: str
    error: str | None = None
    # Name of the registered Sarthi tool executed for this reply (if any)
    tool_used: str | None = None
    # The session id used for this exchange (echoed back so the client can
    # pin a conversation without storing state server-side).
    session_id: str | None = None


class HermesToolInfo(BaseModel):
    """A registered tool Hermes may request."""
    name: str
    description: str
    parameters: dict = Field(default_factory=dict)


class HermesToolsResponse(BaseModel):
    """Response model for listing Hermes tools."""
    success: bool
    tools: list[HermesToolInfo] = Field(default_factory=list)
    error: str | None = None


class HermesSandboxRecord(BaseModel):
    """A compact record for one executed task (as stored in the query index)."""
    task_id: str
    prompt: str
    provider: str
    model: str
    status: str
    tool_used: str | None = None
    timestamp: str
    duration_ms: float = 0


class HermesSandboxQuery(BaseModel):
    """One indexed query and the task records that handled it."""
    query: str
    records: list[HermesSandboxRecord] = Field(default_factory=list)


class HermesSandboxResponse(BaseModel):
    """Response model for browsing the sandbox by query."""
    success: bool
    queries: list[HermesSandboxQuery] = Field(default_factory=list)
    error: str | None = None


class HermesSandboxTaskResponse(BaseModel):
    """Response model for one sandbox task's full artifacts."""
    success: bool
    task_id: str = ""
    prompt: str = ""
    response: str = ""
    trace: list[dict] | None = None
    metadata: dict | None = None
    error: str | None = None


@router.get("/sandbox", response_model=HermesSandboxResponse)
def hermes_sandbox() -> HermesSandboxResponse:
    """
    Browse past queries and their task records (the query index).

    Queries are returned newest-first, each with every task record that
    handled it, so the UI can show what was asked and how it ran without
    reading files itself.

    Returns:
        HermesSandboxResponse with grouped queries or a graceful error.
    """
    try:
        sandbox = _get_sandbox()
        queries = [
            HermesSandboxQuery(
                query=group["query"],
                records=[HermesSandboxRecord(**record) for record in group["records"]],
            )
            for group in sandbox.query_groups()
        ]
        return HermesSandboxResponse(success=True, queries=queries)
    except Exception as e:
        print(f"[DEBUG] Unexpected error in hermes_sandbox: {e}")
        return HermesSandboxResponse(success=False, error="Sandbox is unavailable.")


@router.get("/sandbox/tasks/{task_id}", response_model=HermesSandboxTaskResponse)
def hermes_sandbox_task(task_id: str) -> HermesSandboxTaskResponse:
    """
    Fetch one task's full artifacts (prompt, response, trace, metadata).

    Args:
        task_id: The task id as shown in the sandbox index.

    Returns:
        HermesSandboxTaskResponse with the task's artifacts, or a graceful
        error when the task does not exist.
    """
    try:
        sandbox = _get_sandbox()
        task = sandbox.get_task(task_id)
        if task is None:
            return HermesSandboxTaskResponse(success=False, error="Task not found.")
        return HermesSandboxTaskResponse(
            success=True,
            task_id=task_id,
            prompt=task.get("prompt") or "",
            response=task.get("response") or "",
            trace=task.get("trace"),
            metadata=task.get("metadata"),
        )
    except Exception as e:
        print(f"[DEBUG] Unexpected error in hermes_sandbox_task: {e}")
        return HermesSandboxTaskResponse(success=False, error="Task is unavailable.")


@router.get("/tools", response_model=HermesToolsResponse)
def hermes_tools() -> HermesToolsResponse:
    """
    List the registered tools Hermes may request.

    Tools are discovered from the Tool Registry so the list always matches
    what the LLM decision prompt sees — never hardcoded.

    Returns:
        HermesToolsResponse with the registered tools (name, description,
        parameters) or a graceful error.
    """
    try:
        from hermes.tool_registry import get_tool_registry

        registry = get_tool_registry()
        tools = [HermesToolInfo(**tool) for tool in registry.list_tools()]
        return HermesToolsResponse(success=True, tools=tools)
    except Exception as e:
        print(f"[DEBUG] Unexpected error in hermes_tools: {e}")
        return HermesToolsResponse(success=False, tools=[], error="Tools are unavailable.")


@router.post("/chat", response_model=HermesChatResponse)
def hermes_chat(request: HermesChatRequest) -> HermesChatResponse:
    """
    Send a message to the local Hermes model (via Ollama).

    Flow:
    1. Accept message from frontend
    2. Create Task
    3. Process through HermesOrchestrator
    4. Return structured response

    Args:
        request: Chat request with message

    Returns:
        HermesChatResponse with success, provider, model, response, tool_used, and optional error
    """
    try:
        message = request.message.strip()
        if not message:
            raise HTTPException(status_code=400, detail="Message cannot be empty")

        store = get_conversation_store()
        session_id = request.session_id or DEFAULT_SESSION
        history = store.get_history(session_id)

        # Create task with unique ID and attach prior session turns.
        # /remember facts are injected as a system message so the model
        # remembers what the user told it to remember.
        task_id = f"chat_{uuid.uuid4().hex[:8]}"
        task = Task(
            id=task_id,
            prompt=message,
            task_type="chat",
            history=history,
            memory=build_memory_prompt(),
        )

        # Get orchestrator and process
        orchestrator = _get_orchestrator()
        provider_response = orchestrator.process(task)

        # Remember the exchange for the next turn in this session
        store.add_turn(session_id, "user", message)
        if provider_response.success and provider_response.text:
            store.add_turn(session_id, "assistant", provider_response.text)

        # Debug logging
        print(f"[DEBUG] Provider response: success={provider_response.success}, provider={provider_response.provider}, error={provider_response.error}")

        # Build response
        return HermesChatResponse(
            success=provider_response.success,
            provider=provider_response.provider,
            model=provider_response.model,
            response=provider_response.text,
            error=provider_response.error if not provider_response.success else None,
            tool_used=provider_response.tool_used,
            session_id=session_id,
        )

    except ValueError as e:
        # Validation error
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        # Unexpected error - return graceful response
        print(f"[DEBUG] Unexpected error in hermes_chat: {e}")
        return HermesChatResponse(
            success=False,
            provider="Hermes",
            model="",
            response="",
            error="Local Hermes is unavailable.",
            session_id=request.session_id,
        )
