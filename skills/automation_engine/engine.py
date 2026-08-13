"""
engine.py

Core Automation Engine.

Responsible for coordinating assistants.

It never edits files itself.
"""

from __future__ import annotations

from .context import ProjectScanner
from .contracts import AssistantResponse
from .events import AutomationEvent
from .preview import PreviewGenerator


class AutomationEngine:
    def __init__(self):
        self.scanner = ProjectScanner()

        # Later this becomes automatic discovery.
        self.assistants = []

    # ---------------------------------------------------------

    def register_assistant(self, assistant):
        """
        Registers an assistant with the engine.
        """

        self.assistants.append(assistant)

    # ---------------------------------------------------------

    def run(self, event: AutomationEvent):
        """
        Main execution pipeline.
        """

        print("=" * 60)
        print("Automation Engine Started")
        print("=" * 60)

        # Step 1
        context = self.scanner.build(event)

        # Step 2
        responses = self._run_assistants(context)

        # Step 3
        PreviewGenerator().show(responses)

        # Step 4
        approved = self._request_approval()

        if not approved:
            print("\nAutomation cancelled.")

            return

        # Step 5
        self._apply_requests(responses)

        # Step 6
        self._validate()

        print("\nAutomation completed successfully.")

    # ---------------------------------------------------------

    def _run_assistants(self, context):
        responses = []

        for assistant in self.assistants:
            print(f"\nRunning {assistant.name}...")

            response = assistant.analyze(context)

            responses.append(response)

        return responses

    # ---------------------------------------------------------

    def _request_approval(self):
        while True:
            choice = input("\nApply these changes? (y/n): ").lower()

            if choice == "y":
                return True

            if choice == "n":
                return False

    # ---------------------------------------------------------

    def _apply_requests(self, responses: list[AssistantResponse]):
        """
        Placeholder.

        Applier will be implemented later.
        """

        print("\nApplying approved changes...")

    # ---------------------------------------------------------

    def _validate(self):
        """
        Placeholder.

        Validation comes later.
        """

        print("Running validation...")
