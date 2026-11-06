"""Streaming transport primitives.

This module owns the HTTP layer only: framing an event as SSE, flushing it,
and (most importantly) finding when the client has gone away so an upstream
model pull can be cancelled instead of letting a detached thread run to
completion.

Nothing here touches Hermes core or the provider adapters; it sits purely on
top of the existing FastAPI application layer.
"""

from typing import Any

from fastapi import Request

# The application/x-ndjson hint we send to streaming-capable providers.  The
# server in this repo is a local model (Ollama), whose /api/chat pull answers
# NDJSON one object per line; this header tells it how the client will
# consume those lines.
NDJSON_CONTENT_TYPE = "application/x-ndjson"

# Keep-alive space so a slow consumer does not time out on the HTTP layer.
KEEP_ALIVE_INTERVAL = 15


async def _write_event(send: Any, event: str, data: dict[str, Any]) -> None:
    """Serialize one event and flush it to the client.

    ``send`` is the ASGI send callable passed in by the routing layer.
    """
    chunk = f"event: {event}\ndata: {data}\n\n"
    await send(chunk)


@asynccontextmanager
async def streaming_response(request: Request):
    """Yield (send, accept) for the duration of a streaming response.

    The caller owns the upstream pull; when ``accept()`` returns True the
    client has gone away and the upstream must be interrupted instead of
    running to completion on a detached connection.
    """
    from fastapi import Request as _Request

    async def accept() -> bool:
        return request.is_disconnected()

    yield accept
