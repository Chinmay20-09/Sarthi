from .models import HermesTask


def build_prompt(task: HermesTask) -> str:
    return f"""
You are Hermes.

Task:
{task.prompt}
"""