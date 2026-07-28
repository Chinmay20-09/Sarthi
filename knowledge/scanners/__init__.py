"""
Scanner package — BACKWARD COMPATIBILITY SHIM.

Scanning has moved to skills/scanner/ as a proper BaseSkill.
This module re-exports all public symbols from the canonical location.

ARCHITECTURE:
    Scanning is a skill (skills/scanner/).
    Import from skills.scanner for new code.
"""

import logging

logger = logging.getLogger(__name__)

# Re-export all public symbols from canonical location
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

logger.debug("knowledge.scanners is a backward-compat shim. " "Import from skills.scanner instead.")
