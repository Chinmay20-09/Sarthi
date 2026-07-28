"""
Entity Resolver — BACKWARD COMPATIBILITY WRAPPER.

This module is preserved for existing code that imports from
brain.entity_resolver. The EntityResolver has moved to the
Knowledge Layer where it belongs (knowledge/entity_resolver.py).

ARCHITECTURE:
    Entity resolution is searching stored knowledge, NOT reasoning.
    It belongs in the Knowledge Layer.

NEW CODE SHOULD IMPORT FROM:
    from knowledge.entity_resolver import EntityResolver
"""

import logging

logger = logging.getLogger(__name__)

# Re-export from canonical Knowledge Layer location
from knowledge.entity_resolver import EntityResolver  # noqa: F401

logger.debug("brain.entity_resolver is a backward-compat shim. Use knowledge.entity_resolver.")
