"""
Centralized logging setup for Sarthi.

EVERY package should use this module instead of calling
logging.basicConfig() directly. This ensures:
    - Consistent log format across all packages
    - Single configuration point (change once, affects all)
    - Proper log level management
    - File + console output support

Usage:
    from utils.logger import setup_logging, get_logger

    # At application startup (once):
    setup_logging()

    # In every module:
    logger = get_logger(__name__)
    logger.info("Something happened")
    logger.debug("Detailed info")
    logger.error("Something broke")
"""

import logging
import sys
from pathlib import Path

from config import LOG_FORMAT, LOG_LEVEL, PROJECT_ROOT

# Default log file path
DEFAULT_LOG_FILE = PROJECT_ROOT / "logs" / "sarthi.log"

# Track whether setup has been called
_logging_initialized = False


def setup_logging(
    level: str | None = None,
    log_format: str | None = None,
    log_file: Path | None = None,
    console: bool = True,
) -> None:
    """
    Configure logging for the entire application.

    Call ONCE at application startup (in main.py or api.py).
    All subsequent get_logger() calls use this configuration.

    Args:
        level: Log level string (DEBUG, INFO, WARNING, ERROR).
               Defaults to config.LOG_LEVEL.
        log_format: Log format string.
                    Defaults to config.LOG_FORMAT.
        log_file: Path to log file. If None, file logging is disabled.
        console: If True, log to console (stderr).
    """
    global _logging_initialized

    if _logging_initialized:
        # Prevent duplicate configuration
        return

    resolved_level = (level or LOG_LEVEL).upper()
    resolved_format = log_format or LOG_FORMAT

    handlers: list[logging.Handler] = []

    # Console handler (skipped under pythonw, where sys.stderr is None)
    if console and sys.stderr is not None:
        console_handler = logging.StreamHandler(sys.stderr)
        console_handler.setFormatter(logging.Formatter(resolved_format))
        handlers.append(console_handler)

    # File handler
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(str(log_file), encoding="utf-8")
        file_handler.setFormatter(logging.Formatter(resolved_format))
        handlers.append(file_handler)

    # Configure root logger
    if not handlers:
        # No handlers requested — nothing to configure
        return

    logging.basicConfig(
        level=getattr(logging, resolved_level, logging.INFO),
        format=resolved_format,
        handlers=handlers,
        force=True,
    )

    _logging_initialized = True

    logger = logging.getLogger(__name__)
    logger.debug(f"Logging initialized: level={resolved_level}, file={log_file}, console={console}")


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger for a module.

    Wrapper around logging.getLogger() that ensures logging
    is initialized first.

    Args:
        name: Usually __name__ from the calling module.

    Returns:
        Configured Logger instance.
    """
    if not _logging_initialized:
        # Auto-initialize with defaults if not already set up
        setup_logging()

    return logging.getLogger(name)


def set_level(level: str) -> None:
    """
    Change the log level at runtime.

    Args:
        level: Log level string (DEBUG, INFO, WARNING, ERROR).
    """
    resolved_level = getattr(logging, level.upper(), logging.INFO)
    logging.getLogger().setLevel(resolved_level)
    logging.getLogger(__name__).info(f"Log level changed to {level.upper()}")
