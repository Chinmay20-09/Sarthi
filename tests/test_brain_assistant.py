"""Quick smoke test for the BrainAssistant skill analysis."""

from pathlib import Path

from skills.automation_engine.assistants.brain_assistant.main import BrainAssistant

skill_path = Path(__file__).parent.parent / "skills" / "project_tracker"

assistant = BrainAssistant()

output = assistant.analyze(skill_path)

print(f"Generated: {output}")
