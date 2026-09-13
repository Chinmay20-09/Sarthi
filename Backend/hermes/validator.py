"""
Tool-Call Validator — the single gate between Hermes' decisions and Sarthi's
tools (Phase 3c).

Every structured tool call parsed by ``tool_planner.parse_tool_call`` (and
later, the bounded agent loop) passes through ``validate_tool_call`` BEFORE
the registry dispatches anything. The validator is pure and synchronous:
no model calls, no database access, no network — microseconds per call.

Layered on top of existing Sarthi abstractions (no duplication):

    tool_planner._extract_tool_call   → structural shape (JSON contract)
    validate_tool_call (this module)  → identity, injection, semantics
    tool_registry.validate_arguments  → schema (required/typed properties)
    tool_registry.execute             → dispatch (tools re-check their args)

What it blocks, and why:

    - Unregistered tool names      → structured refusal, never a dispatch.
    - Malformed names (embedded    → an 8B model can echo prompt fragments
      dots/globs/quotes/control      back as a "tool name"; these are noise,
      chars, absurd length)          never legitimate registry keys.
    - Injection-shaped arguments   → arguments are DATA, never interpreted.
      (SQL fragments, shell meta-   Tools receive them through parameterized
      characters, control chars,    queries / subprocess argument lists, but
      credential-like values)       the validator still refuses the obvious
                                    patterns so bad output dies here.
    - Schema mismatches            → unknown arguments, missing required
                                     arguments, wrong types (delegated to
                                     the registry's validate_arguments so
                                     there is exactly one schema authority).
    - Prompt-injection payloads    → tool calls arriving as arguments are a
      embedded in arguments         model-output channel; they die here.

Refusals are structured (ValidationResult.valid=False + a stable ``reason``
code + a model-friendly ``message``), never exceptions — a malformed tool
call is a normal, recoverable event in an LLM loop, not an error condition.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Limits & patterns
# ---------------------------------------------------------------------------

MAX_TOOL_NAME_LENGTH = 64
MAX_ARGUMENTS_JSON_CHARS = 4_000
MAX_STRING_ARGUMENT_CHARS = 2_000

# Registry keys are snake_case identifiers. Everything else is noise from
# the model (echoed prose, prompt fragments, hallucinated names).
_TOOL_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")

# Control characters (except \t \n \r) have no business in a tool call.
_CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

# Substrings that mark a value as a secret rather than data. Arguments that
# carry one are refused: the model must never push credentials into tools.
_SECRET_VALUE_HINTS = (
    "password=",
    "passwd=",
    "api_key=",
    "apikey=",
    "token=",
    "bearer ",
    "authorization:",
    "-----begin",
    "private key",
)

# Per-key argument-name hints: an argument NAMED like a credential is
# refused outright, even though the value never gets a free pass either.
_SECRET_KEY_HINTS = (
    "password",
    "passwd",
    "secret",
    "token",
    "api_key",
    "apikey",
    "credential",
    "cvv",
    "credit_card",
    "card_number",
    "ssn",
)

# Shell/terminal meta escape attempts. Registered Sarthi tools never run a
# raw shell (the terminal tool, in 3e, will use a fixed argv), but refusing
# these patterns keeps a compromised model from ever crafting them.
_SHELL_METACHARS = ("`", "$(", "${", "\x00", "\x1b")

# Prompt-injection payload fragments that must never ride inside tool
# arguments (the model would be instructing a future model call).
_INJECTION_PHRASES = (
    "ignore all previous instructions",
    "ignore previous instructions",
    "disregard all previous",
    "disregard your instructions",
    "forget all previous instructions",
    "system prompt:",
    "</system>",
    "<system>",
    "you are now",
    "new instructions:",
)

# SQL injection shape in string arguments (tools use parameterized SQL, so
# this is defense in depth for anything that ever interpolates). Matches
# stacked-query markers, bare destructive statements, and tautologies —
# deliberately NOT generic words like "select ... from" which appear in
# legitimate natural-language queries ("select all photos from last week").
_SQL_INJECTION_RE = re.compile(
    r"(?:--|;)\s*(?:drop|delete|update|insert|alter)\b"
    r"|\bdrop\s+table\b"
    r"|\bdelete\s+from\b"
    r"|\binsert\s+into\b"
    r"|\balter\s+table\b"
    r"|\bunion\s+select\b"
    r"|\bor\s+['\"]?1['\"]?\s*=\s*['\"]?1\b",
    re.IGNORECASE,
)

# Path traversal shape — arguments naming files must not escape the sandbox.
_PATH_TRAVERSAL_RE = re.compile(r"(?:^|[\\/])\.\.(?:[\\/]|$)")


@dataclass
class ValidationResult:
    """Outcome of validating one structured tool call.

    Attributes:
        valid: True when the call may proceed to registry dispatch.
        reason: Stable machine-readable reason code ("" when valid).
        message: Safe, model-friendly explanation of a refusal ("" when
            valid). Fed back to Hermes so it can correct itself.
        errors: Individual per-check errors (for logging/tests).
    """

    valid: bool
    reason: str = ""
    message: str = ""
    errors: list[str] = field(default_factory=list)


@dataclass
class ValidatedToolCall:
    """A tool call that passed validation — safe to hand to the registry."""

    tool: str
    arguments: dict[str, Any]


# ---------------------------------------------------------------------------
# Argument checks
# ---------------------------------------------------------------------------


def _check_string_value(tool: str, key: str, value: str) -> list[str]:
    """Injection/size checks for one string argument. Returns error list."""
    errors: list[str] = []
    label = f"{tool}.{key}"

    if _CONTROL_CHARS_RE.search(value):
        errors.append(f"{label}: control characters are not allowed")

    if len(value) > MAX_STRING_ARGUMENT_CHARS:
        errors.append(f"{label}: exceeds {MAX_STRING_ARGUMENT_CHARS} characters")

    lowered = value.lower()
    if any(hint in lowered for hint in _SECRET_VALUE_HINTS):
        errors.append(f"{label}: credential-like values are not allowed")

    if any(meta in value for meta in _SHELL_METACHARS):
        errors.append(f"{label}: shell/terminal metacharacters are not allowed")

    if any(phrase in lowered for phrase in _INJECTION_PHRASES):
        errors.append(f"{label}: prompt-injection payload is not allowed")

    if _SQL_INJECTION_RE.search(value):
        errors.append(f"{label}: SQL-injection shape is not allowed")

    if _PATH_TRAVERSAL_RE.search(value):
        errors.append(f"{label}: path traversal is not allowed")

    return errors


def check_arguments(tool: str, arguments: dict[str, Any]) -> list[str]:
    """Structural safety checks over the argument mapping (no schema needed).

    Schema conformance (required keys, declared properties, types) is the
    registry's job — this checks what the schema cannot: size ceilings,
    control characters, injection shapes, and credential-shaped content.
    """
    errors: list[str] = []

    # Serialize once for a global size ceiling (dicts/values can be huge).
    # No ``default=`` hook: an argument that cannot survive JSON is model
    # noise and is refused outright rather than stringified blindly.
    try:
        import json

        serialized = json.dumps(arguments, ensure_ascii=False)
    except (TypeError, ValueError):
        errors.append("arguments: not JSON-serializable")
        return errors

    if len(serialized) > MAX_ARGUMENTS_JSON_CHARS:
        errors.append(f"arguments: exceed {MAX_ARGUMENTS_JSON_CHARS} characters")

    for key, value in arguments.items():
        if not isinstance(key, str):
            errors.append(f"{tool}: argument names must be strings")
            continue

        lowered_key = key.lower()
        if any(hint in lowered_key for hint in _SECRET_KEY_HINTS):
            errors.append(f"{tool}.{key}: credential-like argument names are not allowed")

        if isinstance(value, str):
            errors.extend(_check_string_value(tool, key, value))
        elif isinstance(value, dict):
            for sub_key, sub_value in value.items():
                if isinstance(sub_key, str) and isinstance(sub_value, str):
                    errors.extend(_check_string_value(tool, f"{key}.{sub_key}", sub_value))

    return errors


# ---------------------------------------------------------------------------
# Public validation gate
# ---------------------------------------------------------------------------


def validate_tool_call(
    call: Any,
    is_registered: Callable[[str], bool] | None = None,
) -> ValidationResult:
    """Validate one structured tool call before registry dispatch.

    Args:
        call: The parsed tool call — expected {"tool": str, "arguments": dict}.
            Anything else is refused (the model misbehaved).
        is_registered: Callable returning True when the tool name is in the
            registry (``ToolRegistry.get``-compatible). ``None`` skips the
            registration check (used by unit tests / callers without a
            registry).

    Returns:
        ValidationResult with valid=True exactly when every check passes.
        Never raises.
    """
    try:
        return _validate(call, is_registered)
    except Exception as e:  # absolute last resort — never break the loop
        logger.error("validator: unexpected failure: %s", e)
        return ValidationResult(
            valid=False,
            reason="validation_error",
            message="The requested action could not be validated.",
        )


def _validate(
    call: Any,
    is_registered: Callable[[str], bool] | None,
) -> ValidationResult:
    errors: list[str] = []

    # --- structural shape -------------------------------------------------
    if not isinstance(call, dict):
        return ValidationResult(
            valid=False,
            reason="not_a_tool_call",
            message="The response was not a structured tool call.",
            errors=["tool call is not an object"],
        )

    tool = call.get("tool")
    arguments = call.get("arguments")

    if not isinstance(tool, str) or not tool.strip():
        return ValidationResult(
            valid=False,
            reason="missing_tool_name",
            message="The tool call did not name a tool.",
            errors=["tool name missing or not a string"],
        )

    if arguments is None:
        arguments = {}
    if not isinstance(arguments, dict):
        return ValidationResult(
            valid=False,
            reason="invalid_arguments",
            message="Tool arguments must be an object.",
            errors=["arguments is not an object"],
        )

    tool = tool.strip()

    # --- name hygiene ------------------------------------------------------
    if len(tool) > MAX_TOOL_NAME_LENGTH or not _TOOL_NAME_RE.fullmatch(tool):
        errors.append(f"tool name '{tool[:64]}' is not a registered-tool identifier")
        return ValidationResult(
            valid=False,
            reason="invalid_tool_name",
            message="The requested tool does not exist.",
            errors=errors,
        )

    # --- registration ------------------------------------------------------
    if is_registered is not None and not is_registered(tool):
        return ValidationResult(
            valid=False,
            reason="unknown_tool",
            message=f"The tool '{tool}' is not available.",
            errors=[f"tool '{tool}' is not registered"],
        )

    # --- argument safety ----------------------------------------------------
    errors.extend(check_arguments(tool, arguments))
    if errors:
        return ValidationResult(
            valid=False,
            reason="unsafe_arguments",
            message=(
                "The tool arguments were refused for safety reasons. "
                "Re-check the arguments and try again."
            ),
            errors=errors,
        )

    return ValidationResult(valid=True)


# ---------------------------------------------------------------------------
# Async wrapper (for the 3d agent loop)
# ---------------------------------------------------------------------------


async def validate_tool_call_async(
    call: Any,
    is_registered: Callable[[str], bool] | None = None,
) -> ValidationResult:
    """Async-friendly variant. The validation itself is synchronous and
    fast; the wrapper exists so the agent loop can await it uniformly
    alongside tool executions."""
    return validate_tool_call(call, is_registered)
