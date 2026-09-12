"""
Knowledge Cache — centralized caching for Sarthi's Knowledge Layer.

Provides TTL-based caching for frequently accessed knowledge data.
Reduces redundant JSON reads and database queries.

ARCHITECTURE:
    Knowledge Cache lives in the Knowledge Layer.
    It caches loaded entities, search results, and resolved names.

    The Cache is NOT a database — it has no persistence.
    It simply keeps recently used data in memory for fast access.

Usage:
    from knowledge.cache import get_cache

    cache = get_cache()

    # Cache some data (default TTL: 300 seconds)
    cache.set("apps", app_list)

    # Retrieve cached data
    apps = cache.get("apps")

    # Invalidate when data changes
    cache.invalidate("apps")
    cache.clear()  # Clear all
"""

import logging
import time
from typing import Any

logger = logging.getLogger(__name__)


class KnowledgeCache:
    """
    TTL-based in-memory cache for the Knowledge Layer.

    Designed for caching entity data, search results, and
    frequently accessed knowledge. Not for high-throughput or
    persistent storage.

    Attributes:
        default_ttl: Default TTL in seconds (5 minutes)
    """

    def __init__(self, default_ttl: int = 300):
        """
        Initialize the cache.

        Args:
            default_ttl: Default TTL in seconds (default: 300 = 5 min)
        """
        self._store: dict[str, Any] = {}
        self._expiry: dict[str, float] = {}
        self._stats: dict[str, int] = {"hits": 0, "misses": 0, "sets": 0, "invalidates": 0}
        self._default_ttl = default_ttl

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def get(self, key: str) -> Any | None:
        """
        Get a cached value by key.

        Args:
            key: Cache key

        Returns:
            Cached value, or None if missing or expired
        """
        if key not in self._store:
            self._stats["misses"] += 1
            return None

        if self._is_expired(key):
            self._remove(key)
            self._stats["misses"] += 1
            return None

        self._stats["hits"] += 1
        return self._store[key]

    def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        """
        Set a cached value with TTL.

        Args:
            key: Cache key
            value: Value to cache
            ttl: TTL in seconds. Uses default_ttl if None.
        """
        self._store[key] = value
        self._expiry[key] = time.time() + (ttl if ttl is not None else self._default_ttl)
        self._stats["sets"] += 1

    def has(self, key: str) -> bool:
        """Check if a key exists and is not expired."""
        if key not in self._store:
            return False
        if self._is_expired(key):
            self._remove(key)
            return False
        return True

    # ------------------------------------------------------------------
    # Invalidation
    # ------------------------------------------------------------------

    def invalidate(self, pattern: str | None = None) -> None:
        """
        Invalidate cache entries.

        Args:
            pattern: If provided, invalidates keys starting with this string.
                    If None, clears entire cache.
        """
        self._stats["invalidates"] += 1

        if pattern is None:
            self._store.clear()
            self._expiry.clear()
            return

        keys_to_remove = [k for k in self._store if k.startswith(pattern)]
        for key in keys_to_remove:
            self._remove(key)

    def clear(self) -> None:
        """Clear all cache entries."""
        self._store.clear()
        self._expiry.clear()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _is_expired(self, key: str) -> bool:
        """Check if a cache entry has expired."""
        expiry = self._expiry.get(key)
        return expiry is not None and time.time() > expiry

    def _remove(self, key: str) -> None:
        """Remove a cache entry."""
        self._store.pop(key, None)
        self._expiry.pop(key, None)

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def size(self) -> int:
        """Number of entries in the cache."""
        return len(self._store)

    @property
    def stats(self) -> dict[str, int]:
        """Cache statistics (hits, misses, sets, invalidates)."""
        return dict(self._stats)

    @property
    def hit_rate(self) -> float:
        """Cache hit rate as a percentage."""
        total = self._stats["hits"] + self._stats["misses"]
        if total == 0:
            return 0.0
        return (self._stats["hits"] / total) * 100


# Global singleton instance
_cache: KnowledgeCache | None = None


def get_cache() -> KnowledgeCache:
    """
    Get the global KnowledgeCache instance.

    Returns:
        KnowledgeCache singleton
    """
    global _cache
    if _cache is None:
        _cache = KnowledgeCache()
    return _cache
