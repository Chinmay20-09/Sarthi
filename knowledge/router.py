"""
Knowledge Router — routes requests to the correct database or knowledge store.

The Knowledge Router determines WHERE a request should go:
    - Which database table to query
    - Which JSON knowledge base to read
    - Which cache to check
    - Which storage provider to use

ARCHITECTURE:
    The Router is part of the Knowledge Layer.
    It sits between the KnowledgeManager and the Database Layer.
    Skills never call the Router directly — they go through KnowledgeManager.

    The Router:
    - Knows which data lives where (SQLite vs JSON files vs future backends)
    - Routes search requests to the appropriate store
    - Normalizes responses into a consistent format
    - Handles schema translation between sources

Usage:
    from knowledge.router import KnowledgeRouter, get_router

    router = get_router()

    # Route an entity search
    result = router.route("find_entity", {"name": "Chrome", "category": "applications"})

    # Route a data write
    result = router.route("save_applications", {"applications": [...]})
"""

import logging
from enum import Enum
from typing import Any

from knowledge.cache import get_cache

logger = logging.getLogger(__name__)


class DataSource(Enum):
    """Where data is stored."""

    APPLICATIONS_JSON = "applications_json"
    WEBSITES_JSON = "websites_json"
    SQLITE_GITHUB = "sqlite_github"
    SQLITE_HISTORY = "sqlite_history"
    SQLITE_MEMORY = "sqlite_memory"
    SQLITE_SETTINGS = "sqlite_settings"
    CACHE_ONLY = "cache_only"
    UNKNOWN = "unknown"


