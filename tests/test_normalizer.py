from brain.normalizer import normalize

tests = [
    "open youtub",
    "open youutube",
    "open youtube",
    "open github",
    "open spotfy",
    "open chrom",
    "open code",
]

for t in tests:

    print()

    print("Input :", t)

    print("Output:", normalize(t))