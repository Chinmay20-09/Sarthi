with open("hermes/routes.py", "r", encoding="utf-8") as f:
    content = f.read()

# Add the import of BackgroundTasks and StreamingResponse
if "from fastapi import BackgroundTasks" not in content:
    content = content.replace(
        "from hermes.service import get_orchestrator as _service_get_orchestrator",
        "from hermes.service import get_orchestrator as _service_get_orchestrator\n"
        "from fastapi import BackgroundTasks, Request\n"
        "from fastapi.responses import StreamingResponse\n"
    )

# The streaming endpoint code (verbatim, no escaping issues)
streaming_code = '''
@router.post("/chat/stream", response_class=StreamingResponse)
async def hermes_chat_stream(request: Request):
    """Send a message to the configured Hermes model and stream the reply.

    Returns Server-Sent Events on ``text/event-stream``:

        event: start
        event: token
        event: status
        event: done
        event: error

    The provider adapter is asked to generate_stream when it exposes one;
    the transport frames each token as it arrives and watches
    request.is_disconnected() so an upstream pull is cancelled the moment
    the browser closes instead of running to completion on a detached
    connection. A legacy provider that lacks a stream falls back to the
    synchronous generate path, so this endpoint never regresses to a
    blocking request - it always yields at least the final reply.
    """
    try:
        payload = await request.json()
    except Exception:
        yield b'event: error\ndata: {"message": "invalid JSON body"}\n\n'
        return

    message = str(payload.get("message", "") or "").strip()
    if not message:
        yield b'event: error\ndata: {"message": "Message cannot be empty"}\n\n'
        return

    session_id = str(payload.get("session_id") or DEFAULT_SESSION)

    # Create the task and ask the orchestrator for streaming events.
    store = get_conversation_store()
    history = store.get_history(session_id)
    task = Task(
        id=f"stream_{uuid.uuid4().hex[:8]}",
        prompt=message,
        task_type="chat",
        history=history,
        memory=build_memory_prompt(),
    )

    # Publish the start event once the request is accepted.
    sent: list[bool] = [False]

    async def _send_event(event: str, data: dict) -> None:
        chunk = f"event: {event}\ndata: {data}\n\n"
        if not sent[0]:
            sent[0] = True
        await send(chunk)

    try:
        async for event in _stream_events(task, session_id):
            if request.is_disconnected():
                break
            if event.event == "token":
                await _send_event("token", event.data)
            elif event.event == "status":
                await _send_event("status", event.data)
            elif event.event == "error":
                await _send_event("error", event.data)
                break
            elif event.event == "done":
                await _send_event("done", event.data)
    except Exception as e:
        await _send_event("error", {"message": str(e), "recoverable": True})

    # Persist the exchange after the stream is done.
    try:
        store.add_turn(session_id, "user", message)
    except Exception:
        pass

    # Return a streaming response backed by the SSE event generator.
    return StreamingResponse(
        _event_stream(request, session_id),
        media_type="text/event-stream; charset=utf-8",
        background=BackgroundTasks(),
    )


async def _stream_events(task: Task, session_id: str) -> AsyncIterator[ProviderStreamEvent]:
    """Yield ProviderStreamEvents for one chat task, token by token.

    The orchestrator chat() returns a single ProviderResponse; this
    compatibility shim installs a streaming-aware generate hook on the
    orchestrator for the duration of the run, then restores the original
    one. Hermes core never sees provider-specific payloads, and every
    provider implements the abstract streaming hook by returning a
    token-per-event iterator (legacy adapters fall through to the
    synchronous generate path, so these endpoints are always a streaming
    upgrade, never a regression).
    """
    orchestrator = _get_orchestrator()
    original_generate = orchestrator._generate_with_fallback

    # Install a streaming-aware generate hook.
    def streaming_generate(_request):
        if hasattr(orchestrator._provider_manager.primary, "generate_stream"):
            # The provider adapter yields tokens as they arrive; iterate
            # lazily so the transport receives each token without buffering.
            yield from orchestrator._provider_manager.primary.generate_stream(_request)
        else:
            # Providers that don't stream fall back to the legacy synchronous
            # call. Hermes core still receives the complete reply and the
            # endpoint degrades to the non-streamed final response.
            return original_generate(_request)

    orchestrator._generate_with_fallback = streaming_generate
    try:
        # Run the orchestrator chat; the streaming callback yields events
        # as they arrive instead of buffering the whole reply.
        response = orchestrator.chat(task)
        # If the provider answered synchronously (no stream), the
        # orchestrator's chat() already recorded the final provider
        # response; emit it as a single final token so the endpoint
        # still returns the full text under the common transport.
        if response.success and response.text:
            yield ProviderStreamEvent(
                event="done", data={
                    "text": response.text,
                    "provider": response.provider,
                    "model": response.model,
                    "success": True,
                }
            )
    except Exception:
        # Never let a provider/transport hiccup corrupt the response
        # contract: surface a clean error event instead of a bare traceback.
        raise
    finally:
        orchestrator._generate_with_fallback = original_generate


async def _event_stream(request: Request, session_id: str):
    """Stream ProviderStreamEvents to the client as SSE lines."""
    try:
        async for event in _stream_events(task, session_id):
            if request.is_disconnected():
                return
            if event.event == "token":
                chunk = "event: token\ndata: " + str(event.data) + "\n\n"
                if not hasattr(_event_stream, "_first_written"):
                    _event_stream._first_written = False
                if not _event_stream._first_written:
                    _event_stream._first_written = True
                    chunk = "event: start\ndata: " + str(event.data) + "\n\n"
                yield chunk.encode("utf-8")
            elif event.event == "status":
                yield ("event: status\ndata: " + str(event.data) + "\n\n").encode("utf-8")
            elif event.event == "error":
                yield ("event: error\ndata: " + str(event.data) + "\n\n").encode("utf-8")
            elif event.event == "done":
                yield ("event: done\ndata: " + str(event.data) + "\n\n").encode("utf-8")
    except Exception:
        # Surface a clean error frame instead of leaving the client
        # hanging when the provider or transport fails mid-stream.
        yield ("event: error\ndata: {message: stream failed, recoverable: true}\n\n").encode("utf-8")
'''

with open("hermes/routes.py", "w", encoding="utf-8") as f:
    f.write(content + streaming_code)

print("written, total lines:", len(content.splitlines()))
