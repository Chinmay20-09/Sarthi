"""
Application Scanner for Sarthi.

Discovers installed applications from standard Windows locations and generates
a knowledge base of applications with automatic alias generation.

Supports .exe and .lnk file discovery with smart deduplication.
"""

import json
import logging
import os
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set
from dataclasses import dataclass, field, asdict

logger = logging.getLogger(__name__)


# Application metadata for improving alias generation
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


@dataclass
class Application:
    """Represents a discovered application."""

    name: str
    path: Path
    aliases: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "name": self.name,
            "aliases": self.aliases,
            "path": str(self.path),
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "Application":
        """Create from dictionary."""
        return cls(
            name=data["name"],
            path=Path(data["path"]),
            aliases=data.get("aliases", []),
        )


def should_ignore(path: Path) -> bool:
    """
    Return True if this executable should not be indexed.
    """

    # Ignore folders
    for part in path.parts:
        if part.lower() in IGNORED_FOLDERS:
            return True

    filename = path.name.lower()

    if filename in IGNORED_EXECUTABLES:
        return True

    if any(
        word in filename
        for word in (
            "setup",
            "installer",
            "update",
            "uninstall",
            "helper",
            "crashpad",
            "converter",
        )
    ):
        return True

    return False


def resolve_shortcut(lnk_path: Path) -> Optional[Path]:
    """Resolve a .lnk shortcut to its target executable."""
    try:
        # Use Windows Script Host to resolve shortcut
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


def get_display_name_from_exe(exe_path: Path) -> Optional[str]:
    """Extract display name from executable file properties (Windows)."""
    try:
        # Try to get file description from Windows properties
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


def generate_aliases(exe_name: str, display_name: Optional[str] = None) -> List[str]:
    """Generate aliases for an application."""
    aliases: Set[str] = set()

    # Check if we have metadata for this executable
    exe_base = exe_name.lower().replace(".exe", "")

    if exe_base in APP_METADATA:
        metadata = APP_METADATA[exe_base]
        if display_name is None:
            display_name = metadata.get("display_name")
        aliases.update(metadata.get("aliases", []))

    # Add the base executable name
    if exe_name.lower() != "explorer.exe":
        aliases.add(exe_base)

    # Try to generate from display name
    if display_name:
        display_lower = display_name.lower()
        aliases.add(display_lower)

        # Generate variations from display name
        parts = display_lower.split()

        if len(parts) > 1:
            # Add full phrase
            aliases.add(display_lower)

            # Add first word
            aliases.add(parts[0])

            # Add common abbreviations
            if "visual studio" in display_lower:
                if "code" in display_lower:
                    aliases.add("vscode")
                    aliases.add("vs code")

        # Handle special cases
        if "chrome" in display_lower:
            aliases.add("chrome")
        if "firefox" in display_lower:
            aliases.add("firefox")
        if "notepad++" in display_lower or "notepad ++" in display_lower:
            aliases.add("notepad++")
            aliases.add("notepad plus plus")

    return sorted(list(aliases))


def scan_directory(
    directory: Path, max_depth: int = 1, current_depth: int = 0
) -> List[Application]:
    """Scan a directory for executables (limited depth)."""
    applications: List[Application] = []
    

    if not directory.exists() or not directory.is_dir():
        return applications

    try:
        for item in directory.iterdir():
            try:
                # Stop at max depth
                if current_depth >= max_depth:
                    continue

                if item.is_file():
                    if item.suffix.lower() == ".exe":
                        if should_ignore(item):
                            continue

                        exe_name = item.stem
                        display_name = get_display_name_from_exe(item)
                        aliases = generate_aliases(item.name, display_name)
                        if "windows\\system32" in str(item).lower():
                         continue

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
                    # Recursively scan subdirectories
                    applications.extend(
                        scan_directory(item, max_depth, current_depth + 1)
                    )

            except (PermissionError, OSError) as e:
                logger.debug(f"Skipped {item}: {e}")

    except (PermissionError, OSError) as e:
        logger.debug(f"Cannot scan {directory}: {e}")

    return applications


