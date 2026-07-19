"""
brain_assistant/main.py

Public entry point for the Brain Assistant.
"""

from pathlib import Path

from .generator import AssistantGenerator


class BrainAssistant:
    """
    Generates assistant.json from manifest.json.
    """

    def __init__(self):
        self.generator = AssistantGenerator()

    def analyze(self, skill_path: Path):
        """
        Generate assistant.json for a skill.

        Args:
            skill_path: Path to the skill folder.
        """

        manifest_path = skill_path / "manifest.json"
        assistant_path = skill_path / "assistant.json"

        self.generator.generate(
            manifest_path=manifest_path,
            output_path=assistant_path,
        )

        return assistant_path
