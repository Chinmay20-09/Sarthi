"""
Tests for Entity Resolver.

EntityResolver lives in knowledge/entity_resolver.py.
"""

from knowledge.entity_resolver import EntityResolver

# Create resolver with no entities (empty)
resolver = EntityResolver()

print(f"Total entities: {len(resolver.entities)}")

# Load entities from KnowledgeManager for a more comprehensive test
try:
    from knowledge.manager import get_manager

    manager = get_manager()
    all_entities = manager.get_all_entities()
    resolver_with_data = EntityResolver(entities=all_entities)

    print(f"Total entities from KnowledgeManager: {len(resolver_with_data.entities)}")
    print(f"Applications: {len([e for e in all_entities if e.get('category') == 'applications'])}")

    print("\nSample applications from knowledge base:")
    for entity in resolver_with_data.entities[:5]:
        if entity.get("category") == "applications":
            print(f"  {entity['name']} - {entity.get('aliases', [])[:2]}")
except Exception as e:
    print(f"Note: Could not load from KnowledgeManager: {e}")
