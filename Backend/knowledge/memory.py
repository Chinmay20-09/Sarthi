"""
Knowledge Memory — conversation history and user preferences.

Provides short-term and long-term memory for Sarthi.
Memory is part of the Knowledge Layer — it stores and retrieves,
but does NOT reason about what to remember.

ARCHITECTURE:
    Knowledge Memory sits in the Knowledge Layer.
    It provides:
        - Short-term memory (in-memory, TTL-based)
        - Long-term memory (persistent, SQLite-backed)
        - Conversation history
        - User preferences

    Memory has NO control over what gets stored.
    The Brain decides what's important to remember.
    Memory simply stores and retrieves on request.

Usage:
    from knowledge.memory import KnowledgeMemory, get_memory

    memory = get_memory()

    # Remember something (short-term, 5 min TTL)
    memory.remember("last_command", "open chrome", ttl=300)

    # Recall
    value = memory.recall("last_command")

    # Remember something long-term (persistent)
    memory.remember_long("user_name", "Alice")

    # Recall long-term
    name = memory.recall_long("user_name")

    # Get conversation history
    history = memory.get_history(limit=10)

    # Store a conversation entry
    memory.store_conversation("open chrome", "opened", True)
"""

import logging
from datetime import datetime
from typing import Any

from knowledge.cache import get_cache

logger = logging.getLogger(__name__)


