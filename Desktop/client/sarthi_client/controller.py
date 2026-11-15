"""Desktop client controller — the thin coordination layer.

Sits between the GUI (presentation) and the backend module (network).
Responsibilities: validate input, trigger the send, translate the
structured result into a display line and a status message.

No tkinter here and no httpx2 here — this file stays testable without a
display and without a network.
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from . import backend
from .config import get_backend_url

# Status lines shown in the GUI status bar
STATUS_CONNECTING = "Sending to Sarthi backend..."
STATUS_OFFLINE = "Backend unreachable — start it with root start.bat."
STATUS_BAD_RESPONSE = "Backend returned an invalid response."


class SendResult:
    """What the GUI needs to render one send action."""

    __slots__ = (
        "display_text",
        "status_text",
        "pet_state",
        "action_status",
        "client_action",
        "client_actions",
    )

    def __init__(
        self,
        display_text: str,
        status_text: str,
        pet_state: str | None = None,
        action_status: str | None = None,
        client_action: dict[str, Any] | None = None,
        client_actions: list[dict[str, Any]] | None = None,
    ):
        self.display_text = display_text
        self.status_text = status_text
        self.pet_state = pet_state
        self.action_status = action_status
        self.client_action = client_action
        self.client_actions = client_actions or ([client_action] if client_action else [])

    def __eq__(self, other: object) -> bool:
        return (
            isinstance(other, SendResult)
            and self.display_text == other.display_text
            and self.status_text == other.status_text
            and self.pet_state == other.pet_state
            and self.action_status == other.action_status
            and self.client_action == other.client_action
            and self.client_actions == other.client_actions
        )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return (
            f"SendResult(display={self.display_text!r}, status={self.status_text!r}, "
            f"pet_state={self.pet_state!r})"
        )


def is_valid_query(query: str | None) -> bool:
    """A query is valid when it contains at least one non-space character."""
    return bool(query) and bool(query.strip())


class SarthiController:
    """Validate → send → translate, for the Desktop GUI."""

    def __init__(self, backend_url: str | None = None):
        # Resolved once here so the GUI can display the target backend;
        # config.py stays the only place the URL is decided.
        self.backend_url = backend_url or get_backend_url()
        self.session_id = f"desktop_{uuid4().hex}"

    def send(self, query: str | None) -> SendResult:
        """Send one query to the Backend and translate the result."""
        if not is_valid_query(query):
            return SendResult(
                display_text="",
                status_text="Please enter a command first.",
            )

        result: dict[str, Any] = backend.send_query(
            (query or "").strip(), base_url=self.backend_url, session_id=self.session_id
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
        data = result.get(backend.FIELD_DATA)
        action = result.get("action")
        client_action = result.get("client_action")
        if not isinstance(client_action, dict):
            client_action = None
        client_actions = result.get("client_actions")
        if not isinstance(client_actions, list) or any(not isinstance(item, dict) for item in client_actions):
            client_actions = [client_action] if client_action else []
        action_status = None
        if isinstance(action, dict) and client_action is None:
            action_status = "completed" if action.get("success") else "failed"
        pet_state = result.get("pet_state")
        if not pet_state and isinstance(data, dict):
            pet_state = data.get("pet_state")
        if not result.get(backend.FIELD_SUCCESS):
            status = f"Desktop action {action_status}." if action_status else "Failed"
            return SendResult(
                display_text=response_text or status,
                status_text=status,
                pet_state=pet_state,
                action_status=action_status,
                client_action=None,
                client_actions=[],
            )

        return SendResult(
            display_text=response_text or "Done.",
            status_text=(
                f"Desktop action {action_status}."
                if action_status
                else f"Backend: {self.backend_url}"
            ),
            pet_state=pet_state,
            action_status=action_status,
            client_action=client_action,
            client_actions=client_actions,
        )

    def get_model_profile(self) -> dict[str, Any]:
        """Read the backend's persisted local model profile over HTTP."""
        return backend.get_model_profile(base_url=self.backend_url)

    def set_model_profile(self, profile: str) -> dict[str, Any]:
        """Persist a local model profile through the backend settings API."""
        return backend.set_model_profile(profile, base_url=self.backend_url)
