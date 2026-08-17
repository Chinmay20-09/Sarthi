"""
Skills package for Sarthi.

Every capability is implemented as an independent skill package.
Each skill exposes a BaseSkill interface for the Executor.

Skills are discovered dynamically from this directory by the SkillRegistry
(one folder per skill, each with a manifest.json and main.py).

Public API:
    SkillRegistry — discovers and loads all installed skills
"""
