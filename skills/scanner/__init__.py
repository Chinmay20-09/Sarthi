"""
Application Scanner skill for Sarthi.

Discovers installed applications and games from the system
and passes results to the Knowledge Layer.

Usage:
    from skills.scanner import ScannerSkill
    skill = ScannerSkill()

    # Or use scan_all directly via backward-compat
    from skills.scanner import scan_all
    apps = scan_all()
"""

from .application_scanner import (
    Application,
    generate_aliases,
    merge_results,
    scan_all,
    scan_directory,
    scan_game_directories,
    scan_local_programs,
    scan_path,
    scan_program_files,
    scan_program_files_x86,
    scan_start_menu,
    should_ignore,
)
from .main import ScannerSkill

__all__ = [
    "ScannerSkill",
    "scan_all",
    "scan_directory",
    "scan_game_directories",
    "scan_program_files",
    "scan_program_files_x86",
    "scan_local_programs",
    "scan_start_menu",
    "scan_path",
    "merge_results",
    "Application",
    "generate_aliases",
    "should_ignore",
]
