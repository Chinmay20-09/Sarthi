"""
contracts.py

Shared contracts for the Automation Engine.

Every assistant, engine component, and operation
communicates using these models.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# ==========================================================
# Events
# ==========================================================


@dataclass(frozen=True)
class AutomationEvent:
    """
    Base event.

    Every automation event inherits from this.
    """

    event_name: str


# ==========================================================
# Project Snapshot
# ==========================================================


@dataclass(frozen=True)
class ProjectState:
    """
    Immutable snapshot of the project.

    Assistants may READ this object.

    They must NEVER modify it.
    """

    project_root: Path

    skills: dict[str, Any]

    brain: dict[str, Any]

    metadata: dict[str, Any] = field(default_factory=dict)


# ==========================================================
# Change Request
# ==========================================================


@dataclass(frozen=True)
class ChangeRequest:
    """
    A request sent by an assistant.

    The assistant DOES NOT modify files.

    It simply requests a change.
    """

    subsystem: str

    operation: str

    target: str

    payload: dict[str, Any]

    reason: str

    confidence: float = 1.0


# ==========================================================
# Assistant Response
# ==========================================================


@dataclass(frozen=True)
class AssistantResponse:
    """
    Returned by every assistant.

    The engine collects these responses.
    """

    assistant: str

    success: bool

    summary: str

    requests: list[ChangeRequest] = field(default_factory=list)

    diagnostics: list[str] = field(default_factory=list)

    warnings: list[str] = field(default_factory=list)


# ==========================================================
# Automation Context
# ==========================================================


@dataclass
class AutomationContext:
    """
    Shared runtime context.

    Passed to every assistant.

    Unlike ProjectState, this CAN change during execution.
    """

    event: AutomationEvent

    project_state: ProjectState

    requests: list[ChangeRequest] = field(default_factory=list)

    diagnostics: list[str] = field(default_factory=list)

    metadata: dict[str, Any] = field(default_factory=dict)
