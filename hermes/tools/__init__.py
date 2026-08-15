"""
Sarthi Tool Bridge — registered tools that Hermes may request.

Only tools registered here can be executed by Hermes. Every tool delegates
to an existing Sarthi capability; none of them expose arbitrary code or
shell execution.
"""

from .base import BaseTool, ToolResult
from .open_app import OpenAppTool
from .open_website import OpenWebsiteTool

__all__ = ["BaseTool", "ToolResult", "OpenAppTool", "OpenWebsiteTool", "register_default_tools"]


def register_default_tools(registry) -> None:
    """
    Register the built-in tools on a ToolRegistry.

    Args:
        registry: ToolRegistry instance (or any object with .register()).
    """
    registry.register(OpenAppTool())
    registry.register(OpenWebsiteTool())
