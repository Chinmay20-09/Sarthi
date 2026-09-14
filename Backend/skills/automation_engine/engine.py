"""
engine.py

Core Automation Engine.

Responsible for coordinating assistants: assistants register here, and the
skill drives them one at a time. It never edits files itself, and it never
reasons — an assistant proposes, a human approves, and an applier (not yet
implemented) would apply.

There is deliberately no event pipeline here. The former
``run(event) -> scan -> assistants -> preview -> approve -> apply`` flow was
unreachable (no caller, no test, no config), so it was removed rather than
kept as a second, competing orchestrator next to Sarthi's brain pipeline.
Building the automation lifecycle back is a planned feature: it belongs
behind Sarthi's task ownership (a persisted automation triggered by Sarthi),
not as an independent engine.
"""

from __future__ import annotations


class AutomationEngine:
    """Registry of automation assistants.

    Assistants are coordinated here; the engine owns no reasoning, no
    scheduling and no file access of its own.
    """

    def __init__(self):
        # Later this becomes automatic discovery.
        self.assistants = []

    def register_assistant(self, assistant) -> None:
        """Register an assistant with the engine."""
        self.assistants.append(assistant)

    def run_assistant(self, assistant, context):
        """Run one assistant over a context object and return its response.

        Kept as the single entry point for assistant execution so callers do
        not reach into ``assistant.analyze`` directly.

        Args:
            assistant: A registered assistant (exposes ``name`` + ``analyze``).
            context: The object the assistant analyses (read-only by contract).

        Returns:
            The assistant's response object.
        """
        return assistant.analyze(context)
