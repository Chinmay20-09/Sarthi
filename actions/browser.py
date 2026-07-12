"""
Browser Skill for Sarthi.

Opens websites discovered by the knowledge system.

Uses KnowledgeManager for all lookups.
Does NOT have hardcoded website list.
"""

import logging
import webbrowser

logger = logging.getLogger(__name__)


def open_site(target: str) -> bool:
    """
    Open a website by name or alias.

    Args:
        target: Website name or alias

    Returns:
        True if website opened successfully
    """
    from knowledge.manager import get_manager

    logger.debug(f"Opening website: {target}")

    target = target.lower().strip()

    if not target:
        logger.warning("Empty target provided")
        return False

    try:
        manager = get_manager()

        # Find website via manager
        website = manager.find_website(target)

        if website is None:
            logger.warning(f"Website not found: {target}")
            return False

        url = website.get("url")
        name = website.get("name")

        if not url:
            logger.error(f"No URL found for website: {name}")
            return False

        logger.debug(f"Opening: {url}")

        webbrowser.open(url)
        logger.info(f"Opened {name}")
        return True

    except Exception as e:
        logger.error(f"Error opening website: {e}")
        return False
