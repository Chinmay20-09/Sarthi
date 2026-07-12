"""
Pure JSON I/O layer for Sarthi knowledge bases.

Responsibilities ONLY:
- Load JSON files
- Save JSON files
- Validate file integrity
- Handle file I/O errors

WHAT THIS CLASS DOES NOT DO:
- Searching
- Merging
- Business logic
- Caching
- Alias generation

All higher-level operations go to KnowledgeManager.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class KnowledgeLoader:
    """Pure JSON I/O layer - serialization/deserialization only."""

    def __init__(self, file_path: Path):
        """
        Initialize loader.

        Args:
            file_path: Path to JSON knowledge base file
        """
        self.file_path = Path(file_path)

    def load(self) -> Optional[Dict[str, Any]]:
        """
        Load and parse JSON file.

        Returns:
            Parsed JSON dict, or None if missing/corrupted
        """
        if not self.file_path.exists():
            logger.debug(f"Knowledge file not found: {self.file_path}")
            return None

        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data

        except (json.JSONDecodeError, OSError) as e:
            logger.error(f"Failed to load knowledge file {self.file_path}: {e}")
            return None

    def save(self, data: Dict[str, Any]) -> bool:
        """
        Save data to JSON file.

        Args:
            data: Dictionary to save

        Returns:
            True if successful
        """
        try:
            self.file_path.parent.mkdir(parents=True, exist_ok=True)

            # Manager should set last_scan, but ensure it's there
            if "last_scan" not in data:
                data["last_scan"] = datetime.now().isoformat()

            with open(self.file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

            return True

        except OSError as e:
            logger.error(f"Failed to save knowledge file {self.file_path}: {e}")
            return False

    def is_valid(self) -> bool:
        """
        Validate file structure.

        Returns:
            True if file is valid JSON with required fields
        """
        if not self.file_path.exists():
            return False

        try:
            data = self.load()
            if data is None:
                return False

            # Check required fields
            if not isinstance(data, dict):
                return False

            if "version" not in data:
                return False

            if "entities" not in data or not isinstance(data["entities"], list):
                return False

            return True

        except Exception as e:
            logger.debug(f"File validation failed: {e}")
            return False


# Module-level convenience functions
def load_json(file_path: Path) -> Optional[Dict[str, Any]]:
    """
    Load JSON from file.

    Args:
        file_path: Path to JSON file

    Returns:
        Parsed JSON or None
    """
    loader = KnowledgeLoader(file_path)
    return loader.load()


def save_json(file_path: Path, data: Dict[str, Any]) -> bool:
    """
    Save JSON to file.

    Args:
        file_path: Path to JSON file
        data: Dictionary to save

    Returns:
        True if successful
    """
    loader = KnowledgeLoader(file_path)
    return loader.save(data)
