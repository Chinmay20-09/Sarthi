"""
Entity Resolver — BACKWARD COMPATIBILITY SHIM.

Entity resolution has moved to the Knowledge Layer where it belongs.
This module now re-exports from knowledge/entity_resolver.py.

ARCHITECTURE:
    Entity resolution is searching stored knowledge, NOT reasoning.
    It belongs in the Knowledge Layer, not the Brain.

    New code should import from:
        from knowledge.entity_resolver import EntityResolver

New code should NOT import from brain.resolver.
"""

import logging

logger = logging.getLogger(__name__)

# Re-export from canonical location
from knowledge.entity_resolver import EntityResolver  # noqa: F401

logger.debug("brain.resolver is a backward-compat shim. Import from knowledge.entity_resolver.")
