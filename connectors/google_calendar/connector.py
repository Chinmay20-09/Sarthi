"""
Google Calendar connector — links Sarthi to the user's Google Calendar.

This is the first fully implemented connector. It uses OAuth2 for desktop apps
following Google's recommended flow.

Architecture:
    GoogleCalendarConnector (BaseConnector)
        → auth.py (OAuth2 flow, token management)
        → service.py (Calendar API calls)
"""

import json
import logging
from typing import Any

from connectors.base import BaseConnector
from connectors.google_calendar.auth import (
    OAuthCallbackHandler,
    build_auth_url,
    delete_token,
    exchange_code,
    get_valid_credentials,
    has_credentials,
    has_valid_token,
)
from connectors.google_calendar.service import get_calendar_info, list_upcoming_events
from connectors.models import AuthType, ConnectorMetadata, ConnectorStatus, ConnectorTool

logger = logging.getLogger(__name__)


class GoogleCalendarConnector(BaseConnector):
    """Google Calendar connector with OAuth2 authentication."""

    def __init__(self):
        self._metadata = ConnectorMetadata(
            id="google_calendar",
            name="Google Calendar",
            type="calendar",
            service="Google Calendar",
            auth_type=AuthType.OAUTH2,
            description="Access your Google Calendar events through Sarthi.",
            icon="calendar_today",
            tools=[
                ConnectorTool(
                    name="list_events",
                    description="List upcoming calendar events from your primary calendar.",
                ),
                ConnectorTool(
                    name="get_calendar_info",
                    description="Get calendar metadata (name, timezone).",
                ),
            ],
        )

    @property
    def metadata(self) -> ConnectorMetadata:
        return self._metadata

    def _load_client_config(self) -> dict[str, Any] | None:
        """Load the Google OAuth client credentials from disk."""
        from connectors.google_calendar.auth import CREDENTIALS_FILE

        if not CREDENTIALS_FILE.exists():
            return None
        try:
            return json.loads(CREDENTIALS_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            logger.error(f"Failed to load Google credentials: {e}")
            return None

    def _get_status_from_token(self) -> ConnectorStatus:
        """Determine status based on stored token state."""
        if not has_valid_token():
            return ConnectorStatus.DISCONNECTED
        try:
            token = get_valid_credentials(self._load_client_config() or {})
            if token and token.get("access_token"):
                return ConnectorStatus.CONNECTED
        except Exception:
            pass
        return ConnectorStatus.DISCONNECTED

    def is_connected(self) -> bool:
        """Check if we have valid OAuth credentials."""
        if not has_credentials():
            return False
        config = self._load_client_config()
        if not config:
            return False
        token = get_valid_credentials(config)
        return token is not None and bool(token.get("access_token"))

    def get_status(self) -> ConnectorStatus:
        """Get the current connection status."""
        if not has_credentials():
            return ConnectorStatus.DISCONNECTED
        return self._get_status_from_token()

    def get_auth_url(self) -> str:
        """Get the Google OAuth2 authorization URL.

        Opens a local server and returns the URL for the user to visit.

        Returns:
            The Google authorization URL.
        """
        client_config = self._load_client_config()
        if not client_config:
            raise ValueError(
                "Google credentials not found. Please place your "
                "google_credentials.json in the secrets/ directory."
            )
        auth_url, _state = build_auth_url(client_config)
        return auth_url

    def connect(self) -> dict[str, Any]:
        """Start the OAuth2 flow: open browser, wait for callback.

        This is the main entry point when the user clicks "Connect with Google".

        Returns:
            Dict with success status and any error message.
        """
        client_config = self._load_client_config()
        if not client_config:
            return {
                "success": False,
                "error": (
                    "Google credentials not found. "
                    "Please place your google_credentials.json in the secrets/ directory."
                ),
            }

        # Build auth URL
        auth_url, _state = build_auth_url(client_config)

        # Start local callback server
        handler = OAuthCallbackHandler()
        import webbrowser

        webbrowser.open(auth_url)
        logger.info("Opened browser for Google OAuth — waiting for callback...")

        code, error = handler.start_server_and_wait(timeout=120)

        if error:
            return {"success": False, "error": error}

        if not code:
            return {"success": False, "error": "No authorization code received"}

        # Exchange code for tokens
        result = exchange_code(code, client_config)
        return result

    def handle_auth_callback(self, callback_url: str) -> dict[str, Any]:
        """Handle an OAuth callback URL (for manual/programmatic use)."""
        from urllib.parse import parse_qs, urlparse

        parsed = urlparse(callback_url)
        params = parse_qs(parsed.query)
        code = params.get("code", [None])[0]
        error = params.get("error", [None])[0]

        if error:
            return {"success": False, "error": error}
        if not code:
            return {"success": False, "error": "No authorization code in callback"}

        client_config = self._load_client_config()
        if not client_config:
            return {"success": False, "error": "Google credentials not configured"}

        return exchange_code(code, client_config)

    def disconnect(self) -> dict[str, Any]:
        """Remove stored OAuth tokens."""
        success = delete_token()
        return {"success": success}

    def execute_tool(self, tool_name: str, params: dict | None = None) -> dict[str, Any]:
        """Execute a Google Calendar tool."""
        client_config = self._load_client_config()
        if client_config is None:
            return {"success": False, "error": "Google credentials not configured"}

        token = get_valid_credentials(client_config)
        if not token:
            return {"success": False, "error": "Not connected — please reconnect Google Calendar"}

        if tool_name == "list_events":
            max_results = (params or {}).get("max_results", 10)
            return list_upcoming_events(token, max_results=max_results)
        elif tool_name == "get_calendar_info":
            return get_calendar_info(token)
        else:
            return {"success": False, "error": f"Unknown tool: {tool_name}"}
