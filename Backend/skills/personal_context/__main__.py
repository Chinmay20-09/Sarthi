"""
Standalone personal-context skill entry point.

Usage (from anywhere with backend/ on sys.path):

    python -m skills.personal_context list
    python -m skills.personal_context get <field>
    python -m skills.personal_context check
    python -m skills.personal_context --help

This is a standalone entry point: it does not start the Sarthi API, the Brain,
or the skill registry. It reuses the exact same capability implementation the
PersonalContextSkill uses (get_field), reading from the local SQLite database.

Note: values live in the local SQLite database (database/sarthi.db). The
service only returns fields on the allowlist (SAFE_FIELDS); secret/blocked
fields are refused.
"""

import argparse
import sys

from skills.personal_context.fields import SAFE_FIELDS, DISPLAY_NAMES
from skills.personal_context.service import PersonalContextService

__all__ = ["main"]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Retrieve stored personal profile fields.",
        prog="python -m skills.personal_context",
    )
    parser.add_argument(
        "action",
        choices=["list", "get", "check"],
        help="What to do: list (available fields), get <field>, check.",
    )
    parser.add_argument(
        "field",
        nargs="?",
        default="",
        help="The field to retrieve (for `get`).",
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

    service = PersonalContextService()

    if args.action == "list":
        _print_available_fields()
        return 0

    if not args.field:
        print("ERROR: get requires a field name", file=sys.stderr)
        return 1

    result = service.get_field(args.field)

    if result.get("success"):
        field = result.get("field")
        value = result.get("value")
        print(f" {DISPLAY_NAMES.get(field, field)} = {value}")
        return 0

    print(f" {result.get('error', 'unknown error')}")
    return 1


def _print_available_fields() -> None:
    """List the fields this service can return."""
    print("Available personal fields:")
    categories = {}
    for field in SAFE_FIELDS:
        cats = ()
        # find category (implementation detail: uses FIELD_CATEGORIES)
        import sys
        sys.path.insert(0, ".")
        from skills.personal_context.fields import FIELD_CATEGORIES
        for cat, members in FIELD_CATEGORIES.items():
            if field in members:
                cats = (cat,)
                break
        for cat in cats:
            categories.setdefault(cat, []).append(field)

    for cat, members in sorted(categories.items()):
        print(f"  {cat}: {', '.join(sorted(members))}")


def _check_dependencies() -> int:
    """Verify the database file is accessible."""
    try:
        from database.manager import get_database

        db = get_database()
        row = db.fetch_one("SELECT key FROM settings LIMIT 1")
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
