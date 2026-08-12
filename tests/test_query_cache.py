"""Tests for database/cache/query_cache.py.

Tests the in-memory TTL-based query cache (QueryCache).
"""

import time

import pytest

from database.cache import QueryCache


@pytest.fixture
def cache():
    return QueryCache()


class TestGetSet:
    def test_get_missing_key(self, cache):
        """Getting a non-existent key returns None."""
        assert cache.get("nonexistent") is None

    def test_set_and_get(self, cache):
        """A set value should be retrievable."""
        cache.set("key1", "value1")
        assert cache.get("key1") == "value1"

    def test_overwrite_value(self, cache):
        """Overwriting a key should update the value."""
        cache.set("key", "old")
        cache.set("key", "new")
        assert cache.get("key") == "new"

    def test_complex_values(self, cache):
        """Cache should store complex types (dicts, lists)."""
        data = {"name": "test", "items": [1, 2, 3]}
        cache.set("complex", data)
        result = cache.get("complex")
        assert result == data
        assert result["name"] == "test"
        assert result["items"] == [1, 2, 3]


class TestTTL:
    def test_expired_entry(self, cache):
        """An expired entry should return None."""
        cache.set("short", "value", ttl_seconds=0)  # expires immediately
        # May need small sleep for timer granularity
        time.sleep(0.01)
        assert cache.get("short") is None

    def test_active_entry_not_expired(self, cache):
        """Entry within TTL should still be accessible."""
        cache.set("val", "data", ttl_seconds=60)
        assert cache.get("val") == "data"

    def test_expired_entry_removed(self, cache):
        """Expired entry should be removed from store."""
        cache.set("gone", "bye", ttl_seconds=0)
        time.sleep(0.01)
        cache.get("gone")  # triggers expiry check + removal
        assert "gone" not in cache._store
        assert "gone" not in cache._expiry


class TestSize:
    def test_size(self, cache):
        """size should reflect number of entries."""
        assert cache.size == 0
        cache.set("a", 1)
        assert cache.size == 1
        cache.set("b", 2)
        assert cache.size == 2

    def test_size_after_clear(self, cache):
        """size should be 0 after clear."""
        cache.set("a", 1)
        cache.set("b", 2)
        cache.clear()
        assert cache.size == 0


class TestInvalidate:
    def test_invalidate_all(self, cache):
        """Invalidate with no pattern clears all."""
        cache.set("a", 1)
        cache.set("b", 2)
        cache.invalidate()
        assert cache.size == 0

    def test_invalidate_pattern(self, cache):
        """Invalidate with pattern should clear matching keys."""
        cache.set("user:1", "alice")
        cache.set("user:2", "bob")
        cache.set("config:app", "settings")
        cache.invalidate(pattern="user:")
        assert cache.get("user:1") is None
        assert cache.get("user:2") is None
        assert cache.get("config:app") == "settings"

    def test_invalidate_pattern_no_match(self, cache):
        """Invalidate with non-matching pattern should not affect anything."""
        cache.set("keep_me", "safe")
        cache.invalidate(pattern="other:")
        assert cache.get("keep_me") == "safe"

    def test_invalidate_empty_cache(self, cache):
        """Invalidate on empty cache should not crash."""
        cache.invalidate()
        cache.invalidate(pattern="anything")
        assert cache.size == 0


class TestClear:
    def test_clear_removes_all(self, cache):
        """Clear should remove all entries."""
        cache.set("a", 1)
        cache.set("b", 2)
        cache.clear()
        assert cache.size == 0
        assert cache.get("a") is None

    def test_clear_empty_cache(self, cache):
        """Clear on empty cache should not crash."""
        cache.clear()
        assert cache.size == 0
