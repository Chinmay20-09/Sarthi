"""
Application Scanner for Sarthi.

MIGRATED from knowledge/scanners/ to skills/scanner/.
The scanner is now a proper BaseSkill for architectural consistency.

ARCHITECTURE:
    Scanning is a capability/ability (Skills layer).
    The scanner feeds data into the Knowledge Layer for persistence.
    No other module should scan applications directly.

Supports:
- .exe executables from Program Files, Start Menu, PATH
- .lnk shortcuts via VBScript resolution
- Game directories (Steam, Epic Games, GOG, C:\\Games)
- Smart deduplication with priority-based merging
- Automatic alias generation from metadata and display names
"""

import logging
import os
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


# =============================================================================
# Configuration
# =============================================================================

# Well-known application metadata for improved alias generation
APP_METADATA = {
    "code": {
        "display_name": "Visual Studio Code",
        "aliases": ["vs code", "vscode", "visual studio code"],
    },
    "chrome": {
        "display_name": "Google Chrome",
        "aliases": ["google chrome"],
    },
    "firefox": {
        "display_name": "Mozilla Firefox",
        "aliases": [],
    },
    "spotify": {
        "display_name": "Spotify",
        "aliases": [],
    },
    "discord": {
        "display_name": "Discord",
        "aliases": [],
    },
    "notepad": {
        "display_name": "Notepad",
        "aliases": [],
    },
    "notepad++": {
        "display_name": "Notepad++",
        "aliases": ["notepad plus plus"],
    },
    "steam": {
        "display_name": "Steam",
        "aliases": [],
    },
    "explorer": {
        "display_name": "File Explorer",
        "aliases": ["file explorer"],
    },
    "calc": {
        "display_name": "Calculator",
        "aliases": [],
    },
    "powershell": {
        "display_name": "PowerShell",
        "aliases": [],
    },
    "cmd": {
        "display_name": "Command Prompt",
        "aliases": ["command prompt"],
    },
}

# Executables to ignore during scanning
IGNORED_EXECUTABLES = {
    "setup.exe",
    "installer.exe",
    "install.exe",
    "uninstall.exe",
    "uninst.exe",
    "unins.exe",
    "unins000.exe",
    "update.exe",
    "updater.exe",
    "crashpad_handler.exe",
    "helper.exe",
    "service.exe",
}

IGNORED_FOLDERS = {
    ".venv",
    "venv",
    "site-packages",
    "scripts",
    "__pycache__",
    "python",
    "conda",
    "miniconda",
    "anaconda",
    "windowskits",
    "microsoft sdks",
}

# Game directories to scan
GAME_DIRECTORIES = [
    Path("C:\\Program Files (x86)\\Steam\\steamapps\\common"),
    Path("C:\\Program Files\\Epic Games"),
    Path("C:\\GOG Games"),
    Path("C:\\Games"),
    Path.home() / "Games",
]


# =============================================================================
# Data Model
# =============================================================================


@dataclass
class Application:
    """Represents a discovered application or game."""

    name: str
    path: Path
    aliases: list[str] = field(default_factory=list)
    category: str = "application"  # "application" or "game"

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "name": self.name,
            "aliases": self.aliases,
            "path": str(self.path),
            "category": self.category,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Application":
        """Create from dictionary."""
        return cls(
            name=data["name"],
            path=Path(data["path"]),
            aliases=data.get("aliases", []),
            category=data.get("category", "application"),
        )


# =============================================================================
# Helpers
# =============================================================================


def should_ignore(path: Path) -> bool:
    """Return True if this executable should not be indexed."""
    for part in path.parts:
        if part.lower() in IGNORED_FOLDERS:
            return True

    # Skip Windows system executables (System32 can appear on PATH).
    # as_posix() normalizes separators so this matches on both
    # backslash (Windows) and forward-slash (POSIX) paths.
    if "windows/system32" in path.as_posix().lower():
        return True

    filename = path.name.lower()
    if filename in IGNORED_EXECUTABLES:
        return True

    if any(
        word in filename
        for word in ("setup", "installer", "update", "uninstall", "helper", "crashpad", "converter")
    ):
        return True

    return False


def resolve_shortcut(lnk_path: Path) -> Path | None:
    """Resolve a .lnk shortcut to its target executable using VBScript."""
    try:
        script = f"""
        Dim shell
        Set shell = CreateObject("WScript.Shell")
        Dim link
        Set link = shell.CreateShortcut("{lnk_path}")
        WScript.Echo link.TargetPath
        """

        with tempfile.NamedTemporaryFile(suffix=".vbs", delete=False, mode="w") as f:
            f.write(script)
            script_path = f.name

        try:
            result = subprocess.run(
                ["cscript.exe", script_path],
                capture_output=True,
                text=True,
                timeout=5,
            )

            if result.returncode == 0:
                target = result.stdout.strip()
                if target and Path(target).exists():
                    return Path(target)
        finally:
            Path(script_path).unlink(missing_ok=True)

    except Exception as e:
        logger.debug(f"Failed to resolve shortcut {lnk_path}: {e}")

    return None


