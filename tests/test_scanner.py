"""Tests for skills/scanner/application_scanner.py.

Covers the Application data model serialization, ignore rules, and
merge priority logic. All tests are pure/unit-level and do not touch
the filesystem or scan real directories.
"""

from pathlib import Path

from skills.scanner.application_scanner import (
    GAME_DIRECTORIES,
    Application,
    merge_results,
    should_ignore,
)


class TestApplicationSerialization:
    """The category field must survive save/load round trips."""

    def test_to_dict_includes_category(self):
        app = Application(name="Steam", path=Path("C:/Steam/steam.exe"), category="game")
        data = app.to_dict()
        assert data["name"] == "Steam"
        assert data["path"] == str(Path("C:/Steam/steam.exe"))
        assert data["category"] == "game"

    def test_to_dict_default_category(self):
        app = Application(name="Chrome", path=Path("C:/Chrome/chrome.exe"))
        assert app.to_dict()["category"] == "application"

    def test_from_dict_round_trip_preserves_category(self):
        data = {
            "name": "Steam",
            "path": str(Path("C:/Steam/steam.exe")),
            "aliases": ["steam"],
            "category": "game",
        }
        app = Application.from_dict(data)
        assert app.category == "game"
        assert app.to_dict() == data

    def test_from_dict_defaults_category(self):
        data = {"name": "Chrome", "path": "C:/Chrome/chrome.exe"}
        app = Application.from_dict(data)
        assert app.category == "application"


class TestGameDirectories:
    """C:\\Games should be scanned for games."""

    def test_c_games_in_game_directories(self):
        assert Path("C:\\Games") in GAME_DIRECTORIES


class TestShouldIgnore:
    """Ignore rules should filter system and installer executables."""

    def test_ignores_system32(self):
        assert should_ignore(Path("C:/Windows/System32/cmd.exe")) is True

    def test_ignores_system32_case_insensitive(self):
        assert should_ignore(Path("C:/WINDOWS/system32/regedit.exe")) is True

    def test_allows_normal_app(self):
        assert should_ignore(Path("C:/Program Files/Google/Chrome/chrome.exe")) is False

    def test_ignores_installer(self):
        assert should_ignore(Path("C:/Apps/setup.exe")) is True

    def test_ignores_venv_folder(self):
        assert should_ignore(Path("C:/proj/.venv/bin/python.exe")) is True


class TestMergeResults:
    """Merge should prefer Program Files over lower-priority sources."""

    def test_program_files_beats_path(self):
        pf = Application(name="Git", path=Path("C:/Program Files/Git/git.exe"))
        path_app = Application(name="Git", path=Path("C:/Git/cmd/git.exe"))
        registry = merge_results([[path_app], [pf]])
        assert registry["git"].path == pf.path

    def test_unique_names_kept(self):
        a = Application(name="Alpha", path=Path("C:/A/a.exe"))
        b = Application(name="Beta", path=Path("C:/B/b.exe"))
        registry = merge_results([[a], [b]])
        assert set(registry.keys()) == {"alpha", "beta"}
