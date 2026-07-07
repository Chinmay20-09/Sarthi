from brain.vocabulary import VOCABULARY
from rapidfuzz import process, fuzz


class EntityResolver:

    MIN_CONFIDENCE = 70

    def __init__(self):
        self.vocabulary = VOCABULARY
        self.entities = []

        for category, words in self.vocabulary.items():
            for word in words:
                self.entities.append({
                    "name": word,
                    "category": category
                })

        # Cached cleaned entity names for faster matching
        self.entity_names = [
            self.clean(entity["name"])
            for entity in self.entities
        ]

    def clean(self, text: str) -> str:
        """
        Remove spaces/punctuation and lowercase text.

        Examples:
        "Git Hub" -> "github"
        "VS Code" -> "vscode"
        """
        return "".join(
            c.lower()
            for c in text
            if c.isalnum()
        )

    def generate_phrases(self, text: str, max_words: int = 3):

        words = text.lower().split()

        phrases = []

        for length in range(1, max_words + 1):
            for start in range(len(words) - length + 1):

                phrase = " ".join(words[start:start + length])

                phrases.append(
                    (phrase, start, length)
                )

        return phrases

    def fuzzy_match(self, phrase: str):

        cleaned_phrase = self.clean(phrase)

        match = process.extractOne(
            cleaned_phrase,
            self.entity_names,
            scorer=fuzz.WRatio
        )

        if match is None:
            return None

        _, score, index = match

        entity = self.entities[index]

        return {
            "input": phrase,
            "match": entity["name"],
            "category": entity["category"],
            "confidence": score
        }

    def resolve_entity(self, text: str):

        phrases = self.generate_phrases(text)

        best = None

        print("\n========== Entity Resolver ==========")

        for phrase, start, length in phrases:

            result = self.fuzzy_match(phrase)

            if result is None:
                continue

            if result["confidence"] < self.MIN_CONFIDENCE:
                continue

            # Prefer longer phrases slightly
            result["score"] = result["confidence"] + (length * 5)

            result["start"] = start
            result["length"] = length

            print(
                f"{phrase:<20} -> "
                f"{result['match']:<12}"
                f"{result['confidence']:.1f}"
            )

            if best is None or result["score"] > best["score"]:
                best = result

        return best

    def replace_entity(self, text: str):

        result = self.resolve_entity(text)

        if result is None:
            return text

        words = text.lower().split()

        start = result["start"]
        length = result["length"]

        words[start:start + length] = [result["match"]]

        return " ".join(words)

    def resolve(self, text: str):
        """
        Public API used by Sarthi.
        """
        return self.replace_entity(text)