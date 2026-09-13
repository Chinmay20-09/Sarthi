"""
Sarthi Tool Bridge — registered tools that Hermes may request.

Only tools registered here can be executed by Hermes. Every tool delegates
to an existing Sarthi capability; none of them expose arbitrary code or
shell execution.
"""

from .base import BaseTool, ToolResult
from .browser_ask import BrowserAskTool
from .close_app import CloseAppTool
from .github import GitHubTool
from .history_search import HistorySearchTool
from .memory_search import MemorySearchTool
from .open_app import OpenAppTool
from .open_website import OpenWebsiteTool
from .personal_context import PersonalContextTool
from .project_get import ProjectGetTool
from .search_web import SearchWebTool

__all__ = [
    "BaseTool",
    "ToolResult",
    "GitHubTool",
    "OpenAppTool",
    "OpenWebsiteTool",
    "PersonalContextTool",
    "CloseAppTool",
    "SearchWebTool",
    "BrowserAskTool",
    "HistorySearchTool",
    "MemorySearchTool",
    "ProjectGetTool",
    "register_default_tools",
]


def register_default_tools(registry) -> None:
    """
    Register the built-in tools on a ToolRegistry.

    Args:
        registry: ToolRegistry instance (or any object with .register()).
    """
    registry.register(OpenAppTool())
    registry.register(OpenWebsiteTool())
    registry.register(CloseAppTool())
    registry.register(SearchWebTool())
    registry.register(BrowserAskTool())
    registry.register(HistorySearchTool())
    registry.register(MemorySearchTool())
    registry.register(ProjectGetTool())
    registry.register(GitHubTool())
    registry.register(PersonalContextTool())
