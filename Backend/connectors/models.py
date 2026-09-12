"""
Connector models — data structures for external service integrations.

Each connector represents a link to an external service (Google Calendar,
Gmail, GitHub, etc.) with its authentication state and available tools.
"""

from dataclasses import dataclass, field
from enum import Enum


class AuthType(str, Enum):
    """Supported authentication mechanisms."""

    OAUTH2 = "oauth2"
    API_KEY = "api_key"
    BEARER_TOKEN = "bearer_token"
    NONE = "none"
    CUSTOM = "custom"


class ConnectorStatus(str, Enum):
    """Connector connection states."""

    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"


@dataclass
class ConnectorTool:
    """A tool/capability exposed by a connector."""

    name: str
    description: str
    parameters: dict = field(default_factory=dict)


@dataclass
class ConnectorMetadata:
    """Static metadata about a connector type (not a specific instance).

    This describes what a connector CAN do, before any user has configured it.
    """

    id: str
    name: str
    type: str  # calendar, email, messaging, etc.
    service: str  # Google Calendar, Gmail, etc.
    auth_type: AuthType
    description: str = ""
    icon: str = "extension"
    tools: list[ConnectorTool] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type,
            "service": self.service,
            "auth_type": self.auth_type.value,
            "description": self.description,
            "icon": self.icon,
            "tools": [
                {"name": t.name, "description": t.description, "parameters": t.parameters}
                for t in self.tools
            ],
        }


@dataclass
class ConnectorInstance:
    """A user-configured connector instance (stored in the database)."""

    id: int | None = None
    name: str = ""
    type: str = ""
    service: str = ""
    auth_type: str = "none"
    status: ConnectorStatus = ConnectorStatus.DISCONNECTED
    config: dict = field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type,
            "service": self.service,
            "auth_type": self.auth_type,
            "status": self.status.value,
            "config": self.config,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
