"""
Browser automation profile registry.

Browser Awareness launches Chrome for its runs. With a throwaway temporary
profile every session starts as a "guest" — no cookies, no logins — which is
safe but means the user has to sign in on every run. This module gives the
automation a PERSISTENT profile directory of its own: the path is stored as a
row in the ``browser_profiles`` table (sarthi.db), so the user logs in once
and every later browser session reuses that login. The user's real Chrome
profile is never touched.

Resolution order for a profile directory:

1. ``BROWSER_AWARENESS_PROFILE_DIR`` env var (explicit override, wins over
   the database so tests and one-off runs can point anywhere).
2. The ``default`` row in ``browser_profiles`` (created on first use).
3. ``None`` — the caller falls back to a throwaway temp profile.
"""

import os
from datetime import datetime
from pathlib import Path

from database.manager import DatabaseManager, get_database

PROFILE_TABLE = "browser_profiles"
DEFAULT_PROFILE_NAME = "default"

# Absolute directory (as a string) where automated browsing keeps its Chrome
# profile. Set it to pin a location; it wins over the database entry.
PROFILE_DIR_ENV = "BROWSER_AWARENESS_PROFILE_DIR"


def get_profile_dir(db: DatabaseManager | None = None) -> str | None:
    """Return the persistent profile directory for automated browsing, if any.

    Checks the env override first, then the ``default`` row in
    ``browser_profiles``. Returns ``None`` when neither is set — callers
    fall back to an isolated temporary profile.
    """
    override = os.environ.get(PROFILE_DIR_ENV, "").strip()
    if override:
        return str(Path(override).expanduser())

    db = db or get_database()
    row = db.fetch_one(f"SELECT value FROM {PROFILE_TABLE} WHERE name = ?", (DEFAULT_PROFILE_NAME,))
    value = str(row["value"] or "").strip() if row else ""
    return value or None


def ensure_default_profile(
    db: DatabaseManager | None = None, profile_dir: Path | None = None
) -> Path:
    """Register (or return) the persistent profile directory.

    Idempotent: the first call inserts the ``default`` row; later calls
    return the registered path without touching the existing entry, so a
    directory the user has already logged in through is never repointed.

    Args:
        db: database to use (defaults to the shared singleton).
        profile_dir: where to keep the profile. Defaults to
            ``Backend/skills/browser_awareness/.chrome-profile`` — colocated
            with the capability and git-ignored like the ai_chain profile.
    """
    db = db or get_database()
    if profile_dir is None:
        profile_dir = (
            Path(__file__).resolve().parent.parent
            / "skills"
            / "browser_awareness"
            / ".chrome-profile"
        )
    profile_dir = Path(profile_dir).expanduser().resolve()

    existing = get_profile_dir(db)
    if existing:
        return Path(existing)

    now = datetime.now().isoformat(timespec="seconds")
    db.execute(
        f"INSERT OR IGNORE INTO {PROFILE_TABLE} "
        "(name, value, created_at, updated_at) VALUES (?, ?, ?, ?)",
        (DEFAULT_PROFILE_NAME, str(profile_dir), now, now),
    )
    return profile_dir


def set_profile_dir(profile_dir: Path | str, db: DatabaseManager | None = None) -> Path:
    """Point the ``default`` profile at ``profile_dir`` (upsert).

    Use this to move the automation profile after the fact. The directory is
    created lazily by Chrome on first launch, not here.
    """
    db = db or get_database()
    profile_dir = Path(profile_dir).expanduser().resolve()
    now = datetime.now().isoformat(timespec="seconds")
    db.execute(
        f"INSERT INTO {PROFILE_TABLE} (name, value, created_at, updated_at) "
        "VALUES (?, ?, ?, ?) "
        "ON CONFLICT(name) DO UPDATE SET value = excluded.value, "
        "updated_at = excluded.updated_at",
        (DEFAULT_PROFILE_NAME, str(profile_dir), now, now),
    )
    return profile_dir
