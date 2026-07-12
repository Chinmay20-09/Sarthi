"""
Windows Application Scanner for Sarthi.

Scans Windows Start Menu shortcuts and game directories to build
a comprehensive registry of installed applications and games.

Responsibilities:
- Scan Windows Start Menu (.lnk shortcuts)
- Scan game directories for executables
- Resolve shortcuts to target executables
- Deduplicate by executable path
- Save results to applications.json
"""

import json
import logging
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional, Set
from datetime import datetime

try:
    import win32com.client
    WIN32COM_AVAILABLE = True
except ImportError:
    WIN32COM_AVAILABLE = False

from .config import ScannerConfig

logger = logging.getLogger(__name__)


class WindowsApplicationScanner:
    """Scanner for Windows applications and games."""

    def __init__(self):
        """Initialize the scanner."""
        self.applications: Dict[str, Dict] = {}
        self.seen_paths: Set[str] = set()
        self.scan_stats = {
            "applications": 0,
            "games": 0,
            "shortcuts_resolved": 0,
            "duplicates_skipped": 0,
        }

    def scan_start_menu(self) -> List[Dict]:
        """
        Scan Windows Start Menu for shortcuts.

        Scans both system and user Start Menu folders for .lnk files
        and resolves them to their target executables.

        Returns:
            List of discovered applications
        """
        applications = []
        paths_to_scan = [
            ScannerConfig.SYSTEM_START_MENU,
            ScannerConfig.USER_START_MENU,
        ]

        logger.info("Scanning Windows Start Menu...")

        for start_menu_path in paths_to_scan:
            if not start_menu_path.exists():
                logger.debug(f"Start Menu path does not exist: {start_menu_path}")
                continue

            logger.debug(f"Scanning: {start_menu_path}")
            shortcuts = self._find_shortcuts(start_menu_path)

            for shortcut_path in shortcuts:
                app = self._resolve_shortcut(shortcut_path)
                if app:
                    applications.append(app)
                    self.scan_stats["shortcuts_resolved"] += 1

        logger.info(
            f"Found {self.scan_stats['shortcuts_resolved']} "
            f"shortcuts in Start Menu"
        )
        return applications

   def scan_game_directories(self) -> List[Dict]:
    """
    Scan configured game directories.

    Each first-level folder is treated as one game.
    Only the first valid executable found inside each game folder is added.
    """

    games = []
    game_dirs = ScannerConfig.get_valid_game_directories()

    logger.info(f"Scanning {len(game_dirs)} game directories...")

    for root in game_dirs:

        if not root.exists():
            continue

        for game_folder in root.iterdir():

            if not game_folder.is_dir():
                continue

            exe_path = None

            # Find the first valid executable
            for exe in game_folder.rglob("*.exe"):

                name = exe.stem.lower()

                if any(word in name for word in (
                    "setup",
                    "uninstall",
                    "updater",
                    "update",
                    "helper",
                    "crashpad",
                    "service",
                    "launcherhelper",
                    "redist",
                    "vc_redist",
                    "dxsetup",
                )):
                    continue

                exe_path = exe.resolve()
                break

            if exe_path is None:
                continue

            target = str(exe_path).lower()

            if target in self.seen_paths:
                self.scan_stats["duplicates_skipped"] += 1
                continue

            self.seen_paths.add(target)

            games.append({
                "name": game_folder.name,
                "aliases": [],
                "path": str(exe_path),
                "category": "game",
            })

    logger.info(f"Found {len(games)} games in game directories")

    return games
    def _find_shortcuts(self, directory: Path) -> List[Path]:
        """
        Recursively find all .lnk shortcuts in a directory.

        Args:
            directory: Directory to search

        Returns:
            List of .lnk file paths
        """
        shortcuts = []
        try:
            for item in directory.rglob("*.lnk"):
                if item.is_file():
                    shortcuts.append(item)
        except PermissionError as e:
            logger.debug(f"Permission denied accessing {directory}: {e}")
        except Exception as e:
            logger.debug(f"Error scanning {directory}: {e}")

        return shortcuts

    def _resolve_shortcut(self, shortcut_path: Path) -> Optional[Dict]:
        """
        Resolve a Windows shortcut (.lnk) to its target executable.

        Uses COM API to read the shortcut properties.

        Args:
            shortcut_path: Path to .lnk file

        Returns:
            Application dict or None
        """
        if not WIN32COM_AVAILABLE:
            logger.debug(
                "win32com not available, skipping shortcut resolution"
            )
            return None

        try:
            shell = win32com.client.Dispatch("WScript.Shell")
            shortcut = shell.CreateShortCut(str(shortcut_path))

            target_path = shortcut.Targetpath
            if not target_path or not target_path.strip():
                logger.debug(f"Shortcut has no target: {shortcut_path}")
                return None

            target_path = Path(target_path).resolve()

            # Skip if not an executable
            if target_path.suffix.lower() not in {".exe", ".bat", ".cmd"}:
                return None

            # Skip if target doesn't exist
            if not target_path.exists():
                logger.debug(
                    f"Shortcut target does not exist: {target_path}"
                )
                return None

            # Get application name from shortcut or target
            app_name = shortcut_path.stem  # Use shortcut filename as name
            if not app_name or app_name.lower() == "uninstall":
                app_name = target_path.stem

            # Check for duplicates
            target_str = str(target_path).lower()
            if target_str in self.seen_paths:
                self.scan_stats["duplicates_skipped"] += 1
                return None

            self.seen_paths.add(target_str)

            return {
                "name": app_name,
                "aliases": [],
                "path": str(target_path),
                "category": "application",
            }

        except Exception as e:
            logger.debug(f"Error resolving shortcut {shortcut_path}: {e}")
            return None

    def _scan_directory(
        self, directory: Path, category: str = "game", depth: int = 0
    ) -> List[Dict]:
        """
        Recursively scan a directory for executables.

        Args:
            directory: Directory to scan
            category: Category to assign (application or game)
            depth: Current recursion depth

        Returns:
            List of application dicts
        """
        applications = []

        # Stop recursion if too deep
        if depth > ScannerConfig.MAX_RECURSION_DEPTH:
            logger.debug(
                f"Max recursion depth reached at {directory}"
            )
            return applications

        try:
            for item in directory.iterdir():
                # Skip hidden items
                if item.name.startswith("."):
                    continue

                # Recurse into directories
                if item.is_dir():
                    try:
                        found = self._scan_directory(
                            item, category=category, depth=depth + 1
                        )
                        applications.extend(found)
                    except PermissionError:
                        logger.debug(
                            f"Permission denied accessing {item}"
                        )
                    continue

                # Check if it's an executable
                if item.suffix.lower() in ScannerConfig.EXECUTABLE_EXTENSIONS:
                    app = self._process_executable(item, category)
                    if app:
                        applications.append(app)

        except PermissionError as e:
            logger.debug(f"Permission denied accessing {directory}: {e}")
        except Exception as e:
            logger.debug(f"Error scanning directory {directory}: {e}")

        return applications

    def _process_executable(self, exe_path: Path, category: str) -> Optional[Dict]:
        """
        Process an executable file.

        Args:
            exe_path: Path to executable
            category: Category to assign

        Returns:
            Application dict or None
        """
        try:
            # Check for duplicates by resolved path
            target_str = str(exe_path.resolve()).lower()
            if target_str in self.seen_paths:
                self.scan_stats["duplicates_skipped"] += 1
                return None

            self.seen_paths.add(target_str)

            # Use filename (without extension) as application name
            app_name = exe_path.stem

            return {
                "name": app_name,
                "aliases": [],
                "path": str(exe_path.resolve()),
                "category": category,
            }

        except Exception as e:
            logger.debug(f"Error processing executable {exe_path}: {e}")
            return None

    def deduplicate_applications(self) -> Dict[str, Dict]:
        """
        Deduplicate applications by executable path.

        Returns:
            Dictionary of deduplicated applications keyed by path
        """
        deduplicated = {}

        for app in self.applications.values():
            path = app["path"].lower()
            if path not in deduplicated:
                deduplicated[path] = app

        logger.debug(f"Deduplicated to {len(deduplicated)} unique applications")
        return deduplicated

    def save_applications(self, output_file: Optional[Path] = None) -> bool:
        """
        Save discovered applications to JSON file.

        Args:
            output_file: Path to save file (uses config default if None)

        Returns:
            True if successful
        """
        if output_file is None:
            output_file = ScannerConfig.OUTPUT_FILE

        try:
            # Organize by category
            result = {
                "version": "1.0",
                "last_scan": datetime.now().isoformat(),
                "statistics": self.scan_stats,
                "applications": [],
                "games": [],
            }

            for app in self.applications.values():
                if app["category"] == "game":
                    result["games"].append(app)
                else:
                    result["applications"].append(app)

            # Sort by name for consistency
            result["applications"].sort(key=lambda x: x["name"].lower())
            result["games"].sort(key=lambda x: x["name"].lower())

            output_file.parent.mkdir(parents=True, exist_ok=True)

            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(result, f, indent=2, ensure_ascii=False)

            logger.info(f"Saved results to {output_file}")
            return True

        except Exception as e:
            logger.error(f"Failed to save applications: {e}")
            return False

    def scan(self, output_file: Optional[Path] = None) -> Dict:
        """
        Execute complete application and game scan.

        Args:
            output_file: Optional path to save results

        Returns:
            Scan results dictionary
        """
        logger.info("Starting Windows application and game scan...")

        # Scan Start Menu
        start_menu_apps = self.scan_start_menu()
        self.scan_stats["applications"] = len(start_menu_apps)

        # Scan game directories
        games = self.scan_game_directories()
        self.scan_stats["games"] = len(games)

        # Combine all
        all_apps = start_menu_apps + games

        # Deduplicate
        self.applications = {app["path"].lower(): app for app in all_apps}
        deduped_count = len(self.applications)

        # Update stats
        self.scan_stats["duplicates_skipped"] = (
            len(all_apps) - deduped_count
        )

        logger.info("=" * 60)
        logger.info("Scan Complete - Statistics:")
        logger.info(f"  Start Menu Applications: {self.scan_stats['applications']}")
        logger.info(f"  Game Directory Games: {self.scan_stats['games']}")
        logger.info(f"  Shortcuts Resolved: {self.scan_stats['shortcuts_resolved']}")
        logger.info(f"  Duplicates Skipped: {self.scan_stats['duplicates_skipped']}")
        logger.info(f"  Total Unique Entries: {deduped_count}")
        logger.info("=" * 60)

        # Save to file
        if output_file:
            self.save_applications(output_file)
        else:
            self.save_applications()

        return {
            "success": True,
            "statistics": self.scan_stats,
            "total_unique": deduped_count,
            "output_file": str(ScannerConfig.OUTPUT_FILE),
        }


def main():
    """Main entry point for scanner."""
    # Set up logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # Create and run scanner
    scanner = WindowsApplicationScanner()
    result = scanner.scan()

    # Print summary
    print("\n" + "=" * 60)
    print("SCAN SUMMARY")
    print("=" * 60)
    for key, value in result["statistics"].items():
        print(f"{key.replace('_', ' ').title()}: {value}")
    print(f"Total Unique Entries: {result['total_unique']}")
    print(f"Output File: {result['output_file']}")
    print("=" * 60)

    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
