"""
Application Executor — BACKWARD COMPATIBILITY SHIM.

Application launching has moved to skills/app-launcher/ as a proper BaseSkill.
This module is preserved for existing code that imports from actions.apps.

ARCHITECTURE:
    Application launching is now a skill (skills/app-launcher/).
    New code should use the skill system instead.

NEW CODE SHOULD USE:
    from skills.registry import get_registry
    registry = get_registry()
    launcher = registry.get_skill("app_launcher")
    launcher.execute(intent)
"""

import logging

logger = logging.getLogger(__name__)


def open_app(target: str) -> bool:
    """
    Open an application by name or alias.

    BACKWARD COMPATIBLE: delegates to AppLauncherSkill.
    New callers should go through the skill system directly.
    """
    from brain.intent import Intent
    from skills.app_launcher.main import AppLauncherSkill

    logger.debug(f"open_app (shim): {target}")

    skill = AppLauncherSkill()
    result = skill.execute(Intent(action="open", target=target))

    return result.get("success", False)
