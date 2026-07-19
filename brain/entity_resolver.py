"""
Entity Resolver — BACKWARD COMPATIBILITY WRAPPER.

This module is preserved for existing code that imports from
brain.entity_resolver. New code should import from brain.resolver instead.

DEPRECATED: Import from brain.resolver.EntityResolver for new code.
"""

import logging

from brain.resolver import EntityResolver as _EntityResolver

logger = logging.getLogger(__name__)


class EntityResolver(_EntityResolver):
    """
    Backward-compatible EntityResolver.

    Wraps the new brain.resolver.EntityResolver with the legacy behavior
    of auto-loading entities from KnowledgeManager when entities=None.

    DEPRECATED: Use brain.resolver.EntityResolver with explicit DI instead.
    """

    def __init__(self, entities: list[dict] | None = None, use_knowledge_base: bool = True):
        """
        Initialize with optional fallback to KnowledgeManager.

        Args:
            entities: List of entity dicts. If None, loads from KnowledgeManager.
            use_knowledge_base: If True (and entities is None), auto-load entities.
        """
        if entities is None and use_knowledge_base:
            try:
                from knowledge.manager import get_manager

                manager = get_manager()
                entities = manager.get_all_entities()
                logger.info(f"Loaded {len(entities)} entities from KnowledgeManager")
            except Exception as e:
                logger.warning(f"Could not load entities: {e}")
                entities = []

        super().__init__(entities=entities or [])
