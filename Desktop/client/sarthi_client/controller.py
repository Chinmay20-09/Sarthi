"""Desktop client controller — the thin coordination layer.

Sits between the GUI (presentation) and the backend module (network).
Responsibilities: validate input, trigger the send, translate the
structured result into a display line and a status message.

No tkinter here and no httpx2 here — this file stays testable without a
display and without a network.
"""

from __future__ import annotations

from typing import Any

from . import backend
from .config import get_backend_url

# Status lines shown in the GUI status bar
STATUS_CONNECTING = "Sending to Sarthi backend..."
STATUS_OFFLINE = "Backend unreachable — is it running? (Backend\\sarthi.bat)"
STATUS_BAD_RESPONSE = "Backend returned an invalid response."


class SendResult:
    """What the GUI needs to render one send action."""

    __slots__ = ("display_text", "status_text")

    def __init__(self, display_text: str, status_text: str):
        self.display_text = display_text
        self.status_text = status_text

    def __eq__(self, other: object) -> bool:
        return (
            isinstance(other, SendResult)
            and self.display_text == other.display_text
            and self.status_text == other.status_text
        )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"SendResult(display={self.display_text!r}, status={self.status_text!r})"


def is_valid_query(query: str | None) -> bool:
    """A query is valid when it contains at least one non-space character."""
    return bool(query) and bool(query.strip())


class SarthiController:
    """Validate → send → translate, for the Desktop GUI."""

    def __init__(self, backend_url: str | None = None):
        # Resolved once here so the GUI can display the target backend;
        # config.py stays the only place the URL is decided.
        self.backend_url = backend_url or get_backend_url()

    def send(self, query: str | None) -> SendResult:
        """Send one query to the Backend and translate the result."""
        if not is_valid_query(query):
            return SendResult(
                display_text="",
                status_text="Please enter a command first.",
            )

        result: dict[str, Any] = backend.send_query(
            (query or "").strip(), base_url=self.backend_url
        )

        error = result.get("error")
        if error == "unavailable":
            return SendResult(display_text="", status_text=STATUS_OFFLINE)
        if error == "bad_response":
            return SendResult(
                display_text="",
                status_text=f"{STATUS_BAD_RESPONSE} ({result.get('detail', '')})",
            )

        response_text = str(result.get(backend.FIELD_RESPONSE, "")).strip()
        if not result.get(backend.FIELD_SUCCESS):
            status = "Failed"
            return SendResult(display_text=response_text or status, status_text=status)

        return SendResult(
            display_text=response_text or "Done.",
            status_text=f"Backend: {self.backend_url}",
        )
