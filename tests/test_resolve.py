"""
Tests for entity resolution with knowledge base.

Updated for new architecture: EntityResolver lives in knowledge/entity_resolver.py.
Uses KnowledgeManager to load entities instead of use_knowledge_base parameter.
"""

from knowledge.entity_resolver import EntityResolver
from knowledge.manager import get_manager

# Load entities from KnowledgeManager
manager = get_manager()
entities = manager.get_all_entities()
resolver = EntityResolver(entities=entities)

# Test resolution with knowledge base
print("Testing entity resolution with knowledge base:")
print()

result = resolver.replace_entity("open vscode")
print(f"'open vscode' -> '{result}'")

result = resolver.replace_entity("launch spotify")
print(f"'launch spotify' -> '{result}'")

result = resolver.replace_entity("open chrome")
print(f"'open chrome' -> '{result}'")

result = resolver.replace_entity("go to github")
print(f"'go to github' -> '{result}'")
