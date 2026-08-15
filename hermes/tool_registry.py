"""
Tool Registry for the Sarthi Tool Bridge.

Hermes may only request tools that are registered here. The registry
dispatches to the registered tool and NEVER executes anything itself
beyond that dispatch. Arguments are validated before any tool runs.
"""

import logging
from typing import Any

from hermes.tools.base import BaseTool, ToolResult

logger = logging.getLogger(__name__)


def validate_arguments(parameters: dict[str, Any], arguments: Any) -> str | None:
    """
    Validate arguments against a JSON-schema-style parameter description.

    Supports the subset used by registered tools: object type with
    string-typed properties and a required list.

    Args:
        parameters: {"type": "object", "properties": {...}, "required": [...]}
        arguments: Value supplied by Hermes.

    Returns:
        An error message string, or None when the arguments are valid.
    """
    if not isinstance(arguments, dict):
        return "Arguments must be an object."

    schema = parameters or {}
    properties = schema.get("properties", {}) or {}

    for required in schema.get("required", []) or []:
        if required not in arguments or arguments[required] in (None, ""):
            return f"Missing required argument: {required}"

    for key, value in arguments.items():
        prop = properties.get(key) or {}
        if prop.get("type") == "string" and not isinstance(value, str):
            return f"Argument '{key}' must be a string."

    return None


class ToolRegistry:
    """
    Registry of tools Hermes may call.

    Responsibilities:
        - register a tool
        - retrieve a tool by name
        - list available tools (for LLM prompts / UI)
        - validate arguments and dispatch to the registered tool
    """

    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}

    # ------------------------------------------------------------------
    # Registration & lookup
    # ------------------------------------------------------------------

    def register(self, tool: BaseTool) -> None:
        """Register a tool. Replaces any existing tool with the same name."""
        if not tool.name:
            raise ValueError("Tool must have a name.")
        self._tools[tool.name] = tool
        logger.debug("Registered tool: %s", tool.name)

    def get(self, name: str) -> BaseTool | None:
        """Retrieve a tool by name, or None if not registered."""
        return self._tools.get(name)

    def list_tools(self) -> list[dict[str, Any]]:
        """List registered tools as name/description/parameters dicts."""
        return [
            {"name": tool.name, "description": tool.description, "parameters": tool.parameters}
            for tool in self._tools.values()
        ]

    def tool_names(self) -> list[str]:
        """Names of all registered tools."""
        return list(self._tools.keys())

    # ------------------------------------------------------------------
    # Dispatch
    # ------------------------------------------------------------------

    def execute(self, name: str, arguments: dict[str, Any]) -> ToolResult:
        """
        Validate arguments and dispatch to the registered tool.

        Args:
            name: Registered tool name.
            arguments: Arguments for the tool.

        Returns:
            ToolResult. Never raises; unknown tools and invalid arguments
            produce structured, safe results.
        """
        tool = self._tools.get(name)
        if tool is None:
            return ToolResult(success=False, tool=name, unknown=True)

        error = validate_arguments(tool.parameters, arguments)
        if error is not None:
            return ToolResult(success=False, tool=name, error=error, invalid=True)

        try:
            return tool.execute(arguments)
        except Exception as e:  # never leak internals upward
            logger.error("Tool '%s' failed unexpectedly: %s", name, e)
            return ToolResult(
                success=False,
                tool=name,
                error="The tool failed unexpectedly.",
            )


# ----------------------------------------------------------------------
# Default registry (singleton)
# ----------------------------------------------------------------------

_registry: ToolRegistry | None = None


def get_tool_registry() -> ToolRegistry:
    """Get the global ToolRegistry with the default tools registered."""
    global _registry
    if _registry is None:
        from hermes.tools import register_default_tools

        _registry = ToolRegistry()
        register_default_tools(_registry)
    return _registry
