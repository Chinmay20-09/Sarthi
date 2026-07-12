from brain.interpreter import interpret

tests = [
    "Hey Sarthi, could you please open Chrome for me",
    "Would you launch GitHub",
    "Please start Visual Studio Code",
    "Can you find Python tutorials",
]

print("=" * 60)
print("INTERPRETER TEST")
print("=" * 60)

for text in tests:
    intent = interpret(text)

    print(f"\nInput      : {text}")
    print(f"Action     : {intent.action}")
    print(f"Target     : {intent.target}")
    print(f"Confidence : {intent.confidence}")