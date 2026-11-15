"""Read-only YouTube search resolution helpers.

This module resolves a search phrase to a video URL. It never opens a browser;
the desktop client remains responsible for playback on the user's computer.
"""

from __future__ import annotations

import re
import urllib.request
from urllib.parse import quote_plus


def get_first_youtube_video_url(query: str) -> str | None:
    """Return the first video URL in YouTube's search page, if available."""
    search_url = "https://www.youtube.com/results?" + "search_query=" + quote_plus(query)
    request = urllib.request.Request(search_url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            html = response.read().decode("utf-8", errors="ignore")
        match = re.search(r'"videoId":"([a-zA-Z0-9_-]{11})"', html)
        if match:
            return f"https://www.youtube.com/watch?v={match.group(1)}"
    except Exception:
        # Search URL remains a useful fallback when YouTube is unavailable or
        # changes its page format.
        return None
    return None
