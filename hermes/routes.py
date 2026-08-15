"""Hermes chat endpoint for local AI integration."""

import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from hermes.config.loader import ConfigLoader
from hermes.models import Task
from hermes.orchestrator import HermesOrchestrator
from hermes.providers.local_provider import LocalHermesProvider
from hermes.providers.manager import ProviderManager
from hermes.providers.openrouter_provider import OpenRouterProvider

router = APIRouter(prefix="/hermes", tags=["hermes"])

# Lazy-initialized orchestrator
_orchestrator: HermesOrchestrator | None = None


def _get_orchestrator() -> HermesOrchestrator:
    """Get or initialize the Hermes orchestrator.

    Mirrors hermes/main.py: OpenRouter is the primary provider with a local
    Ollama fallback, unless HERMES_PROVIDER is set to an explicit local value.
    """
    global _orchestrator
    if _orchestrator is None:
        config = ConfigLoader().load()
        manager = ProviderManager()

        provider_name = (config.provider or "openrouter/free").lower()
        explicit_local = provider_name in ("local", "local_hermes", "localhermes")

        if explicit_local:
            # Explicit local mode: local provider only, no fallback
            manager.initialize(LocalHermesProvider(config))
        else:
            # Default mode: OpenRouter primary with local fallback
            manager.initialize(OpenRouterProvider(config))
            manager.set_fallback(LocalHermesProvider(config))

        _orchestrator = HermesOrchestrator(manager)
    return _orchestrator


class HermesChatRequest(BaseModel):
    """Request model for Hermes chat."""
    message: str = Field(..., min_length=1, max_length=10000, description="User message")


class HermesChatResponse(BaseModel):
    """Response model for Hermes chat."""
    success: bool
    provider: str
    model: str
    response: str
    error: str | None = None
    # Name of the registered Sarthi tool executed for this reply (if any)
    tool_used: str | None = None


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

        # Create task with unique ID
        task_id = f"chat_{uuid.uuid4().hex[:8]}"
        task = Task(
            id=task_id,
            prompt=message,
            task_type="chat"
        )

        # Get orchestrator and process
        orchestrator = _get_orchestrator()
        provider_response = orchestrator.process(task)

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
        )
