"""
Connector Registry — discovers and manages all available connectors.

Follows the same pattern as skills/registry.py: lazy discovery,
singleton access, and clean API for FastAPI endpoints.
"""

import logging
from typing import Any

from connectors.base import BaseConnector

logger = logging.getLogger(__name__)

# Global singleton
_registry: "ConnectorRegistry | None" = None


class ConnectorRegistry:
    """Registry of all available connector types.

    Connector implementations register themselves here.
    The registry provides a clean API for FastAPI endpoints.
    """

    def __init__(self):
        self._connectors: dict[str, BaseConnector] = {}
        self._discovered = False

    def register(self, connector: BaseConnector) -> None:
        """Register a connector instance."""
        meta = connector.metadata
        self._connectors[meta.id] = connector
        logger.info(f"Registered connector: {meta.name} ({meta.id})")

    def get(self, connector_id: str) -> BaseConnector | None:
        """Get a connector by its ID."""
        if not self._discovered:
            self.discover()
        return self._connectors.get(connector_id)

    def list_all(self) -> list[dict[str, Any]]:
        """List all registered connectors with their status."""
        if not self._discovered:
            self.discover()
        result = []
        for conn in self._connectors.values():
            d = conn.to_dict()
            result.append(d)
        return result

    def discover(self) -> None:
        """Discover and register all available connectors."""
        if self._discovered:
            return

        # Register Google Calendar connector
        try:
            from connectors.google_calendar.connector import GoogleCalendarConnector

            gc = GoogleCalendarConnector()
            self.register(gc)
        except Exception as e:
            logger.warning(f"Could not register Google Calendar connector: {e}")

        # Future connectors go here:
        # try:
        #     from connectors.gmail.connector import GmailConnector
        #     self.register(GmailConnector())
        # except Exception as e:
        #     logger.warning(f"Could not register Gmail connector: {e}")

        self._discovered = True
        logger.info(f"Discovered {len(self._connectors)} connector(s)")

    @property
    def count(self) -> int:
        if not self._discovered:
            self.discover()
        return len(self._connectors)


def get_registry() -> ConnectorRegistry:
    """Get the global ConnectorRegistry singleton."""
    global _registry
    if _registry is None:
        _registry = ConnectorRegistry()
    return _registry
