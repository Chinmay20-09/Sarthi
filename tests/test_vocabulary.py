from brain.vocabulary import VOCABULARY

for category, words in VOCABULARY.items():

    print()

    print(category.upper())

    for word in words:
        print("-", word)