def scan_program_files() -> List[Application]:
    """Scan C:\\Program Files."""
    logger.info("Scanning C:\\Program Files...")
    return scan_directory(Path("C:\\Program Files"), max_depth=2)


def scan_program_files_x86() -> List[Application]:
    """Scan C:\\Program Files (x86)."""
    logger.info("Scanning C:\\Program Files (x86)...")
    return scan_directory(Path("C:\\Program Files (x86)"), max_depth=2)


def scan_local_programs() -> List[Application]:
    """Scan %LOCALAPPDATA%\\Programs."""
    logger.info("Scanning %LOCALAPPDATA%\\Programs...")
    local_appdata = Path(os.getenv("LOCALAPPDATA", ""))

    if not local_appdata.exists():
        return []

    programs_dir = local_appdata / "Programs"
    if not programs_dir.exists():
        return []

    return scan_directory(programs_dir, max_depth=2)


def scan_start_menu() -> List[Application]:
    """Scan Start Menu shortcuts."""
    logger.info("Scanning Start Menu...")
    applications: List[Application] = []

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


def scan_path() -> List[Application]:
    """Scan executables in PATH environment variable."""
    logger.info("Scanning PATH...")
    applications: List[Application] = []
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


def merge_results(
    all_applications: List[List[Application]],
) -> Dict[str, Application]:
    """
    Merge results from different scan locations.

    Preference order:
    1. Program Files
    2. Program Files (x86)
    3. LocalAppData
    4. Start Menu
    5. PATH
    """
    registry: Dict[str, Application] = {}

    for app_list in all_applications:
        for app in app_list:
            app_key = app.name.lower()

            # Determine priority based on path
            priority = 999
            path_str = str(app.path).upper()

            if "PROGRAM FILES (X86)" in path_str:
                priority = 1
            elif "PROGRAM FILES" in path_str:
                priority = 0
            elif "LOCALAPPDATA" in path_str:
                priority = 2
            elif "START MENU" in path_str:
                priority = 3
            else:
                priority = 4

            # Keep if not seen before or if this version has higher priority
            if app_key not in registry:
                registry[app_key] = app
            else:
                existing = registry[app_key]
                existing_priority = 999
                existing_path = str(existing.path).upper()

                if "PROGRAM FILES (X86)" in existing_path:
                    existing_priority = 1
                elif "PROGRAM FILES" in existing_path:
                    existing_priority = 0
                elif "LOCALAPPDATA" in existing_path:
                    existing_priority = 2
                elif "START MENU" in existing_path:
                    existing_priority = 3
                else:
                    existing_priority = 4

                if priority < existing_priority:
                    registry[app_key] = app

    return registry


def save_registry(
    registry: Dict[str, Application], output_path: Path
) -> None:
    """Save registry to JSON file."""
    data = {
        "version": 1,
        "last_scan": datetime.now().isoformat(),
        "applications": sorted(
            [app.to_dict() for app in registry.values()],
            key=lambda x: x["name"].lower(),
        ),
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    logger.info(f"Saved {len(registry)} applications to {output_path}")


def scan_all() -> List[Dict]:
    """
    Execute full application discovery pipeline.

    Returns:
        List of application dictionaries (not saved to file).
        KnowledgeManager decides how to save.

    Note:
        This function NO LONGER writes JSON.
        It only discovers and returns results.
    """
    logger.info("Starting application scan...")

    # Scan all locations
    results = [
        
     scan_start_menu(),
     scan_local_programs(),
     scan_program_files(),
     scan_program_files_x86(),

    ]

    # Merge results
    registry = merge_results(results)

    logger.info(f"Discovered {len(registry)} unique applications")

    # Convert to list of dicts for manager
    applications = [app.to_dict() for app in registry.values()]

    return applications


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    from knowledge.manager import get_manager

    manager = get_manager()

    # Scan and save through manager
    if manager.refresh_applications():
        print(f"\nRefreshed applications successfully")
    else:
        print(f"\nFailed to refresh applications")
