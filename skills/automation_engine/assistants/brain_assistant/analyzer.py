"""
analyzer.py
"""

from ...contracts import (
    AssistantResponse,
    ChangeRequest,
)
from .constants import BRAIN, REGISTER_COMMAND


class BrainAnalyzer:
    def analyze(self, context, skill):
        requests = []

        capabilities = skill["brain"]["capabilities"]

        for capability in capabilities:
            requests.append(
                ChangeRequest(
                    subsystem=BRAIN,
                    operation=REGISTER_COMMAND,
                    target="command_registry",
                    payload=capability,
                    reason="Skill registration",
                )
            )

        return AssistantResponse(
            assistant="Brain Assistant",
            success=True,
            summary="Brain analysis complete.",
            requests=requests,
        )
