"""
Simple in-memory query cache for Sarthi's DatabaseManager.

Reduces redundant database reads for frequently accessed,
rarely changed data.

Usage:
    cache = QueryCache()
    cache.get("key")
    cache.set("key", value, ttl_seconds=300)
    cache.invalidate("pattern*")
"""

import time
from typing import Any


class QueryCache:
    """
    Time-to-live (TTL) based in-memory cache for query results.

    Not intended for high-throughput caching.
    Used for reducing repeated reads of reference data.
    """

    def __init__(self):
        self._store: dict[str, Any] = {}
        self._expiry: dict[str, float] = {}

    def get(self, key: str) -> Any | None:
        """
        Get a cached value by key.

        Args:
            key: Cache key

        Returns:
            Cached value, or None if missing or expired
        """
        if key not in self._store:
            return None

        if self._is_expired(key):
            self._remove(key)
            return None

        return self._store[key]

    def set(self, key: str, value: Any, ttl_seconds: int = 300) -> None:
        """
        Set a cached value with TTL.

        Args:
            key: Cache key
            value: Value to cache
            ttl_seconds: Time to live in seconds (default: 5 minutes)
        """
        self._store[key] = value
        self._expiry[key] = time.time() + ttl_seconds

    def invalidate(self, pattern: str | None = None) -> None:
        """
        Invalidate cache entries.

        Args:
            pattern: If provided, invalidates keys starting with this string.
                     If None, clears entire cache.
        """
        if pattern is None:
            self._store.clear()
            self._expiry.clear()
            return

        keys_to_remove = [k for k in self._store if k.startswith(pattern)]
        for key in keys_to_remove:
            self._remove(key)

    def _is_expired(self, key: str) -> bool:
        """Check if a cache entry has expired."""
        expiry = self._expiry.get(key)
        return expiry is not None and time.time() > expiry

    def _remove(self, key: str) -> None:
        """Remove a cache entry."""
        self._store.pop(key, None)
        self._expiry.pop(key, None)

    @property
    def size(self) -> int:
        """Number of items in the cache."""
        return len(self._store)

    def clear(self) -> None:
        """Clear all cache entries."""
        self._store.clear()
        self._expiry.clear()