class KnowledgeMemory:
    """
    Short-term and long-term memory for Sarthi.

    Short-term memory is in-memory with TTL (like human working memory).
    Long-term memory is stored in SQLite (like human episodic memory).

    Responsibilities:
        - Store short-term memories (in-memory cache with TTL)
        - Store long-term memories (SQLite-backed)
        - Store and retrieve conversation history
        - Store and retrieve user preferences

    What this does NOT do:
        - Decide what to remember (Brain decides)
        - Analyze or reason about memories
        - Forget based on importance (only TTL-based expiry)
    """

    def __init__(self):
        """Initialize memory systems."""
        self._short_term = get_cache()
        self._initialized = False

    # ------------------------------------------------------------------
    # Initialization
    # ------------------------------------------------------------------

    def _ensure_tables(self) -> None:
        """Ensure database tables exist using canonical schemas from models.py (lazy init)."""
        if self._initialized:
            return

        try:
            from database.manager import get_database
            from database.models import (
                CREATE_COMMAND_HISTORY,
                CREATE_KNOWLEDGE_MEMORY,
                CREATE_SETTINGS,
            )

            db = get_database()
            db.create_table(CREATE_COMMAND_HISTORY)
            db.create_table(CREATE_KNOWLEDGE_MEMORY)
            db.create_table(CREATE_SETTINGS)

            self._initialized = True
            logger.debug("Memory tables initialized")
        except Exception as e:
            logger.warning(f"Could not initialize memory tables: {e}")

    # ------------------------------------------------------------------
    # Short-term memory (in-memory, TTL-based)
    # ------------------------------------------------------------------

    def remember(self, key: str, value: Any, ttl: int = 300) -> None:
        """
        Store a short-term memory (in-memory with TTL).

        Args:
            key: Memory key
            value: Value to remember
            ttl: TTL in seconds (default: 300 = 5 min)
        """
        self._short_term.set(f"memory:{key}", value, ttl=ttl)
        logger.debug(f"Remembered (short-term): {key}")

    def recall(self, key: str) -> Any | None:
        """
        Recall a short-term memory.

        Args:
            key: Memory key

        Returns:
            Value, or None if forgotten/expired
        """
        value = self._short_term.get(f"memory:{key}")
        if value is None:
            logger.debug(f"Could not recall (expired/missing): {key}")
        return value

    def forget(self, key: str) -> None:
        """Forget a short-term memory."""
        self._short_term.invalidate(f"memory:{key}")

    # ------------------------------------------------------------------
    # Long-term memory (SQLite-backed)
    # ------------------------------------------------------------------

    def remember_long(self, key: str, value: str) -> bool:
        """
        Store a long-term memory (persistent).

        Args:
            key: Memory key
            value: Value to remember

        Returns:
            True if successful
        """
        try:
            self._ensure_tables()
            from database.manager import get_database

            db = get_database()
            db.execute(
                "INSERT OR REPLACE INTO knowledge_memory (key, value, updated_at) VALUES (?, ?, ?)",
                (key, value, datetime.now().isoformat()),
            )
            logger.debug(f"Remembered (long-term): {key}")
            return True
        except Exception as e:
            logger.error(f"Failed to store long-term memory '{key}': {e}")
            return False

    def recall_long(self, key: str) -> str | None:
        """
        Recall a long-term memory.

        Args:
            key: Memory key

        Returns:
            Value string, or None if not found
        """
        try:
            self._ensure_tables()
            from database.manager import get_database

            db = get_database()
            row = db.fetch_one(
                "SELECT * FROM knowledge_memory WHERE key = ?",
                (key,),
            )
            return row["value"] if row else None
        except Exception as e:
            logger.error(f"Failed to recall long-term memory '{key}': {e}")
            return None

    def forget_long(self, key: str) -> bool:
        """Delete a long-term memory."""
        try:
            self._ensure_tables()
            from database.manager import get_database

            db = get_database()
            db.execute("DELETE FROM knowledge_memory WHERE key = ?", (key,))
            return True
        except Exception as e:
            logger.error(f"Failed to forget long-term memory '{key}': {e}")
            return False

    def list_memories(self) -> list[dict[str, Any]]:
        """List all long-term memories."""
        try:
            self._ensure_tables()
            from database.manager import get_database

            db = get_database()
            return db.fetch_all("SELECT * FROM knowledge_memory ORDER BY key")
        except Exception as e:
            logger.error(f"Failed to list memories: {e}")
            return []

    # ------------------------------------------------------------------
    # Conversation history
    # ------------------------------------------------------------------

    def store_conversation(
        self, command: str, action: str = "", target: str = "", success: bool = False
    ) -> bool:
        """
        Store a conversation entry in history.

        Args:
            command: The user's command text
            action: The parsed action
            target: The parsed target
            success: Whether execution was successful

        Returns:
            True if successful
        """
        try:
            self._ensure_tables()
            from database.manager import get_database

            db = get_database()
            db.execute(
                "INSERT INTO command_history (command, action, target, success, timestamp) "
                "VALUES (?, ?, ?, ?, ?)",
                (command, action, target, int(success), datetime.now().isoformat()),
            )
            return True
        except Exception as e:
            logger.error(f"Failed to store conversation: {e}")
            return False

    def get_history(self, limit: int = 50) -> list[dict[str, Any]]:
        """
        Get recent conversation history.

        Args:
            limit: Maximum number of entries

        Returns:
            List of history entries
        """
        try:
            self._ensure_tables()
            from database.manager import get_database

            db = get_database()
            return db.fetch_all(
                "SELECT * FROM command_history ORDER BY id DESC LIMIT ?",
                (limit,),
            )
        except Exception as e:
            logger.error(f"Failed to get history: {e}")
            return []

    def clear_history(self) -> bool:
        """Clear all conversation history."""
        try:
            self._ensure_tables()
            from database.manager import get_database

            db = get_database()
            db.execute("DELETE FROM command_history")
            return True
        except Exception as e:
            logger.error(f"Failed to clear history: {e}")
            return False

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def stats(self) -> dict[str, Any]:
        """Get memory statistics."""
        return {
            "short_term_size": self._short_term.size,
            "short_term_hit_rate": self._short_term.hit_rate,
            "long_term_memories": len(self.list_memories()),
        }


def build_memory_prompt() -> str | None:
    """
    Format every saved /remember fact as a system-prompt block.

    This is the "prompt injection" for memory: whatever the user stored with
    /remember is injected into the model's system prompt on the next chat, so
    Hermes actually remembers it. Returns None when nothing is saved.

    Returns:
        A block like "The user asked you to remember: ..." or None.
    """
    try:
        memories = get_memory().list_memories()
    except Exception:
        return None
    if not memories:
        return None
    lines = [f"- {m['key']}: {m['value']}" for m in memories]
    return (
        "The user asked you to remember the following facts. "
        "Treat them as true and refer to them when relevant:\n" + "\n".join(lines)
    )


# Global singleton instance
_memory: KnowledgeMemory | None = None


def get_memory() -> KnowledgeMemory:
    """
    Get the global KnowledgeMemory instance.

    Returns:
        KnowledgeMemory singleton
    """
    global _memory
    if _memory is None:
        _memory = KnowledgeMemory()
    return _memory
