"""
Configuration for the Windows Application Scanner.

Defines game directories and scanner settings for Sarthi.
"""

from pathlib import Path
import os


class ScannerConfig:
    """Configuration for application scanning."""

    # Game directories to scan (can be configured per user)
    GAME_DIRECTORIES = [
        # Steam installation
        Path("C:\\Program Files (x86)\\Steam\\steamapps\\common"),
        # Epic Games
        Path("C:\\Program Files\\Epic Games"),
        # GOG Games
        Path("C:\\GOG Games"),
        # User-defined games folder
        Path.home() / "Games",
    ]

    # Start Menu folders
    # System Start Menu
    SYSTEM_START_MENU = Path(
        "C:\\ProgramData\\Microsoft\\Windows\\Start Menu\\Programs"
    )

    # User Start Menu
    USER_START_MENU = Path.home() / "AppData\\Roaming\\Microsoft\\Windows\\Start Menu\\Programs"

    # Output file for scanned applications
    OUTPUT_FILE = Path(__file__).parent / "applications.json"

    # Maximum recursion depth for directory scanning
    MAX_RECURSION_DEPTH = 10

    # File extensions to scan for in game directories
    EXECUTABLE_EXTENSIONS = {".exe", ".bat", ".cmd", ".com"}

    # Extensions to skip
    SKIP_EXTENSIONS = {".txt", ".ini", ".cfg", ".log", ".tmp"}

    @classmethod
    def get_valid_game_directories(cls) -> list:
        """
        Get list of game directories that actually exist.

        Returns:
            List of valid Path objects
        """
        valid_dirs = []
        for directory in cls.GAME_DIRECTORIES:
            if directory.exists() and directory.is_dir():
                valid_dirs.append(directory)
        return valid_dirs

    @classmethod
    def add_game_directory(cls, directory: Path) -> None:
        """
        Add a custom game directory to scan.

        Args:
            directory: Path object or string path
        """
        if isinstance(directory, str):
            directory = Path(directory)

        if directory not in cls.GAME_DIRECTORIES:
            cls.GAME_DIRECTORIES.append(directory)
