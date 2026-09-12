"""
events.py

Concrete automation events.

Every event inherits from AutomationEvent.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .contracts import AutomationEvent

# ==========================================================
# Skill Events
# ==========================================================


@dataclass(frozen=True)
class SkillTestPassedEvent(AutomationEvent):
    """
    Triggered when a skill successfully passes its tests.

    This is currently the only event supported by
    the Automation Engine.
    """

    skill_name: str

    skill_path: Path

    manifest_path: Path

    automation_path: Path

    def __init__(
        self,
        skill_name: str,
        skill_path: Path,
        manifest_path: Path,
        automation_path: Path,
    ):
        object.__setattr__(self, "event_name", "skill_test_passed")

        object.__setattr__(self, "skill_name", skill_name)

        object.__setattr__(self, "skill_path", skill_path)

        object.__setattr__(self, "manifest_path", manifest_path)

        object.__setattr__(self, "automation_path", automation_path)
