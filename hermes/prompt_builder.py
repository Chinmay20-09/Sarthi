from .models import Task


def build_prompt(task: Task) -> str:
    return f"""
You are Hermes.

Task:
{task.prompt}
"""
