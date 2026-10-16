"""
Standalone project-tracker skill entry point.

Usage (from anywhere with backend/ on sys.path):

    python -m skills.project_tracker status
    python -m skills.project_tracker check
    python -m skills.project_tracker list
    python -m skills.project_tracker check --username YOURNAME
    python -m skills.project_tracker --check
    python -m skills.project_tracker --help

This is a standalone entry point: it does not start the Sarthi API, the Brain,
or the skill registry. It reuses the exact same capability implementation the
GitHubProjectSkill uses (project_status, check_new_repositories, sync).

Note: GitHub project tracking requires a GitHub username (and optionally a
personal access token). Run --check to verify the database is available.
Use --username to supply a GitHub username on the command line.
"""

import argparse
import os
import sys

from skills.project_tracker.main import GitHubProjectSkill

__all__ = ["main"]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Track GitHub projects and provide status summaries.",
        prog="python -m skills.project_tracker",
    )
    parser.add_argument(
        "action",
        choices=["status", "check", "sync", "list", "check", "check"],
        help="What to do: status (project summary), check (new repos), sync.",
    )
    parser.add_argument(
        "--username",
        default="",
        help="GitHub username (overrides env var SKILL_PROJECT_TRACKER_USERNAME).",
    )
    parser.add_argument(
        "--token",
        default="",
        help="GitHub personal access token (optional).",
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

    skill = GitHubProjectSkill(username=args.username or os.environ.get("SKILL_PROJECT_TRACKER_USERNAME", ""), token=args.token)

    try:
        if args.action == "status":
            repositories = skill.database.get_all_repositories()
            result = skill.project_status(repositories)
            print(f" {result}")
            cards = skill._project_cards(repositories)
            if cards:
                print(f"   {len(cards)} project(s) tracked")
            return 0

        if args.action == "check":
            result = skill.check_new_repositories()
            print(f" {result}")
            return 0

        if args.action == "sync":
            result = skill.sync_repositories()
            print(f" {result}")
            return 0

        if args.action == "list":
            repos = skill.database.get_all_repositories()
            print(f"Tracked projects ({len(repos)}):")
            for repo in repos:
                print(f"  - {repo.get('name')}")
            return 0

        return 1
    except Exception as e:  # noqa: BLE001
        print(f"ERROR: {e}", file=sys.stderr)
        return 1


def _check_dependencies() -> int:
    """Verify the database file is accessible and has the projects table."""
    try:
        from database.manager import get_database

        db = get_database()
        row = db.fetch_one("SELECT name FROM sqlite_master WHERE type='table' AND name='projects'")
        if row:
            count = db.fetch_one("SELECT COUNT(*) AS c FROM projects")["c"]
            print(f" Database OK: projects table ({count} project(s))")
        else:
            print(" Database OK: projects table not created yet")
        return 0
    except Exception as e:  # noqa: BLE001
        print(f" Database unavailable: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
