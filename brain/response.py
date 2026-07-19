"""
Response models for Sarthi's Brain.

BrainResponse is the standardized output of the brain pipeline,
containing both the intent and execution result.
"""

from dataclasses import dataclass, field
from typing import Any

from brain.intent import Intent


@dataclass
class BrainResponse:
    """
    Standardized output from the brain pipeline.

    Returned by BrainEngine.process() and used by API endpoints
    and the CLI main loop.

    Attributes:
        intent: The final Intent after resolution
        success: Whether execution completed successfully
        status: Human-readable status message
        action_result: Result data from the executor (varies by action type)
        execution_ms: Time taken for pipeline execution in milliseconds
        error: Error message if execution failed
    """

    intent: Intent
    success: bool = False
    status: str = "initialized"
    action_result: dict[str, Any] | None = field(default=None)
    execution_ms: float = 0.0
    error: str | None = field(default=None)

    def to_api_dict(self) -> dict[str, Any]:
        """Serialize to a dict suitable for API responses."""
        return {
            "action": self.intent.action,
            "target": self.intent.target,
            "confidence": self.intent.confidence,
            "status": self.status,
            "success": self.success,
            "execution_ms": round(self.execution_ms, 1),
        }
