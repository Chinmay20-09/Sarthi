"""
Standalone user-config skill entry point.

Usage (from anywhere with backend/ on sys.path):

    python -m skills.user_config get
    python -m skills.user_config set <username>
    python -m skills.user_config check
    python -m skills.user_config --help

This is a standalone entry point: it does not start the Sarthi API, the Brain,
or the skill registry. It reuses the exact same capability implementation the
UserConfigSkill uses (set_github_username / get_github_username), writing to
the local SQLite database.

Note: the database file (database/sarthi.db) must exist. Run --check to verify
the database is available before using the command.
"""

import argparse
import sys

from skills.user_config.main import UserConfigSkill

__all__ = ["main"]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Manage user configuration settings (GitHub username).",
        prog="python -m skills.user_config",
    )
    parser.add_argument(
        "action",
        choices=["get", "set", "check", "list"],
        help="What to do: get (current username), set <username>, check (db), list.",
    )
    parser.add_argument(
        "value",
        nargs="?",
        default="",
        help="The username to save (for `set`).",
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

    # Keep db arg available if needed
    db_path = args.db

    skill = UserConfigSkill()

    try:
        if args.action == "set":
            if not args.value:
                print("ERROR: set requires a username", file=sys.stderr)
                return 1
            success = skill.set_github_username(args.value)
            if success:
                print(f" Saved GitHub username: {args.value}")
                return 0
            print(" Could not save username", file=sys.stderr)
            return 1

        if args.action == "get":
            username = skill.get_github_username()
            if username:
                print(f" GitHub username: {username}")
                return 0
            print("️  No GitHub username configured yet")
            return 0

        if args.action == "list":
            print("Available settings: github_username")
            return 0

        return 1
    except Exception as e:  # noqa: BLE001
        print(f"ERROR: {e}", file=sys.stderr)
        return 1


def _check_dependencies() -> int:
    """Verify the SQLite database file is accessible and has the settings table."""
    try:
        from database.manager import get_database

        db = get_database()
        row = db.fetch_one("SELECT key, value FROM settings LIMIT 1")
        if row:
            print(f" Database OK: found setting '{row['key']}'")
        else:
            print(" Database OK: no settings yet")
        return 0
    except Exception as e:  # noqa: BLE001
        print(f" Database unavailable: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
