"""
Standalone scanner skill entry point.

Usage (from anywhere with backend/ on sys.path):

    python -m skills.scanner

Discovers installed applications, games, and websites and prints them to
stdout. This is a standalone entry point: it does not start the Sarthi API,
the Brain, or the skill registry.

This reuses the exact same ``scan_all`` capability the Sarthi ScannerSkill
uses, so a scan in the terminal produces the same results as a scan from the
skill registry.
"""

import argparse
import sys

from skills.scanner.application_scanner import scan_all

__all__ = ["main"]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Discover installed applications, games, and websites.",
        prog="python -m skills.scanner",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Print only the discovered application names, one per line.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print results as JSON instead of a human-readable list.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Verify dependencies are available and exit (no scanning).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Entry point for `python -m skills.scanner`."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.check:
        return _check_dependencies()

    try:
        results = scan_all()
    except Exception as e:  # noqa: BLE001
        print(f"ERROR: scan failed: {e}", file=sys.stderr)
        return 1

    if args.json:
        import json

        print(json.dumps(results, indent=2, ensure_ascii=False))
    elif args.quiet:
        for app in results:
            print(app.get("name", ""))
    else:
        print(f"Found {len(results)} application(s):")
        for app in results:
            name = app.get("name", "unknown")
            path = app.get("path", "")
            category = app.get("category", "application")
            print(f"  - {name} ({category})" + (f" at {path}" if path else ""))

    return 0


def _check_dependencies() -> int:
    """The scanner needs only the standard library."""
    print("SCANNER DEPENDENCIES OK (standard library only)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
