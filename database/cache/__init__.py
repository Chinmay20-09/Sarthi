"""Database caching.

- query_cache.py     — in-memory TTL query cache (QueryCache)
- browser_cache.py   — in-memory browser session cache (browser_cache)
"""

from .query_cache import QueryCache

__all__ = ["QueryCache"]