def get_display_name_from_exe(exe_path: Path) -> str | None:
    """Extract display name from executable file properties (Windows)."""
    try:
        from win32api import GetFileVersionInfo

        try:
            info = GetFileVersionInfo(str(exe_path), "\\")
            if "FileDescription" in info:
                return info["FileDescription"]
        except Exception:
            pass
    except ImportError:
        logger.debug("pywin32 not available for extracting display names")
    except Exception as e:
        logger.debug(f"Failed to extract display name from {exe_path}: {e}")

    return None


def generate_aliases(exe_name: str, display_name: str | None = None) -> list[str]:
    """Generate intelligent aliases for an application."""
    aliases: set[str] = set()
    exe_base = exe_name.lower().replace(".exe", "")

    # Check metadata for well-known apps
    if exe_base in APP_METADATA:
        metadata = APP_METADATA[exe_base]
        if display_name is None:
            fallback = metadata.get("display_name")
            if isinstance(fallback, str):
                display_name = fallback
        aliases.update(metadata.get("aliases", []))

    # Add base executable name
    if exe_name.lower() != "explorer.exe":
        aliases.add(exe_base)

    # Generate from display name
    if display_name:
        display_lower = display_name.lower()
        aliases.add(display_lower)

        parts = display_lower.split()
        if len(parts) > 1:
            aliases.add(display_lower)
            aliases.add(parts[0])

            if "visual studio" in display_lower and "code" in display_lower:
                aliases.add("vscode")
                aliases.add("vs code")

        if "chrome" in display_lower:
            aliases.add("chrome")
        if "firefox" in display_lower:
            aliases.add("firefox")
        if "notepad++" in display_lower or "notepad +" in display_lower:
            aliases.add("notepad++")
            aliases.add("notepad plus plus")

    return sorted(list(aliases))


# =============================================================================
# Scanners
# =============================================================================


def scan_directory(
    directory: Path, max_depth: int = 1, current_depth: int = 0
) -> list[Application]:
    """Scan a directory for executables (limited depth)."""
    applications: list[Application] = []

    if not directory.exists() or not directory.is_dir():
        return applications

    try:
        for item in directory.iterdir():
            try:
                if current_depth >= max_depth:
                    continue

                if item.is_file():
                    if item.suffix.lower() == ".exe":
                        if should_ignore(item):
                            continue

                        exe_name = item.stem
                        display_name = get_display_name_from_exe(item)
                        aliases = generate_aliases(item.name, display_name)

                        app = Application(
                            name=display_name or exe_name,
                            path=item,
                            aliases=aliases,
                        )
                        applications.append(app)

                    elif item.suffix.lower() == ".lnk":
                        target = resolve_shortcut(item)
                        if target and target.suffix.lower() == ".exe":
                            if should_ignore(target):
                                continue

                            exe_name = target.stem
                            display_name = get_display_name_from_exe(target)
                            aliases = generate_aliases(target.name, display_name)

                            app = Application(
                                name=display_name or exe_name,
                                path=target,
                                aliases=aliases,
                            )
                            applications.append(app)

                elif item.is_dir():
                    applications.extend(scan_directory(item, max_depth, current_depth + 1))

            except (PermissionError, OSError) as e:
                logger.debug(f"Skipped {item}: {e}")

    except (PermissionError, OSError) as e:
        logger.debug(f"Cannot scan {directory}: {e}")

    return applications


def scan_game_directories() -> list[Application]:
    """Scan configured game directories for installed games."""
    games = []
    existing_paths: set[str] = set()

    for root in GAME_DIRECTORIES:
        if not root.exists():
            continue

        logger.debug(f"Scanning games in: {root}")

        for game_folder in root.iterdir():
            if not game_folder.is_dir():
                continue

            exe_path = None
            for exe in game_folder.rglob("*.exe"):
                name = exe.stem.lower()
                if any(
                    word in name
                    for word in (
                        "setup",
                        "uninstall",
                        "updater",
                        "update",
                        "helper",
                        "crashpad",
                        "crashhandler",
                        "bootstrapper",
                        "service",
                        "launcherhelper",
                        "redist",
                        "vc_redist",
                        "dxsetup",
                    )
                ):
                    continue
                exe_path = exe.resolve()
                break

            if exe_path is None:
                continue

            target_path = str(exe_path).lower()
            if target_path in existing_paths:
                continue

            existing_paths.add(target_path)

            games.append(
                Application(
                    name=game_folder.name,
                    path=exe_path,
                    category="game",
                )
            )

    logger.info(f"Found {len(games)} games in game directories")
    return games


