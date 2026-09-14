"""
Tool-call protocol — the Hermes <-> Sarthi tool bridge contract.

This module owns the *interfaces* of the tool bridge and nothing else:

    - the decision prompt that offers the registered tools to the model
      (``build_decision_instructions``)
    - the follow-up prompt that feeds a tool result back
      (``build_followup_instructions``)
    - the structured parser for the model's tool request
      (``parse_tool_call``)

Hermes produces a structured, machine-readable tool request
({"tool_call": {"tool": ..., "arguments": {...}}}) — natural language is
never parsed with fragile string matching. The loop that drives these calls,
bounds the iterations, validates each request and persists the run lives in
one place: ``hermes/agent.py`` (HermesAgent). There is no second loop here.
"""

import json
from typing import Any

from hermes.tools.base import ToolResult

_DECISION_HEADER = """You are Hermes, the reasoning and orchestration layer of Sarthi.

Decide whether the user's request can be fulfilled using one of the registered
tools below. You can ONLY use these tools — you never write or execute code,
run shell commands, access the filesystem, or browse the web yourself.

Available tools:
{TOOLS}

Rules:
- If the request can be fulfilled with a tool, reply with EXACTLY one JSON
  object and nothing else:
  {"tool_call": {"tool": "<tool name>", "arguments": {"<argument>": "<value>"}}}
- Use single curly braces exactly as shown (do not double them).
- If the request is a normal conversation, reply normally — do not mention
  tools or JSON.
"""

_FOLLOWUP_HEADER = """You are Hermes, the reasoning and orchestration layer of Sarthi.

The user's request was: "{USER_REQUEST}"

You used the tool "{TOOL}" and received this result:
{TOOL_RESULT}

Reply to the user in a concise, friendly way based on this result. If the
result was a failure, explain it gracefully without technical details.
Reply with a normal message. Only use the JSON tool_call format above if
another registered tool is still needed to complete the request.
"""


def _render_tools(tools: list[dict[str, Any]]) -> str:
    """Render registered tools into the prompt (never hardcoded)."""
    lines = []
    for tool in tools:
        properties = (tool.get("parameters") or {}).get("properties", {}) or {}
        args = ", ".join(f'"{name}": "<{name}>"' for name in properties)
        lines.append(f"- {tool['name']}: {tool['description']} Arguments: {{{args}}}")
    return "\n".join(lines) if lines else "- (no tools registered)"


def _result_summary(result: ToolResult) -> str:
    """Safe, human-readable summary of a tool result for the LLM."""
    if result.success:
        return f'{{"success": true, "result": "{result.result}"}}'
    return f'{{"success": false, "error": "{result.error or "the tool could not complete the action."}"}}'


def build_decision_instructions(user_message: str, tools: list[dict[str, Any]]) -> str:
    """System instructions asking the model to decide text vs tool call."""
    return (
        _DECISION_HEADER.replace("{TOOLS}", _render_tools(tools))
        + f"\nUser request: {user_message}"
    )


def build_followup_instructions(user_message: str, tool: str, result: ToolResult) -> str:
    """System instructions giving the model the tool result for the final reply."""
    return (
        _FOLLOWUP_HEADER.replace("{USER_REQUEST}", user_message)
        .replace("{TOOL}", tool)
        .replace("{TOOL_RESULT}", _result_summary(result))
    )


def _try_json(text: str) -> dict[str, Any] | None:
    """Parse a JSON object, returning None when parsing fails."""
    try:
        parsed = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return None
    return parsed if isinstance(parsed, dict) else None


def _try_parse_candidate(candidate: str) -> dict[str, Any] | None:
    """Try whole-text JSON, then the outermost JSON object embedded in prose."""
    parsed = _try_json(candidate)
    if parsed is not None:
        return _extract_tool_call(parsed)

    start = candidate.find("{")
    end = candidate.rfind("}")
    if start != -1 and end > start:
        parsed = _try_json(candidate[start : end + 1])
        if parsed is not None:
            return _extract_tool_call(parsed)
    return None


def parse_tool_call(text: str) -> dict[str, Any] | None:
    """
    Parse a structured tool call from a model response.

    Accepts a bare JSON object or one wrapped in markdown code fences.
    Tolerates models that double curly braces ({{ }}) as an escaping
    artifact. Returns {"tool": ..., "arguments": {...}} for a valid tool
    call, or None when the response is a normal conversational answer.
    """
    if not text or not text.strip():
        return None

    candidate = text.strip()
    # Strip markdown code fences if present.
    if candidate.startswith("```"):
        candidate = candidate.strip("`").strip()
        if candidate.startswith(("json", "JSON")):
            candidate = candidate[4:].strip()

    result = _try_parse_candidate(candidate)
    if result is not None:
        return result

    # Some models double the braces even when told not to — collapse them
    # and retry. Only attempted after the plain parse fails, and only the
    # tool_call shape is accepted, so we never mis-execute a valid reply.
    deescaped = candidate.replace("{{", "{").replace("}}", "}")
    if deescaped != candidate:
        return _try_parse_candidate(deescaped)

    return None


def _extract_tool_call(parsed: dict[str, Any]) -> dict[str, Any] | None:
    """Validate a parsed object has the tool_call shape."""
    tool_call = parsed.get("tool_call")
    if not isinstance(tool_call, dict):
        return None
    tool = tool_call.get("tool")
    if not isinstance(tool, str) or not tool:
        return None
    arguments = tool_call.get("arguments")
    if not isinstance(arguments, dict):
        arguments = {}
    return {"tool": tool, "arguments": arguments}
