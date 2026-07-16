from rapidfuzz import process, fuzz

from brain.interpreter import ACTION_WORDS

SIMILARITY_THRESHOLD = 75


def fuzzy_match(word: str):

    match = process.extractOne(
        word,
        ACTION_WORDS,
        scorer=fuzz.ratio,
    )

    if match is None:
        return word

    candidate, score, _ = match

    if score >= SIMILARITY_THRESHOLD:
        return candidate

    return word


def normalize(text: str):

    words = text.lower().split()

    normalized = []

    for word in words:
        normalized.append(fuzzy_match(word))

    return " ".join(normalized)