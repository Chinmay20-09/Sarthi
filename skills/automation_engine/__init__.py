"""
Automation Engine skill for Sarthi.

Generates assistant configurations from skill manifests.
Automates code generation and project analysis.

Public API:
    AutomationSkill — BaseSkill-compatible entry point
    AutomationEngine — core orchestrator (advanced usage)

Usage:
    from skills.automation_engine import AutomationSkill
    skill = AutomationSkill()
    result = skill.execute(intent)
"""

from .engine import AutomationEngine
from .skill import AutomationSkill

__all__ = ["AutomationSkill", "AutomationEngine"]