def scan_program_files() -> list[Application]:
    """Scan C:\\Program Files."""
    logger.info("Scanning C:\\Program Files...")
    return scan_directory(Path("C:\\Program Files"), max_depth=2)


def scan_program_files_x86() -> list[Application]:
    """Scan C:\\Program Files (x86)."""
    logger.info("Scanning C:\\Program Files (x86)...")
    return scan_directory(Path("C:\\Program Files (x86)"), max_depth=2)


def scan_local_programs() -> list[Application]:
    """Scan %LOCALAPPDATA%\\Programs."""
    logger.info("Scanning %LOCALAPPDATA%\\Programs...")
    local_appdata = Path(os.getenv("LOCALAPPDATA", ""))
    if not local_appdata.exists():
        return []

    programs_dir = local_appdata / "Programs"
    if not programs_dir.exists():
        return []

    return scan_directory(programs_dir, max_depth=2)


def scan_start_menu() -> list[Application]:
    """Scan Start Menu shortcuts."""
    logger.info("Scanning Start Menu...")
    applications: list[Application] = []

    # Current user Start Menu
    appdata = Path(os.getenv("APPDATA", ""))
    if appdata.exists():
        start_menu = appdata / "Microsoft" / "Windows" / "Start Menu" / "Programs"
        if start_menu.exists():
            applications.extend(scan_directory(start_menu, max_depth=3))

    # All users Start Menu
    program_data = Path(os.getenv("PROGRAMDATA", "C:\\ProgramData"))
    if program_data.exists():
        start_menu = program_data / "Microsoft" / "Windows" / "Start Menu" / "Programs"
        if start_menu.exists():
            applications.extend(scan_directory(start_menu, max_depth=3))

    return applications


def scan_path() -> list[Application]:
    """Scan executables in PATH environment variable."""
    logger.info("Scanning PATH...")
    applications: list[Application] = []
    path_env = os.getenv("PATH", "")

    for path_str in path_env.split(os.pathsep):
        try:
            path = Path(path_str)
            if path.exists() and path.is_dir():
                for item in path.iterdir():
                    try:
                        if item.suffix.lower() == ".exe":
                            if should_ignore(item):
                                continue

                            exe_name = item.stem
                            aliases = generate_aliases(item.name, None)

                            app = Application(
                                name=exe_name,
                                path=item,
                                aliases=aliases,
                            )
                            applications.append(app)
                    except (PermissionError, OSError):
                        pass
        except (PermissionError, OSError):
            pass

    return applications


# =============================================================================
# Merging
# =============================================================================


def _get_priority(path_str: str) -> int:
    """Determine merge priority based on path (lower = higher priority)."""
    upper = path_str.upper()
    if "PROGRAM FILES (X86)" in upper:
        return 1
    elif "PROGRAM FILES" in upper:
        return 0
    elif "LOCALAPPDATA" in upper:
        return 2
    elif "START MENU" in upper:
        return 3
    else:
        return 4


def merge_results(
    all_applications: list[list[Application]],
) -> dict[str, Application]:
    """
    Merge results from different scan locations.

    Preference order:
    1. Program Files
    2. Program Files (x86)
    3. LocalAppData
    4. Start Menu
    5. PATH
    """
    registry: dict[str, Application] = {}

    for app_list in all_applications:
        for app in app_list:
            app_key = app.name.lower()
            priority = _get_priority(str(app.path))

            if app_key not in registry or priority < _get_priority(str(registry[app_key].path)):
                registry[app_key] = app

    return registry


# =============================================================================
# Public API
# =============================================================================


def scan_all() -> list[dict]:
    """
    Execute full application and game discovery pipeline.

    Discovers:
    - Applications from Start Menu
    - Applications from LocalAppData Programs
    - Applications from Program Files
    - Applications from Program Files (x86)
    - Games from recognized game directories
    - Executables on PATH

    Returns:
        List of application dictionaries (not saved to file).
        KnowledgeManager decides how to persist.

    Note:
        Does NOT write JSON. Returns data for KnowledgeManager to handle.
    """
    logger.info("Starting application scan...")

    results = [
        scan_start_menu(),
        scan_local_programs(),
        scan_program_files(),
        scan_program_files_x86(),
        scan_game_directories(),
        scan_path(),
    ]

    registry = merge_results(results)

    logger.info(f"Discovered {len(registry)} unique applications and games")

    return [app.to_dict() for app in registry.values()]


if __name__ == "__main__":
    from utils.logger import setup_logging

    setup_logging(level="INFO")

    from knowledge.manager import get_manager

    manager = get_manager()

    if manager.refresh_applications():
        print("\nRefreshed applications successfully")
    else:
        print("\nFailed to refresh applications")
