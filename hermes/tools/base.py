"""
Tool abstraction for the Sarthi Tool Bridge.

Hermes is the reasoning layer; it may only request tools registered here.
Each tool wraps an EXISTING Sarthi capability (skill / knowledge / executor).
Tools never expose arbitrary code, shell, or filesystem execution.

Security contract:
    - execute(arguments) must validate arguments before acting.
    - execute() returns a ToolResult — never raises, never leaks exceptions.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class ToolResult:
    """
    Structured, machine-readable result of a tool execution.

    Never contains raw Python exceptions, stack traces, API keys, or
    filesystem paths. ``error`` is always a safe, user-facing message.

    Attributes:
        success: Whether the underlying Sarthi execution succeeded.
        tool: Name of the tool that produced this result.
        result: Short human-readable summary (used when success=True).
        error: Safe failure message (used when success=False).
        data: Optional structured payload for the UI (never internal paths).
        unknown: True when the requested tool is not registered.
        invalid: True when the arguments failed validation.
    """

    success: bool
    tool: str
    result: str = ""
    error: str = ""
    data: dict[str, Any] | None = None
    unknown: bool = False
    invalid: bool = False


class BaseTool(ABC):
    """
    Minimal tool interface: name, description, parameters, execute(arguments).

    Subclasses delegate to Sarthi's existing execution system (skills,
    knowledge layer, executor) — they never become a second executor.
    """

    name: str = ""
    description: str = ""
    # JSON-schema-style parameter description:
    # {"type": "object", "properties": {...}, "required": [...]}
    parameters: dict[str, Any] = {}

    @abstractmethod
    def execute(self, arguments: dict[str, Any]) -> ToolResult:
        """
        Execute the tool with validated arguments.

        Args:
            arguments: Keyword arguments supplied by Hermes.

        Returns:
            ToolResult describing the outcome. Must not raise.
        """
        ...
