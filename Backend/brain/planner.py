"""
Planner for Sarthi's Brain.

Responsible for decomposing complex intents into multi-step plans.

Future examples:
    "Open YouTube and play Lofi"
        → [Intent(open, YouTube), Intent(play, Lofi)]

    "Send an email to John about the meeting tomorrow"
        → [Intent(open, email), Intent(compose, John), Intent(schedule, meeting)]

Current implementation is a pass-through stub.
The Planner simply returns the intent as a single-step plan.
"""

import logging

from brain.context import BrainContext
from brain.intent import Intent

logger = logging.getLogger(__name__)


class Planner:
    """
    Multi-step intent planner.

    Currently a pass-through stub. Future versions will:
    - Parse compound commands (e.g., "and then", "after that")
    - Decompose complex requests into sequential steps
    - Handle conditional logic and error recovery
    - Support parallel action execution
    """

    def plan(self, intent: Intent, context: BrainContext) -> list[Intent]:
        """
        Decompose an intent into a sequence of executable steps.

        Args:
            intent: The parsed Intent from the Interpreter
            context: Current pipeline context

        Returns:
            List of Intent objects to execute in sequence.
            Currently returns a single-element list.
        """
        logger.debug(
            f"Planning: {intent.action} {intent.target} (confidence={intent.confidence:.2f})"
        )

        # Current: pass-through
        # Future: split compound commands into multiple intents
        return [intent]