class KnowledgeRouter:
    """
    Routes requests to the correct data store.

    Responsibilities:
        - Determine which data source handles a given request
        - Route requests to the appropriate handler
        - Normalize responses
        - Cache frequently requested data

    What this does NOT do:
        - Perform business logic or validation
        - Execute commands or launch applications
        - Make decisions about what to store
    """

    def __init__(self):
        """Initialize the router."""
        self.cache = get_cache()

    # ------------------------------------------------------------------
    # Routing
    # ------------------------------------------------------------------

    def route(self, operation: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """
        Route a request to the correct handler.

        Args:
            operation: Operation name (e.g., "find_entity", "save_applications")
            params: Operation parameters

        Returns:
            Dict with result data
        """
        params = params or {}
        source = self._resolve_source(operation, params)

        logger.debug(f"Routing '{operation}' -> {source.value}")

        try:
            if source == DataSource.APPLICATIONS_JSON:
                return self._handle_applications(operation, params)
            elif source == DataSource.WEBSITES_JSON:
                return self._handle_websites(operation, params)
            elif source == DataSource.SQLITE_GITHUB:
                return self._handle_github(operation, params)
            elif source == DataSource.SQLITE_HISTORY:
                return self._handle_history(operation, params)
            elif source == DataSource.SQLITE_MEMORY:
                return self._handle_memory(operation, params)
            elif source == DataSource.SQLITE_SETTINGS:
                return self._handle_settings(operation, params)
            elif source == DataSource.CACHE_ONLY:
                return self._handle_cache(operation, params)
            else:
                return {"success": False, "error": f"Unknown data source for: {operation}"}
        except Exception as e:
            logger.error(f"Router failed for '{operation}': {e}")
            return {"success": False, "error": str(e)}

    def _resolve_source(self, operation: str, params: dict[str, Any]) -> DataSource:
        """Determine which data source handles an operation."""
        op_lower = operation.lower()

        # Application operations
        if any(word in op_lower for word in ["application", "app_", "scan"]):
            return DataSource.APPLICATIONS_JSON

        # Website operations
        if any(word in op_lower for word in ["website", "site"]):
            return DataSource.WEBSITES_JSON

        # GitHub operations
        if any(word in op_lower for word in ["github", "project"]):
            return DataSource.SQLITE_GITHUB

        # History operations
        if any(word in op_lower for word in ["history"]):
            return DataSource.SQLITE_HISTORY

        # Memory operations
        if any(word in op_lower for word in ["memory"]):
            return DataSource.SQLITE_MEMORY

        # Settings operations
        if any(word in op_lower for word in ["setting", "config"]):
            return DataSource.SQLITE_SETTINGS

        # Cache operations
        if any(word in op_lower for word in ["cache"]):
            return DataSource.CACHE_ONLY

        return DataSource.UNKNOWN

    # ------------------------------------------------------------------
    # Handlers (delegate to KnowledgeLoader/Manager)
    # ------------------------------------------------------------------

    def _handle_applications(self, operation: str, params: dict[str, Any]) -> dict[str, Any]:
        """Route to applications knowledge base."""
        from knowledge.manager import get_manager

        manager = get_manager()

        if "find" in operation:
            name = params.get("name", "")
            return {"success": True, "data": manager.find_application(name)}
        elif "save" in operation:
            apps = params.get("applications", [])
            return {"success": manager.save_applications(apps)}
        elif "load" in operation:
            return {"success": True, "data": manager.load_applications()}
        return {"success": True, "data": manager.load_applications()}

    def _handle_websites(self, operation: str, params: dict[str, Any]) -> dict[str, Any]:
        """Route to websites knowledge base."""
        from knowledge.manager import get_manager

        manager = get_manager()

        if "find" in operation:
            name = params.get("name", "")
            return {"success": True, "data": manager.find_website(name)}
        elif "save" in operation:
            sites = params.get("websites", [])
            return {"success": manager.save_websites(sites)}
        elif "load" in operation:
            return {"success": True, "data": manager.load_websites()}
        return {"success": True, "data": manager.load_websites()}

    def _handle_github(self, operation: str, params: dict[str, Any]) -> dict[str, Any]:
        """Route to GitHub database tables."""
        from database.manager import get_database

        db = get_database()

        if "find" in operation:
            repo = params.get("name", "")
            row = db.fetch_one("SELECT * FROM github_projects WHERE name = ?", (repo,))
            return {"success": True, "data": row}
        elif "all" in operation:
            rows = db.fetch_all("SELECT * FROM github_projects ORDER BY name")
            return {"success": True, "data": rows}
        return {"success": False, "error": f"Unsupported github operation: {operation}"}

    def _handle_history(self, operation: str, params: dict[str, Any]) -> dict[str, Any]:
        """Route to history database tables."""
        from database.manager import get_database

        db = get_database()

        if "write" in operation or "save" in operation:
            entry = params.get("entry", {})
            db.execute(
                "INSERT INTO command_history (command, action, target, success, timestamp) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    entry.get("command", ""),
                    entry.get("action", ""),
                    entry.get("target", ""),
                    int(entry.get("success", False)),
                    entry.get("timestamp", ""),
                ),
            )
            return {"success": True}
        elif "load" in operation or "get" in operation:
            limit = params.get("limit", 50)
            rows = db.fetch_all(
                "SELECT * FROM command_history ORDER BY timestamp DESC LIMIT ?",
                (limit,),
            )
            return {"success": True, "data": rows}
        return {"success": False, "error": f"Unsupported history operation: {operation}"}

    def _handle_memory(self, operation: str, params: dict[str, Any]) -> dict[str, Any]:
        """Route to memory database tables."""
        from database.manager import get_database

        db = get_database()

        if "write" in operation or "save" in operation:
            key = params.get("key", "")
            value = params.get("value", "")
            db.execute(
                "INSERT OR REPLACE INTO knowledge_memory (key, value, updated_at) VALUES (?, ?, datetime('now'))",
                (key, str(value)),
            )
            return {"success": True}
        elif "get" in operation or "read" in operation:
            key = params.get("key", "")
            row = db.fetch_one("SELECT * FROM knowledge_memory WHERE key = ?", (key,))
            return {"success": True, "data": row}
        elif "all" in operation:
            rows = db.fetch_all("SELECT * FROM knowledge_memory ORDER BY key")
            return {"success": True, "data": rows}
        return {"success": False, "error": f"Unsupported memory operation: {operation}"}

    def _handle_settings(self, operation: str, params: dict[str, Any]) -> dict[str, Any]:
        """Route to settings database tables."""
        from database.manager import get_database

        db = get_database()

        if "write" in operation or "save" in operation:
            key = params.get("key", "")
            value = params.get("value", "")
            db.execute(
                "INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES (?, ?, datetime('now'))",
                (key, str(value)),
            )
            return {"success": True}
        elif "get" in operation or "read" in operation:
            key = params.get("key", "")
            row = db.fetch_one("SELECT * FROM settings WHERE key = ?", (key,))
            return {"success": True, "data": row}
        return {"success": False, "error": f"Unsupported settings operation: {operation}"}

    def _handle_cache(self, operation: str, params: dict[str, Any]) -> dict[str, Any]:
        """Handle cache-only operations."""
        if "clear" in operation:
            self.cache.clear()
            return {"success": True}
        elif "stats" in operation:
            return {
                "success": True,
                "data": {
                    "size": self.cache.size,
                    "stats": self.cache.stats,
                    "hit_rate": self.cache.hit_rate,
                },
            }
        return {"success": False, "error": f"Unsupported cache operation: {operation}"}


# Global singleton instance
_router: KnowledgeRouter | None = None


def get_router() -> KnowledgeRouter:
    """
    Get the global KnowledgeRouter instance.

    Returns:
        KnowledgeRouter singleton
    """
    global _router
    if _router is None:
        _router = KnowledgeRouter()
    return _router
