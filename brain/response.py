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
    resolved: bool = False

    def to_api_dict(self) -> dict[str, Any]:
        """Serialize to a dict suitable for API responses."""
        # Human-readable message shown in the chat bubble.
        if not self.success and self.error:
            message = self.error
        # A skill can provide its own friendly message via result["message"]
        elif isinstance(self.action_result, dict) and self.action_result.get("message"):
            message = str(self.action_result["message"])
        elif self.status and self.status not in ("completed", "executed"):
            message = self.status
        else:
            message = "Done." if self.success else "Something went wrong."

        # Guard against a missing intent (pipeline error before interpretation)
        intent = self.intent

        # Lift conversational metadata a skill may attach (e.g. the Natural
        # Language Processor's source="nlp") to the top level so the UI can
        # badge the reply distinctly without digging into result.
        skill_result = self.action_result if isinstance(self.action_result, dict) else {}
        source = skill_result.get("source")
        provider = skill_result.get("provider")
        model = skill_result.get("model")

        return {
            "action": getattr(intent, "action", None),
            "target": getattr(intent, "target", None),
            "confidence": getattr(intent, "confidence", None),
            "status": self.status,
            "success": self.success,
            "execution_ms": round(self.execution_ms, 1),
            # Assistant message text for the chat bubble
            "text": message,
            # Structured result payload (skills emit visual cards via result.visual)
            "result": self.action_result,
            "error": self.error,
            # True only when the resolver actually rewrote an intent target
            "resolved": bool(self.resolved),
            # Skill reply metadata (source="nlp" etc.), when present
            "source": source,
            "provider": provider,
            "model": model,
        }
