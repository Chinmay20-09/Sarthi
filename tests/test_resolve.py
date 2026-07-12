from brain.entity_resolver import EntityResolver

resolver = EntityResolver(use_knowledge_base=True)

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