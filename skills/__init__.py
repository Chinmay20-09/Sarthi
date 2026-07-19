"""
Skills package for Sarthi.

Every capability is implemented as an independent skill package.
Each skill exposes a BaseSkill interface for the Executor.

Skills currently available:
    - project_tracker (GitHub/Notion project management)
    - automation_engine (Code automation subsystem)
    - speech_recognition (Voice input)

Public API:
    SkillManager — discovers and loads all installed skills
"""
