"""
Database package for Sarthi — centralized data storage.

Every skill uses DatabaseManager instead of creating its own connections.
This prevents duplicated registries and scattered database files.

ARCHITECTURE:
    manager.py    — DatabaseManager: SQLite connection + query API
    models.py     — Shared table schemas and dataclass models
    cache/        — Browser session caching
                    (browser_cache.py: BrowserCache)

USAGE:
    from database.manager import get_database, DatabaseManager

    # Singleton instance (simple)
    db = get_database()
    db.execute("INSERT INTO table ...", (val1, val2))
    rows = db.fetch_all("SELECT * FROM table")

    # Fresh instance (advanced)
    db = DatabaseManager(path / "custom.db")
"""

from .manager import DatabaseManager, get_database

__all__ = ["DatabaseManager", "get_database"]
