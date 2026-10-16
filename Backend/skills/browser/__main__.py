"""
Standalone browser skill entry point.

Usage (from anywhere with backend/ on sys.path):

    python -m skills.browser open google
    python -m skills.browser search "python tutorial"
    python -m skills.browser play lofi
    python -m skills.browser list
    python -m skills.browser --check

This is a standalone entry point: it does not start the Sarthi API, the
Brain, or the skill registry. It reuses the exact same capability
implementation as the BrowserSkill, so search/play/open behave
identically from the CLI and from the skill.

Note: opening a real website in a browser requires a browser on the host
and the KnowledgeLayer website lookup for "open X". In test mode no
browser is opened and the result is reported.
"""

import argparse
import json
import sys
from pathlib import Path

from skills.browser.main import BrowserSkill

__all__ = ["main"]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Open websites, search, and play media in the browser.",
        prog="python -m skills.browser",
    )
    parser.add_argument(
        "action",
        choices=["open", "search", "play", "list", "check"],
        help="What to do: open <name>, search <query>, play <media>, list, or check.",
    )
    parser.add_argument(
        "target",
        nargs="?",
        default="",
        help="The website name, search query, or media query.",
    )
    parser.add_argument(
        "--site",
        default="",
        help="Site to search on (e.g. youtube, github).",
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="Test mode: no browser is opened, result is reported.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Verify dependencies are available and exit (no action).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.check:
        return _check_dependencies()

    if args.action == "list":
        _list_websites()
        return 0

    skill = BrowserSkill()

    try:
        if args.action == "open":
            result = _execute_open(skill, args.target, args.test)
        elif args.action == "search":
            result = _execute_search(skill, args.target, args.site, args.test)
        elif args.action == "play":
            result = _execute_play(skill, args.target, args.test)
        else:
            return 2
    except Exception as e:  # noqa: BLE001
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    if isinstance(result, dict) and result.get("success"):
        print(f"OK {result.get('status', 'executed')}: {result.get('message', '')}")
        print(f"   URL: {result.get('url', '')}")
        return 0
    else:
        print(f"FAIL {result.get('status', 'error')}: {result.get('error', 'unknown error')}")
        return 1


def _execute_open(skill: BrowserSkill, target: str, test: bool) -> dict:
    """Open a website by name/alias (reuses the skill's capability)."""
    if test:
        return skill._open_website(target)  # noqa: SLF001

    # Real mode: resolve the website via the KnowledgeLayer, then open.
    try:
        from skills.browser.main import _open_website

        # Use the browser skill's knowledge path (skills/knowledge/websites.json)
        from skills.knowledge.manager import KnowledgeManager

        km = KnowledgeManager()
        km.load_websites()
        website = km.find_website(target)
        if website is None:
            return {"success": False, "status": "not_found", "error": f"Website not found: {target}"}
        url = website.get("url") or ""
        if not url:
            return {"success": False, "status": "error", "error": f"No URL for website: {website.get('name')}"}
        import webbrowser

        webbrowser.open(url)
        return {
            "success": True,
            "status": "executed",
            "result": {"website": website.get("name"), "url": url},
        }
    except Exception as e:  # noqa: BLE001
        return {"success": False, "status": "error", "error": str(e)}


def _execute_search(skill: BrowserSkill, target: str, site: str, test: bool) -> dict:
    """Search Google or a specific site (reuses the skill's capability)."""
    if test:
        return skill._search(target, site)  # noqa: SLF001
    return skill._search(target, site)  # noqa: SLF001


def _execute_play(skill: BrowserSkill, target: str, test: bool) -> dict:
    """Play the first YouTube video for a query (reuses the skill's capability)."""
    if test:
        from skills.browser.main import _get_first_youtube_video

        first = _get_first_youtube_video(target)
        url = first or f"https://www.youtube.com/results?search_query={target.replace(' ', '+')}"
        return {
            "success": True,
            "status": "test_mode",
            "result": {"website": "YouTube", "url": url, "query": target, "test_mode": True},
        }
    return skill._play(target)  # noqa: SLF001


def _list_websites() -> None:
    """List known websites from the knowledge file."""
    websites_path = Path(__file__).resolve().parent.parent.parent / "knowledge" / "websites.json"
    if not websites_path.exists():
        print("No websites known.")
        return
    with open(websites_path, encoding="utf-8") as f:
        data = json.load(f)
    entities = data.get("entities") if isinstance(data, dict) else data
    for entry in entities:
        name = entry.get("name", entry.get("url", "unknown"))
        url = entry.get("url", "")
        print(f"  - {name}  ->  {url}")


def _check_dependencies() -> int:
    """Verify the browser skill's dependencies are available."""
    try:
        import webbrowser

        browsers = webbrowser._browsers if hasattr(webbrowser, "_browsers") else []
        print("BROWSER AVAILABLE (webbrowser module)")
        if browsers:
            print(f"   default browser: {browsers[0].name if hasattr(browsers[0], 'name') else browsers[0]}")
    except Exception as e:  # noqa: BLE001
        print(f"BROWSER UNAVAILABLE: {e}", file=sys.stderr)
        return 1

    websites_path = Path(__file__).resolve().parent.parent.parent / "knowledge" / "websites.json"
    if websites_path.exists():
        print("KNOWLEDGE FOUND (websites.json)")
    else:
        print("KNOWLEDGE MISSING (websites.json not found - will use Google search fallback)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
