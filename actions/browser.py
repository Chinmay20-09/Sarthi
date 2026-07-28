"""
Browser Skill — BACKWARD COMPATIBILITY SHIM.

Website opening has moved to skills/browser/ as a proper BaseSkill.
This module is preserved for existing code that imports from actions.browser.

ARCHITECTURE:
    Website opening is now a skill (skills/browser/).
    New code should use the skill system instead.

NEW CODE SHOULD USE:
    from skills.registry import get_registry
    registry = get_registry()
    browser = registry.get_skill("browser")
    browser.execute(intent)
"""

import logging

logger = logging.getLogger(__name__)


def open_site(target: str) -> bool:
    """
    Open a website by name or alias.

    BACKWARD COMPATIBLE: delegates to BrowserSkill.
    New callers should go through the skill system directly.
    """
    from brain.intent import Intent
    from skills.browser.main import BrowserSkill

    logger.debug(f"open_site (shim): {target}")

    skill = BrowserSkill()
    result = skill.execute(Intent(action="open", target=target))

    return result.get("success", False)
