from brain.entity_resolver import EntityResolver

# Test with knowledge base
resolver = EntityResolver(use_knowledge_base=True)

print(f"Total entities: {len(resolver.entities)}")
print(f"Applications: {len([e for e in resolver.entities if e.get('category') == 'applications'])}")

print("\nSample applications from knowledge base:")
for entity in resolver.entities[:5]:
    if entity.get('category') == 'applications':
        print(f"  {entity['name']} - {entity.get('aliases', [])[:2]}")