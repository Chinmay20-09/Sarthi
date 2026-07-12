"""Knowledge base module for Sarthi.

Centralized knowledge management system.

ARCHITECTURE:

loader.py       - Pure JSON I/O layer (no business logic)
manager.py      - Centralized business logic and searches
applications.json - Discovered applications (generated)
websites.json    - Known websites (generated)

USAGE:

from knowledge.manager import get_manager

manager = get_manager()
app = manager.find_application("vscode")
all_entities = manager.get_all_entities()  # For EntityResolver
"""

from .manager import KnowledgeManager, get_manager
from .loader import KnowledgeLoader, load_json, save_json

__all__ = [
    "KnowledgeManager",
    "get_manager",
    "KnowledgeLoader",
    "load_json",
    "save_json",
]

