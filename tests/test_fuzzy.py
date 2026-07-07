from brain.entity_resolver import EntityResolver

resolver = EntityResolver()

tests = [
    "open youtube",
    "open you tube",
    "open git hub",
    "launch chrom",
    "start spotfy",
    "open vs code",
]

for test in tests:
    print("=" * 60)
    print("Input :", test)
    print("Output:", resolver.resolve(test))