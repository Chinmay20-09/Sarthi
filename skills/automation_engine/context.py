"""
context.py

Builds the AutomationContext used during execution.
"""

from __future__ import annotations

import json
from pathlib import Path

from .contracts import (
    AutomationContext,
    ProjectState,
)
from .events import SkillTestPassedEvent


class ProjectScanner:
    """
    Builds an immutable project snapshot
    and wraps it inside an AutomationContext.
    """

    def build(
        self,
        event: SkillTestPassedEvent,
    ) -> AutomationContext:
        project_root = event.skill_path.parent.parent

        project_state = ProjectState(
            project_root=project_root,
            skills=self._load_skills(project_root),
            brain=self._load_brain(project_root),
            metadata={},
        )

        return AutomationContext(
            event=event,
            project_state=project_state,
        )

    # ------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------

    def _load_skills(
        self,
        project_root: Path,
    ) -> dict:
        skills = {}

        skills_folder = project_root / "skills"

        if not skills_folder.exists():
            return skills

        for skill in skills_folder.iterdir():
            if not skill.is_dir():
                continue

            manifest = skill / "manifest.json"

            if not manifest.exists():
                continue

            try:
                with open(manifest, encoding="utf-8") as f:
                    skills[skill.name] = json.load(f)

            except Exception:
                continue

        return skills

    def _load_brain(
        self,
        project_root: Path,
    ) -> dict:
        """
        Temporary.

        Eventually this will read
        brain registries automatically.
        """

        return {}
