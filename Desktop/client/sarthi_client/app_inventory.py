"""Device-owned inventory of Windows Start Menu and PATH applications.

The inventory is intentionally local to the signed-in Windows user. It is
used only to resolve explicit local launch requests; it is not an execution
API and does not accept arbitrary paths from user input.
"""

from __future__ import annotations

import os
import sqlite3
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

REFRESH_SECONDS = 24 * 60 * 60
ALIASES = {
    "calculator": ("calc", "windows calculator"),
    "google chrome": ("chrome",),
    "visual studio code": ("vscode", "vs code", "code"),
    "file explorer": ("explorer",),
    "notepad": (),
}


def _normalize(value: str) -> str:
    return " ".join("".join(ch.lower() if ch.isalnum() else " " for ch in value).split())


def inventory_path() -> Path:
    """Return the per-user SQLite path, outside the repository/backend."""
    base = os.environ.get("LOCALAPPDATA")
    if base:
        root = Path(base)
    else:
        root = Path.home() / ".local" / "share"
    return root / "Sarthi" / "device.db"


def _shortcut_roots() -> list[Path]:
    roots: list[Path] = []
    appdata = os.environ.get("APPDATA")
    programdata = os.environ.get("PROGRAMDATA")
    if appdata:
        roots.append(Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs")
    if programdata:
        roots.append(Path(programdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs")
    return roots


def _path_applications() -> list[tuple[str, str]]:
    """Discover executable entries on PATH without launching or resolving input."""
    found: dict[str, list[str]] = {}
    for raw_dir in os.environ.get("PATH", "").split(os.pathsep):
        directory = Path(raw_dir.strip('"'))
        if not directory.is_dir():
            continue
        try:
            for entry in directory.iterdir():
                if entry.is_file() and entry.suffix.lower() == ".exe":
                    paths = found.setdefault(_normalize(entry.stem), [])
                    resolved = str(entry)
                    if resolved not in paths:
                        paths.append(resolved)
        except OSError:
            continue
    return [(Path(path).stem, path) for paths in found.values() for path in paths]


def _discover() -> list[tuple[str, str]]:
    apps: dict[str, list[tuple[str, str]]] = {}
    for root in _shortcut_roots():
        if not root.is_dir():
            continue
        try:
            for shortcut in root.rglob("*.lnk"):
                if shortcut.is_file():
                    key = _normalize(shortcut.stem)
                    entry = (shortcut.stem, str(shortcut.resolve()))
                    choices = apps.setdefault(key, [])
                    if all(existing_path != entry[1] for _, existing_path in choices):
                        choices.append(entry)
        except OSError:
            continue
    for name, path in _path_applications():
        key = _normalize(name)
        choices = apps.setdefault(key, [])
        if all(existing_path != path for _, existing_path in choices):
            choices.append((name, path))
    return [entry for choices in apps.values() for entry in choices]


def _connect() -> sqlite3.Connection:
    path = inventory_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=5)
    db.execute(
        "CREATE TABLE IF NOT EXISTS applications ("
        "name TEXT NOT NULL, normalized_name TEXT NOT NULL, path TEXT NOT NULL UNIQUE, "
        "refreshed_at REAL NOT NULL)"
    )
    db.execute("CREATE TABLE IF NOT EXISTS inventory_meta (key TEXT PRIMARY KEY, value REAL NOT NULL)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_applications_name ON applications(normalized_name)")
    db.commit()
    return db


@contextmanager
def _database() -> Iterator[sqlite3.Connection]:
    db = _connect()
    try:
        with db:
            yield db
    finally:
        db.close()


def refresh_if_stale(force: bool = False) -> None:
    """Refresh local launch entries at first use and at most daily thereafter."""
    with _database() as db:
        row = db.execute("SELECT value FROM inventory_meta WHERE key = 'last_refresh'").fetchone()
        last = row[0] if row else None
        if not force and last is not None and time.time() - last < REFRESH_SECONDS:
            return
        now = time.time()
        discovered = _discover()
        db.execute("DELETE FROM applications")
        db.executemany(
            "INSERT OR IGNORE INTO applications(name, normalized_name, path, refreshed_at) "
            "VALUES (?, ?, ?, ?)",
            [(name, _normalize(name), path, now) for name, path in discovered if name],
        )
        db.execute(
            "INSERT INTO inventory_meta(key, value) VALUES ('last_refresh', ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (now,),
        )


def resolve_application(query: str) -> tuple[str, str] | None:
    """Resolve an exact display name or known alias; never use fuzzy guessing."""
    refresh_if_stale()
    wanted = _normalize(query)
    with _database() as db:
        rows = db.execute(
            "SELECT name, path FROM applications WHERE normalized_name = ?", (wanted,)
        ).fetchall()
        if not rows:
            alias_names = [
                _normalize(name) for name, values in ALIASES.items()
                if any(_normalize(alias) == wanted for alias in values)
            ]
            for candidate in alias_names:
                rows.extend(
                    db.execute(
                        "SELECT name, path FROM applications WHERE normalized_name = ?",
                        (candidate,),
                    ).fetchall()
                )
    rows = list({row[1]: row for row in rows}.values())
    if len(rows) != 1:
        return None
    return str(rows[0][0]), str(rows[0][1])
