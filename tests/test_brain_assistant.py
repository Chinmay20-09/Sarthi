from pathlib import Path

from skills.automation_engine.assistants.brain_assistant.main import BrainAssistant

skill_path = Path(r"C:\Sarthi\skills\project_tracker")

assistant = BrainAssistant()

output = assistant.analyze(skill_path)

print(f"Generated: {output}")
