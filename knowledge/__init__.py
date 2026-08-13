"""Knowledge base module for Sarthi.

Centralized knowledge management system.

ARCHITECTURE:

loader.py       - Pure JSON I/O layer (internal)
manager.py      - Centralized business logic and searches (public)
applications.json - Discovered applications (generated)
websites.json    - Known websites (generated)

USAGE:

from knowledge.manager import get_manager

manager = get_manager()
app = manager.find_application("vscode")
all_entities = manager.get_all_entities()  # For EntityResolver

INTERNAL MODULES:
    loader.KnowledgeLoader  — Not exported. Use KnowledgeManager instead.
    scanners.*              — Internal. Only KnowledgeManager calls scanners.
"""

from .manager import KnowledgeManager, get_manager

__all__ = [
    "KnowledgeManager",
    "get_manager",
]
