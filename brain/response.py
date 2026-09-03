"""
Response models for Sarthi's Brain.

BrainResponse is the standardized output of the brain pipeline,
containing both the intent and execution result.
"""

from dataclasses import dataclass, field
from typing import Any

from brain.intent import Intent


def _message_for(success: bool, status: str, error: str | None, action_result: Any) -> str:
    """Human-readable message for one executed step."""
    if not success and error:
        return error
    # A skill can provide its own friendly message via result["message"]
    if isinstance(action_result, dict) and action_result.get("message"):
        return str(action_result["message"])
    if status and status not in ("completed", "executed"):
        return status
    return "Done." if success else "Something went wrong."


def step_payload(intent: Intent, result: dict[str, Any]) -> dict[str, Any]:
    """API-shaped payload for ONE executed plan step.

    Mirrors the top-level fields of BrainResponse.to_api_dict() so the UI
    can render every step of a multi-query command (open, play, reply...)
    with the same message/result/source semantics.
    """
    success = bool(result.get("success", False))
    status = result.get("status") or ("executed" if success else "error")
    action_result = result.get("result")
    error = result.get("error")

    # Lift conversational metadata (source="nlp" etc.) from the step result
    skill_result = action_result if isinstance(action_result, dict) else {}

    return {
        "action": getattr(intent, "action", None),
        "target": getattr(intent, "target", None),
        "confidence": getattr(intent, "confidence", None),
        "status": status,
        "success": success,
        # Assistant text for this step (reply text, error, status...)
        "text": _message_for(success, status, error, action_result),
        # Structured result payload (skills emit visual cards via result.visual)
        "result": action_result,
        "error": error,
        # Skill reply metadata (source="nlp" etc.), when present
        "source": skill_result.get("source"),
        "provider": skill_result.get("provider"),
        "model": skill_result.get("model"),
    }


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
        steps: One API-shaped payload per executed plan step (multi-query
               commands), newest last. None for single-step commands.
    """

    intent: Intent
    success: bool = False
    status: str = "initialized"
    action_result: dict[str, Any] | None = field(default=None)
    execution_ms: float = 0.0
    error: str | None = field(default=None)
    resolved: bool = False
    steps: list[dict[str, Any]] | None = field(default=None)

    def to_api_dict(self) -> dict[str, Any]:
        """Serialize to a dict suitable for API responses."""
        # Guard against a missing intent (pipeline error before interpretation)
        intent = self.intent
        message = _message_for(self.success, self.status, self.error, self.action_result)

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
            # One payload per executed plan step, so the UI can render a
            # card for every action of a multi-query command.
            "steps": self.steps or [],
        }
