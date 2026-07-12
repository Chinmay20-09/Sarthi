"""
Application Executor for Sarthi.

Launches applications discovered by the knowledge system.

Uses KnowledgeManager for all lookups.
Does NOT know about JSON files or scanner directly.
"""

import logging
import subprocess
from typing import Optional

logger = logging.getLogger(__name__)


def open_app(target: str) -> bool:
    """
    Open an application by name or alias.

    Args:
        target: Application name or alias

    Returns:
        True if application opened successfully
    """
    from knowledge.manager import get_manager

    logger.debug(f"Opening application: {target}")

    target = target.lower().strip()

    if not target:
        logger.warning("Empty target provided")
        return False

    try:
        manager = get_manager()

        # Find application via manager
        app = manager.find_application(target)

        if app is None:
            logger.warning(f"Application not found: {target}")
            return False

        app_path = app.get("path")
        app_name = app.get("name")

        if not app_path:
            logger.error(f"No path found for application: {app_name}")
            return False

        logger.debug(f"Launching: {app_path}")

        try:
            subprocess.Popen(app_path, shell=True)
            logger.info(f"Opened {app_name}")
            return True

        except Exception as e:
            logger.error(f"Failed to launch {app_name}: {e}")
            return False

    except Exception as e:
        logger.error(f"Error in open_app: {e}")
        return False
