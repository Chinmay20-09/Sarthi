"""
Application Scanner — BACKWARD COMPATIBILITY SHIM.

The scanner has moved to skills/scanner/ as a proper BaseSkill.
This module is preserved for existing code that imports from
knowledge.scanners.application_scanner.

ARCHITECTURE:
    Scanning is now a skill (skills/scanner/).
    New code should use the ScannerSkill or import from skills/scanner/.
"""

import logging

logger = logging.getLogger(__name__)

# Re-export from canonical location
from skills.scanner.application_scanner import (  # noqa: F401
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

logger.debug(
    "knowledge.scanners.application_scanner is a backward-compat shim. "
    "Import from skills.scanner.application_scanner instead."
)
