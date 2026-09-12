"""Network boundary of the Desktop client.

The ONLY module allowed to talk to the Backend — and only over HTTP.
Nothing here imports backend internals (brain, interpreter, model,
knowledge, executor); that separation is the point of the architecture.

Request/response shapes (see Backend/api.py ``/command``):

    request:  {"query": "<user text>"}
    response: {"success": bool, "response": str, "data": {...}|None, ...}

``send_query`` always returns a structured dict, even on connection
errors and malformed responses — the GUI never has to handle exceptions.
"""

from __future__ import annotations

from typing import Any

import httpx

from .config import REQUEST_TIMEOUT, get_backend_url

# Field names of the client-facing envelope (Backend/api.py _client_envelope).
FIELD_SUCCESS = "success"
FIELD_RESPONSE = "response"
FIELD_DATA = "data"


def build_command_payload(query: str) -> dict[str, str]:
    """Build the request body sent to ``POST /command``."""
    return {"query": query}


def send_query(
    query: str,
    base_url: str | None = None,
    timeout: float = REQUEST_TIMEOUT,
) -> dict[str, Any]:
    """Send one user query to the Backend and return a structured result.

    Returns a dict with at least:
        success  bool    did the Backend process the query successfully
        response str     human-readable answer ("" when unavailable)
        data     dict|None
        error    str     error kind for failures: unavailable | bad_response
        detail   str     human-readable error detail (failures only)

    Connection failures and malformed responses are converted into
    structured results — they are never raised past this boundary.
    """
    url = (base_url or get_backend_url()).rstrip("/") + "/command"
    payload = build_command_payload(query)

    try:
        http_response = httpx.post(url, json=payload, timeout=timeout)
    except (httpx.HTTPError, OSError) as exc:
        return {
            FIELD_SUCCESS: False,
            FIELD_RESPONSE: "",
            FIELD_DATA: None,
            "error": "unavailable",
            "detail": f"Could not reach the Sarthi backend ({url}): {exc}",
        }

    if http_response.status_code != 200:
        return {
            FIELD_SUCCESS: False,
            FIELD_RESPONSE: "",
            FIELD_DATA: None,
            "error": "bad_response",
            "detail": f"Backend returned HTTP {http_response.status_code} for {url}",
        }

    try:
        body = http_response.json()
    except ValueError:
        return {
            FIELD_SUCCESS: False,
            FIELD_RESPONSE: "",
            FIELD_DATA: None,
            "error": "bad_response",
            "detail": "Backend returned a response that is not valid JSON.",
        }

    if not isinstance(body, dict):
        return {
            FIELD_SUCCESS: False,
            FIELD_RESPONSE: "",
            FIELD_DATA: None,
            "error": "bad_response",
            "detail": "Backend returned malformed JSON (expected an object).",
        }

    # Tolerant field extraction: a backend that omits fields still yields
    # a predictable shape for the GUI.
    return {
        FIELD_SUCCESS: bool(body.get(FIELD_SUCCESS, False)),
        FIELD_RESPONSE: str(body.get(FIELD_RESPONSE) or body.get("text") or ""),
        FIELD_DATA: body.get(FIELD_DATA) if isinstance(body.get(FIELD_DATA), dict | list) else None,
        **{k: v for k, v in body.items() if k not in (FIELD_SUCCESS, FIELD_RESPONSE, FIELD_DATA)},
    }
