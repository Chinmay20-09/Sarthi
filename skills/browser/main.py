"""
Browser Skill for Sarthi.

Opens websites in the default browser via the Knowledge Layer.
Uses injected KnowledgeManager via self.knowledge (DI pattern).

ARCHITECTURE:
    This skill communicates ONLY through the Knowledge Layer.
    It never accesses databases or JSON files directly.
    Dependencies are injected via BaseSkill constructor.
"""

import logging
import re
import urllib.request
import webbrowser
from typing import Any

from brain.intent import Intent
from brain.modes import get_test_mode
from skills.base import BaseSkill

logger = logging.getLogger(__name__)


class BrowserSkill(BaseSkill):
    """
    Browser skill.

    Opens websites by name or alias in the default browser.
    Uses Knowledge Layer for website lookup.

    Usage:
        skill = BrowserSkill(knowledge_manager=manager)
        result = skill.execute(Intent(action="open", target="google"))
    """

    name = "browser"
    description = "Opens websites in the default browser via the Knowledge Layer"
    version = "1.0.0"

    # ------------------------------------------------------------------
    # BaseSkill interface
    # ------------------------------------------------------------------

    def execute(self, intent: Intent) -> dict[str, Any]:
        """
        Execute a website open, search, or play action.

        Args:
            intent: Parsed Intent with action and target

        Returns:
            Dict with execution results
        """
        action = intent.action.lower() if intent.action else ""
        target = intent.target if intent.target else ""

        if action in ("open", "launch", "start", "go"):
            return self._open_website(target)

        if action == "search":
            # "open X and search Q" sets intent.site so the search runs on
            # the opened site (e.g. youtube.com/results) when it is a
            # website, and falls back to Google for apps like Chrome.
            site = getattr(intent, "site", "") or ""
            return self._search(target, site=site)

        if action == "play":
            return self._play(target)

        return {
            "success": False,
            "status": "unknown_action",
            "error": f"Browser does not support action: {action}",
        }

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def _search(self, target: str, site: str = "") -> dict[str, Any]:
        """
        Search on a website or Google.

        "search YouTube"  → opens youtube.com/results?search_query=...
        "search python"   → opens google.com/search?q=...
        "search GitHub python" → opens github.com/search?q=...
        "open youtube and search AI" (site="youtube") → opens
        youtube.com/results?search_query=AI; a non-website site (an app
        like "chrome") falls back to Google.
        """
        logger.debug(f"Searching: {target}")
        target = target.strip()
        if not target:
            return {"success": False, "status": "error", "error": "No search query provided"}

        # An explicit site (from "open X and search Q") takes priority.
        if site:
            website = self.knowledge.find_website(site)
            if website and website.get("url"):
                return self._search_on_site(website, target)
            return self._google_search(target)

        # Check if target contains a known website name first
        words = target.split()
        if len(words) > 1:
            potential_site = words[0]
            query = " ".join(words[1:])
            website = self.knowledge.find_website(potential_site)
            if website and website.get("url"):
                return self._search_on_site(website, query)

        # Try the whole target as a website name (e.g. "search YouTube" with no query)
        website = self.knowledge.find_website(target)
        if website and website.get("url"):
            return self._search_on_site(website, target)

        # Default: Google search
        return self._google_search(target)

    def _search_on_site(self, website: dict, query: str) -> dict[str, Any]:
        """Search on a specific website."""
        url = website["url"]
        name = website.get("name", "")

        # Build search URL based on the site
        search_urls = {
            "youtube.com": f"https://www.youtube.com/results?search_query={query.replace(' ', '+')}",
            "github.com": f"https://github.com/search?q={query.replace(' ', '+')}&type=repositories",
            "google.com": f"https://www.google.com/search?q={query.replace(' ', '+')}",
            "stackoverflow.com": f"https://stackoverflow.com/search?q={query.replace(' ', '+')}",
        }

        # Find matching URL
        search_url = None
        for site_domain, site_url in search_urls.items():
            if site_domain in url.lower():
                search_url = site_url
                break

        if not search_url:
            # Generic: append search path
            base = url.rstrip("/")
            search_url = f"{base}/search?q={query.replace(' ', '+')}"

        # For YouTube searches, try to play the first video directly
        if "youtube.com" in url.lower():
            first_video_url = self._get_first_youtube_video(query)
            if first_video_url:
                if get_test_mode():
                    return {
                        "success": True,
                        "status": "test_mode",
                        "result": {
                            "website": name,
                            "url": first_video_url,
                            "query": query,
                            "test_mode": True,
                        },
                    }
                webbrowser.open(first_video_url)
                return {
                    "success": True,
                    "status": "executed",
                    "result": {
                        "website": name,
                        "url": first_video_url,
                        "query": query,
                        "action": "playing",
                    },
                }

        if get_test_mode():
            return {
                "success": True,
                "status": "test_mode",
                "result": {"website": name, "url": search_url, "query": query, "test_mode": True},
            }

        webbrowser.open(search_url)
        return {
            "success": True,
            "status": "executed",
            "result": {"website": name, "url": search_url, "query": query},
        }

    def _get_first_youtube_video(self, query: str) -> str | None:
        """Fetch the first YouTube video URL for a search query without an API key."""
        try:
            search_url = f"https://www.youtube.com/results?search_query={query.replace(' ', '+')}"
            req = urllib.request.Request(search_url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                html = resp.read().decode("utf-8", errors="ignore")
            # Extract video IDs from the rendered page data
            match = re.search(r'"videoId":"([a-zA-Z0-9_-]{11})"', html)
            if match:
                return f"https://www.youtube.com/watch?v={match.group(1)}"
        except Exception as e:
            logger.debug(f"Could not fetch first YouTube video: {e}")
        return None

    def _google_search(self, query: str) -> dict[str, Any]:
        """Perform a Google search."""
        url = f"https://www.google.com/search?q={query.replace(' ', '+')}"
        if get_test_mode():
            return {
                "success": True,
                "status": "test_mode",
                "result": {"website": "Google", "url": url, "query": query, "test_mode": True},
            }
        webbrowser.open(url)
        return {
            "success": True,
            "status": "executed",
            "result": {"website": "Google", "url": url, "query": query},
        }

    # ------------------------------------------------------------------
    # Play
    # ------------------------------------------------------------------

    def _play(self, target: str) -> dict[str, Any]:
        """Play media on YouTube or Spotify.

        "play lofi"      → opens youtube.com/watch?v=... (first video)
        "play music"     → opens youtube.com/watch?v=... (first video)
        """
        logger.debug(f"Playing: {target}")
        target = target.strip()
        if not target:
            return {"success": False, "status": "error", "error": "No media query provided"}

        # Try to get the first video directly
        first_video_url = self._get_first_youtube_video(target)
        url = (
            first_video_url
            or f"https://www.youtube.com/results?search_query={target.replace(' ', '+')}"
        )

        if get_test_mode():
            return {
                "success": True,
                "status": "test_mode",
                "result": {"website": "YouTube", "url": url, "query": target, "test_mode": True},
            }
        webbrowser.open(url)
        return {
            "success": True,
            "status": "executed",
            "result": {
                "website": "YouTube",
                "url": url,
                "query": target,
                "action": "playing" if first_video_url else "searching",
            },
        }

    # ------------------------------------------------------------------
    # Website opening
    # ------------------------------------------------------------------

    def _open_website(self, target: str) -> dict[str, Any]:
        """
        Open a website by name or alias.

        Uses self.knowledge for entity lookup (DI pattern).
        """
        logger.debug(f"Opening website: {target}")

        target = target.lower().strip()
        if not target:
            return {
                "success": False,
                "status": "error",
                "error": "No target specified",
            }

        try:
            website = self.knowledge.find_website(target)

            if website is None:
                return {
                    "success": False,
                    "status": "not_found",
                    "error": f"Website not found: {target}",
                }

            url = website.get("url")
            name = website.get("name")

            if not url:
                return {
                    "success": False,
                    "status": "error",
                    "error": f"No URL found for website: {name}",
                }

            if get_test_mode():
                logger.info(f"[TEST] Would open {name} at {url}")
                return {
                    "success": True,
                    "status": "test_mode",
                    "result": {"website": name, "url": url, "test_mode": True},
                }

            webbrowser.open(url)
            logger.info(f"Opened {name} at {url}")

            return {
                "success": True,
                "status": "executed",
                "result": {"website": name, "url": url},
            }

        except Exception as e:
            logger.error(f"Error opening website: {e}")
            return {
                "success": False,
                "status": "error",
                "error": str(e),
            }
