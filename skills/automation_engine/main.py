"""
Entry point for the SkillRegistry.

The registry instantiates skills from ``skills/<id>/main.py`` (see
skills/registry.py instantiate()) — without this file the Automation
Engine is never registered with the Brain, so "chain ... from chatgpt
to gemini" commands fall through to other skills and never run.

The actual skill lives in skill.py; this module just re-exports it.
"""

from .skill import AutomationSkill

__all__ = ["AutomationSkill"]
