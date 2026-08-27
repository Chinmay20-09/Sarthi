"""
Tool Planner — Hermes' decision layer for the Sarthi Tool Bridge.

Flow:
    User request
      -> Hermes (LLM) decides: final answer OR structured tool call
      -> Sarthi Tool Registry executes the registered tool
      -> Tool result is fed back to Hermes
      -> Hermes produces the final response

The LLM produces a structured, machine-readable tool request
({"tool_call": {"tool": ..., "arguments": {...}}}) — natural language is
never parsed with fragile string matching. The loop is bounded by
MAX_TOOL_CALLS_PER_TASK so Hermes can never loop forever.
"""

import json
import logging
from collections.abc import Callable
from typing import Any

from hermes.models import Task
from hermes.providers.base import ProviderResponse
from hermes.tool_registry import ToolRegistry
from hermes.tools.base import ToolResult

logger = logging.getLogger(__name__)

# Hard limit on tool executions per task — prevents infinite tool loops.
MAX_TOOL_CALLS_PER_TASK = 5

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


def _with_instructions(task: Task, instructions: str) -> Task:
    """Copy the task, preserving all fields, and attach system instructions."""
    return Task(
        prompt=task.prompt,
        id=task.id,
        task_type=task.task_type,
        context=task.context,
        instructions=instructions,
        # Preserve prior conversation turns so decision/follow-up calls see
        # the full session context, not just the current prompt.
        history=task.history,
        # Preserve /remember facts so tool-planning calls see them too.
        memory=task.memory,
    )


class ToolPlanner:
    """
    Runs the bounded Hermes <-> Sarthi tool loop for one task.

    Args:
        tool_registry: Registry of tools Hermes may request.
        generate: Callable that sends a Task to the providers and returns a
                  ProviderResponse (primary + fallback handled by the caller).
    """

    def __init__(
        self,
        tool_registry: ToolRegistry,
        generate: Callable[[Task], ProviderResponse],
        trace: list[dict] | None = None,
    ) -> None:
        self._tool_registry = tool_registry
        self._generate = generate
        self._trace = trace

    def _record(self, **step: Any) -> None:
        """Append an execution step to the trace when one was provided."""
        if self._trace is not None:
            self._trace.append(step)

    def run(self, task: Task) -> ProviderResponse:
        """
        Process the task: decide, (optionally) run tools, produce the final answer.

        Args:
            task: The user's chat task.

        Returns:
            ProviderResponse. When a tool was used, tool_used is set to the
            last tool that executed.
        """
        # Phase 1 — decision: ask the model whether a tool is needed.
        decision_task = _with_instructions(
            task, build_decision_instructions(task.prompt, self._tool_registry.list_tools())
        )
        response = self._generate(decision_task)
        self._record(
            step="decision",
            provider=response.provider,
            model=response.model,
            success=response.success,
            text=response.text,
            error=response.error,
        )
        if not response.success:
            return response

        decision = parse_tool_call(response.text)
        if decision is None:
            # Normal conversational answer — no tool involved.
            return response

        last_tool: str | None = None
        for _ in range(MAX_TOOL_CALLS_PER_TASK):
            tool = decision["tool"]
            arguments = decision["arguments"]
            last_tool = tool
            self._record(step="tool_call", tool=tool, arguments=arguments)

            result = self._tool_registry.execute(tool, arguments)
            self._record(
                step="tool_result",
                tool=tool,
                success=result.success,
                result=result.result,
                error=result.error,
            )
            if result.unknown:
                # Hermes requested a tool that is not registered.
                return ProviderResponse(
                    success=True,
                    provider=response.provider,
                    model=response.model,
                    text="That capability is not available.",
                    tool_used=tool,
                )

            # Phase 2 — feed the result back and get the next decision/answer.
            followup_task = _with_instructions(
                task, build_followup_instructions(task.prompt, tool, result)
            )
            response = self._generate(followup_task)
            self._record(
                step="response",
                provider=response.provider,
                model=response.model,
                success=response.success,
                text=response.text,
                error=response.error,
            )
            if not response.success:
                return response

            decision = parse_tool_call(response.text)
            if decision is None:
                # Hermes' final response based on the tool result.
                return ProviderResponse(
                    success=True,
                    provider=response.provider,
                    model=response.model,
                    text=response.text,
                    tool_used=last_tool,
                )

        # Hard limit reached — stop gracefully with an explanatory response.
        logger.warning("Tool call limit (%d) reached for task %s", MAX_TOOL_CALLS_PER_TASK, task.id)
        return ProviderResponse(
            success=True,
            provider=response.provider,
            model=response.model,
            text=(
                "I could not complete that request because it needed too many steps. "
                "Please ask for one action at a time."
            ),
            tool_used=last_tool,
        )
