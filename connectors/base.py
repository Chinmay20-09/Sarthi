"""
Base connector — abstract interface for all external service connectors.

Every connector (Google Calendar, Gmail, GitHub, etc.) subclasses this
and implements the required methods.
"""

import logging
from abc import ABC, abstractmethod
from typing import Any

from connectors.models import ConnectorMetadata, ConnectorStatus, ConnectorTool

logger = logging.getLogger(__name__)


class BaseConnector(ABC):
    """Abstract base class for all external service connectors.

    Subclasses must implement:
        - metadata (property)
        - get_auth_url() — for OAuth2 connectors
        - handle_auth_callback() — complete the auth flow
        - disconnect() — remove stored credentials
        - is_connected() — check if valid credentials exist
        - execute_tool() — run a connector tool (e.g., list_events)
    """

    @property
    @abstractmethod
    def metadata(self) -> ConnectorMetadata:
        """Static metadata describing this connector type."""
        ...

    @abstractmethod
    def get_auth_url(self) -> str:
        """Get the OAuth2 authorization URL (for OAuth2 connectors).

        Returns:
            URL string the user should open in a browser.
        """
        ...

    @abstractmethod
    def handle_auth_callback(self, callback_url: str) -> dict[str, Any]:
        """Complete the OAuth2 flow with the callback URL.

        Args:
            callback_url: The full redirect URL with auth code.

        Returns:
            Dict with success status and optional error message.
        """
        ...

    @abstractmethod
    def disconnect(self) -> dict[str, Any]:
        """Remove stored credentials and mark as disconnected.

        Returns:
            Dict with success status.
        """
        ...

    @abstractmethod
    def is_connected(self) -> bool:
        """Check if valid credentials exist and the service is reachable."""
        ...

    @abstractmethod
    def execute_tool(self, tool_name: str, params: dict | None = None) -> dict[str, Any]:
        """Execute a connector tool.

        Args:
            tool_name: Name of the tool to execute (e.g., 'list_events').
            params: Optional parameters for the tool.

        Returns:
            Dict with tool execution results.
        """
        ...

    def get_status(self) -> ConnectorStatus:
        """Get the current connection status."""
        try:
            if self.is_connected():
                return ConnectorStatus.CONNECTED
        except Exception:
            logger.debug(f"Status check failed for {self.metadata.id}")
        return ConnectorStatus.DISCONNECTED

    def to_dict(self) -> dict:
        """Serialize to dictionary for API responses."""
        return {
            **self.metadata.to_dict(),
            "status": self.get_status().value,
        }
