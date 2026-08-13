"""
Intent model for Sarthi's Brain.

The core data contract that flows through the entire pipeline:
    Interpreter → Planner → Resolver → Executor

Each stage may enrich the Intent with additional metadata,
but the action/target/confidence fields are set by the Interpreter.
"""

from pydantic import BaseModel


class Intent(BaseModel):
    """
    Parsed intent from natural language input.

    This is the PRIMARY data contract for the brain pipeline.
    Every stage (Interpreter, Planner, Resolver, Executor)
    operates on this model.

    Attributes:
        action: The action to perform (open, search, play, close, etc.)
        target: The target entity (application, website, file, etc.)
        confidence: Confidence score of the interpretation (0.0 to 1.0)
    """

    action: str = "unknown"
    target: str = ""
    confidence: float = 0.0
