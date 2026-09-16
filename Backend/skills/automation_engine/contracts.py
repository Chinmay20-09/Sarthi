"""
contracts.py

Shared contracts for the Automation Engine.

Assistants read an immutable ProjectState and answer with an
AssistantResponse carrying ChangeRequests. Assistants never modify files
themselves. (The event/context machinery that used to wrap these models was
unreachable and has been removed.)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

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
