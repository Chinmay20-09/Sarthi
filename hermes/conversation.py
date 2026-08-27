"""
Conversation history — per-session memory for Hermes chat.

Hermes is stateless per request; this store gives it a short-term memory so
it can reference earlier turns in a session. History is persisted to the
project SQLite database (via DatabaseManager) so it survives server restarts;
the sandbox remains the durable record of every task.

Design:
    - Keyed by session_id (client-supplied), with a sensible default.
    - Thread-safe (FastAPI runs sync endpoints in a threadpool).
    - Capped per session so the context window stays bounded.
    - Two modes:
        * db=None          — in-memory only (used by tests / transient stores)
        * db=DatabaseManager — turns are stored in the conversation_messages
          table and reloaded on the next store instance (or restart).
"""

import threading

from database.manager import DatabaseManager, get_database
from database.models import CREATE_CONVERSATION_MESSAGES

# Default session used when the client does not supply one.
DEFAULT_SESSION = "default"

# Max messages remembered per session (user + assistant turns combined).
# Keeps the context window bounded without truncating a long chat too hard.
MAX_HISTORY_MESSAGES = 20


class ConversationStore:
    """Thread-safe, capped message history per session.

    With ``db=None`` the store keeps everything in memory (useful for tests
    and transient stores). With a ``DatabaseManager`` it persists every turn
    to the ``conversation_messages`` table, so a new store instance (or a
    server restart) sees the same history.
    """

    def __init__(
        self,
        max_messages: int = MAX_HISTORY_MESSAGES,
        db: DatabaseManager | None = None,
    ):
        self._max_messages = max_messages
        self._db = db
        self._sessions: dict[str, list[dict]] = {}
        self._lock = threading.Lock()
        if self._db is not None:
            self._db.create_table(CREATE_CONVERSATION_MESSAGES)

    # ------------------------------------------------------------------
    # History access
    # ------------------------------------------------------------------

    def get_history(self, session_id: str) -> list[dict]:
        """
        Return the session's prior turns, oldest first.

        Each entry is {"role": "user"|"assistant", "content": ...}.
        Returns a copy so callers can't mutate the store.
        """
        if self._db is None:
            with self._lock:
                return list(self._sessions.get(session_id, []))

        rows = self._db.fetch_all(
            "SELECT role, content FROM conversation_messages WHERE session_id = ? ORDER BY id ASC",
            (session_id,),
        )
        return [{"role": row["role"], "content": row["content"]} for row in rows]

    def add_turn(self, session_id: str, role: str, content: str) -> None:
        """Append a turn, trimming oldest messages over the cap."""
        if self._db is None:
            with self._lock:
                turns = self._sessions.setdefault(session_id, [])
                turns.append({"role": role, "content": content})
                if len(turns) > self._max_messages:
                    del turns[: len(turns) - self._max_messages]
            return

        with self._lock:
            self._db.execute(
                "INSERT INTO conversation_messages (session_id, role, content, created_at) "
                "VALUES (?, ?, ?, datetime('now'))",
                (session_id, role, content),
            )
            # Keep only the newest max_messages turns for this session.
            self._db.execute(
                "DELETE FROM conversation_messages WHERE session_id = ? AND id NOT IN "
                "(SELECT id FROM conversation_messages WHERE session_id = ? "
                "ORDER BY id DESC LIMIT ?)",
                (session_id, session_id, self._max_messages),
            )

    def clear(self, session_id: str) -> None:
        """Forget all history for a session (e.g. a 'forget' command)."""
        if self._db is None:
            with self._lock:
                self._sessions.pop(session_id, None)
            return

        with self._lock:
            self._db.execute(
                "DELETE FROM conversation_messages WHERE session_id = ?",
                (session_id,),
            )


# ----------------------------------------------------------------------
# Default store (singleton) — persisted to the project database
# ----------------------------------------------------------------------

_store: ConversationStore | None = None


def get_conversation_store() -> ConversationStore:
    """Get the global ConversationStore, creating it on first use.

    The singleton is backed by the shared project database so conversation
    history survives server restarts.
    """
    global _store
    if _store is None:
        _store = ConversationStore(db=get_database())
    return _store
