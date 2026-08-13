"""
Knowledge Writer — structured write operations for Sarthi's Knowledge Layer.

All write operations to the Database Layer go through this module.
Knowledge NEVER performs reasoning — it only writes data.

ARCHITECTURE:
    Knowledge Writer is part of the Knowledge Layer.
    It handles structured writes:
        - History entries
        - Memory entries
        - Entity data (via refresh)

    The Writer delegates actual persistence to the Database Layer.
    It does NOT contain business logic about WHAT to write.
"""

import logging
from datetime import datetime
from typing import Any

from events import get_bus

logger = logging.getLogger(__name__)


class KnowledgeWriter:
    """
    Handles all write operations from the Knowledge Layer.

    Responsibilities:
        - Write history entries
        - Write memory entries
        - Route write requests to correct database

    What this does NOT do:
        - Make decisions about WHAT to write
        - Perform reasoning or validation
        - Launch applications or execute commands
    """

    def __init__(self):
        """Initialize the writer."""
        self.bus = get_bus()

    # ------------------------------------------------------------------
    # History
    # ------------------------------------------------------------------

    def write_history(self, entry: dict[str, Any]) -> bool:
        """
        Write a history entry.

        Args:
            entry: History entry data

        Returns:
            True if successful
        """
        try:
            from database.manager import get_database

            db = get_database()
            db.execute(
                """
                INSERT INTO command_history (command, action, target, success, timestamp)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    entry.get("command", ""),
                    entry.get("action", ""),
                    entry.get("target", ""),
                    int(entry.get("success", False)),
                    entry.get("timestamp", datetime.now().isoformat()),
                ),
            )
            return True
        except Exception as e:
            logger.error(f"Failed to write history: {e}")
            return False

    def write_memory(self, key: str, value: Any, ttl_seconds: int | None = None) -> bool:
        """
        Write a memory entry.

        Args:
            key: Memory key
            value: Memory value
            ttl_seconds: Optional TTL

        Returns:
            True if successful
        """
        try:
            from database.manager import get_database

            expires_at = None
            if ttl_seconds is not None:
                from datetime import timedelta

                expires_at = (datetime.now() + timedelta(seconds=ttl_seconds)).isoformat()

            db = get_database()
            db.execute(
                """
                INSERT OR REPLACE INTO knowledge_memory (key, value, expires_at, updated_at)
                VALUES (?, ?, ?, ?)
                """,
                (
                    key,
                    str(value),
                    expires_at,
                    datetime.now().isoformat(),
                ),
            )
            return True
        except Exception as e:
            logger.error(f"Failed to write memory: {e}")
            return False


# Global instance
_writer: KnowledgeWriter | None = None


def get_writer() -> KnowledgeWriter:
    """
    Get the global KnowledgeWriter instance.

    Returns:
        KnowledgeWriter singleton
    """
    global _writer
    if _writer is None:
        _writer = KnowledgeWriter()
    return _writer
