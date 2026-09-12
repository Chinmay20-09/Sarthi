#!/usr/bin/env python3
"""Pre-commit check: fail if database files are staged for commit.

Database files (*.db, *.db-wal, *.db-shm, *.sqlite*, ...) contain personal
data — chat transcripts, /remember facts, saved settings, command history —
so they must never be committed. This hook inspects the *staged* file list
(additions, modifications, renames) and fails if any of them match the
patterns. Staged deletions are allowed: that is how a database file gets
removed from the repository.

Usage:
    python scripts/check_no_db_staged.py

Exit codes:
    0  ok — no database files staged
    1  forbidden database file(s) staged
    2  not inside a git repository
"""

from __future__ import annotations

import fnmatch
import subprocess
import sys

# Same class of files the .gitignore SQLite section excludes. Kept in sync
# with .gitignore so the hook and the ignore rules can never drift apart.
DB_PATTERNS = (
    "*.db",
    "*.db-shm",
    "*.db-wal",
    "*.db-journal",
    "*.sqlite",
    "*.sqlite-shm",
    "*.sqlite-wal",
    "*.sqlite-journal",
    "*.sqlite3",
    "*.sqlite3-shm",
    "*.sqlite3-wal",
    "*.sqlite3-journal",
)


def main() -> int:
    try:
        root = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except subprocess.CalledProcessError:
        print("error: not inside a git repository", file=sys.stderr)
        return 2

    # Staged changes only, excluding deletions (removing a db file is the fix).
    proc = subprocess.run(
        [
            "git",
            "-C",
            root,
            "diff",
            "--cached",
            "--diff-filter=ACMR",
            "--name-only",
            "-z",
        ],
        check=True,
        capture_output=True,
    )
    staged = [name for name in proc.stdout.decode("utf-8", "replace").split("\0") if name]

    forbidden = [
        name for name in staged if any(fnmatch.fnmatch(name.lower(), p) for p in DB_PATTERNS)
    ]

    if not forbidden:
        print("ok: no database files staged")
        return 0

    print("error: database files are personal data and must not be committed:", file=sys.stderr)
    for name in forbidden:
        print(f"  - {name}", file=sys.stderr)
    print(
        "Remove them from the index with:\n"
        "    git rm --cached <file>\n"
        "and make sure the pattern is covered by .gitignore.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
