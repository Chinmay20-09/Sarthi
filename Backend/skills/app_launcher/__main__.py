"""
Standalone application-launcher skill entry point.

Usage (from anywhere with backend/ on sys.path):

    python -m skills.app_launcher launch <app-name-or-path>
    python -m skills.app_launcher launch <path> --force
    python -m skills.app_launcher list
    python -m skills.app_launcher check
    python -m skills.app_launcher --help

This is a standalone entry point: it does not start the Sarthi API, the Brain,
or the skill registry. It reuses the exact same capability implementation the
AppLauncherSkill uses (_launch_path), launching applications through the
DesktopHand.

Note: launching real applications requires a desktop/hand capability. Use
--test to preview what would be launched without executing anything.
"""

import argparse
import os
import sys

from skills.app_launcher.main import AppLauncherSkill

__all__ = ["main"]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Launch desktop applications by name or path.",
        prog="python -m skills.app_launcher",
    )
    parser.add_argument(
        "action",
        choices=["launch", "list", "check"],
        help="What to do: launch <app>, list known apps, check.",
    )
    parser.add_argument(
        "target",
        nargs="?",
        default="",
        help="Application name or full path to launch.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Launch regardless of favourites gate (Run Anyway).",
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="Test mode: report what WOULD be launched, do not execute.",
    )
    parser.add_argument(
        "--db",
        default="database/sarthi.db",
        help="Path to the SQLite database (default: database/sarthi.db).",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Verify the database is available and exit.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.check:
        return _check_dependencies()

    skill = AppLauncherSkill()

    if args.action == "list":
        return _list_applications(skill)

    if not args.target:
        print("ERROR: launch requires a target (app name or path)", file=sys.stderr)
        return 1

    try:
        if args.test:
            return _launch_test(skill, args.target, args.force)

        # Real mode
        if args.action == "launch":
            return _launch_real(skill, args.target, args.force)

        return 1
    except Exception as e:  # noqa: BLE001
        print(f"ERROR: {e}", file=sys.stderr)
        return 1


def _launch_test(skill: AppLauncherSkill, target: str, force: bool) -> int:
    """Test mode: find the app and report what would be launched."""
    app = skill.knowledge.find_application(target)
    if app is None:
        print(f" Application not found: {target}", file=sys.stderr)
        return 1

    app_path = app.get("path")
    app_name = app.get("name")
    app_status = app.get("app_status", "favourite")

    if app_status != "favourite" and not force:
        print(f"⚠️  {app_name} is '{app_status}' — use --force to launch (Run Anyway)")
        return 0

    print(f" Would launch: {app_name} at {app_path}")
    return 0


def _launch_real(skill: AppLauncherSkill, target: str, force: bool) -> int:
    """Launch an application for real."""
    from skills.app_launcher.main import _launch_path

    app = skill.knowledge.find_application(target)
    if app is None:
        print(f" Application not found: {target}", file=sys.stderr)
        return 1

    app_path = app.get("path")
    app_name = app.get("name")
    app_status = app.get("app_status", "favourite")

    if not app_path:
        print(f" No path found for application: {app_name}", file=sys.stderr)
        return 1

    if app_status != "favourite" and not force:
        print(f" {app_name} is '{app_status}' — use --force to launch (Run Anyway)", file=sys.stderr)
        return 1

    if app_path.lower().endswith((".exe", ".lnk", ".bat", ".cmd")):
        _launch_path(app_path)
        print(f" Launched: {app_name}")
        return 0

    print(f" Unsupported app type for launch: {app_path}", file=sys.stderr)
    return 1


def _list_applications(skill: AppLauncherSkill) -> int:
    """List known applications from the knowledge layer."""
    # Use the knowledge manager's list method
    from knowledge.manager import get_manager

    km = get_manager()
    apps = km.load_applications()
    if isinstance(apps, dict):
        apps = apps.get("applications", [])
    print(f"Tracked applications ({len(apps)}):")
    for app in apps[:50]:
        name = app.get("name", "unknown")
        status = app.get("app_status", "favourite")
        path = app.get("path", "")
        print(f"  - {name} ({status})" + (f"  -> {path}" if path else ""))
    if len(apps) > 50:
        print(f"  ... and {len(apps) - 50} more")
    return 0


def _check_dependencies() -> int:
    """Verify the knowledge layer can provide applications."""
    try:
        from knowledge.manager import get_manager

        km = get_manager()
        apps = km.load_applications()
        count = len(apps) if apps else 0
        print(f" Knowledge OK: {count} application(s)")
        return 0
    except Exception as e:  # noqa: BLE001
        print(f" Knowledge unavailable: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
