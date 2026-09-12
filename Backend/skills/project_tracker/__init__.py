"""
GitHub Project Tracker skill for Sarthi.

Manages GitHub repositories, tracks issues, pull requests,
and provides project status summaries.

Public API:
    GitHubProjectSkill — skill.execute(intent) for command processing
"""

from .main import GitHubProjectSkill

__all__ = ["GitHubProjectSkill"]
