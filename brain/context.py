"""
Runtime context for the Brain pipeline.

Carries state across pipeline stages (Interpreter → Planner → Resolver → Executor)
and provides metadata for logging, debugging, and telemetry.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from brain.intent import Intent


@dataclass
class BrainContext:
    """
    Runtime context for a single command execution.

    Created by BrainEngine at the start of processing
    and passed through each pipeline stage.

    Attributes:
        original_text: The raw text input from the user
        intent: The parsed Intent (enriched as it flows through stages)
        start_time: When processing started
        stage: Current pipeline stage name
        metadata: Arbitrary key-value store for stage-specific data
        error: Error message if the pipeline failed (None if successful)
    """

    original_text: str
    intent: Intent = field(default_factory=Intent)
    start_time: datetime = field(default_factory=datetime.now)
    stage: str = "initialized"
    metadata: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    # True when the resolver actually rewrote an intent target
    resolved: bool = False

    @property
    def elapsed_ms(self) -> float:
        """Milliseconds since context was created."""
        return (datetime.now() - self.start_time).total_seconds() * 1000
