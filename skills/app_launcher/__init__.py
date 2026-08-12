"""
Application Launcher skill for Sarthi.

Launches desktop applications discovered by the Knowledge Layer.

Usage:
    from skills.app_launcher import AppLauncherSkill
    skill = AppLauncherSkill()
"""

from .main import AppLauncherSkill

__all__ = ["AppLauncherSkill"]
