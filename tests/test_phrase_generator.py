from brain.entity_resolver import EntityResolver

resolver = EntityResolver()

text = "open you dude"

phrases = resolver.generate_phrases(text)

for phrase, start, length in phrases:
    print(
        f"{phrase:<20} start={start} length={length}"
    )