"""
Entity Resolver for Sarthi — MOVED to knowledge layer.

This module was moved from brain/resolver.py because entity resolution
is searching stored knowledge, NOT reasoning. It belongs in the
Knowledge Layer per the three-layer architecture.

Original location: brain/resolver.py (now a backward-compat shim)

ARCHITECTURE:
    EntityResolver resides in the Knowledge Layer because:
    - It searches stored knowledge (aliases, fuzzy matching)
    - It does NOT perform reasoning or planning
    - It is data retrieval, not decision making
    - Skills and Brain use it through Knowledge

Usage:
    from knowledge.entity_resolver import EntityResolver

    entities = manager.get_all_entities()
    resolver = EntityResolver(entities=entities)
    result = resolver.resolve("open visual studio code")
"""

import logging

from rapidfuzz import fuzz, process

logger = logging.getLogger(__name__)


class EntityResolver:
    """
    Fuzzy entity matcher using RapidFuzz.

    Pure dependency injection — entities are provided at construction time.
    Has no knowledge of data sources whatsoever.

    Responsibilities:
        - Store entities
        - Perform fuzzy matching
        - Generate phrase variations
        - Resolve entities from natural language

    What this does NOT do:
        - Load data from disk
        - Query databases
        - Import knowledge modules
        - Perform reasoning
    """

    MIN_CONFIDENCE = 70
    STOP_WORDS = {
        "open",
        "launch",
        "start",
        "run",
        "search",
        "find",
        "play",
        "close",
        "stop",
        "please",
        "could",
        "would",
        "can",
        "you",
        "me",
        "the",
        "a",
        "an",
    }

    def __init__(self, entities: list[dict] | None = None):
        """
        Initialize resolver with entities.

        Args:
            entities: List of entity dicts with 'name', 'aliases', 'category'.
                     If None, creates an empty resolver (no entities to match).
        """
        self.entities: list[dict] = []
        self.entity_names: list[str] = []

        if entities:
            self._build_index(entities)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def resolve(self, text: str) -> str:
        """
        Resolve entities in text — replace with canonical names.

        Args:
            text: Natural language text (e.g., "open vs code")

        Returns:
            Text with entities replaced by canonical names (e.g., "open Visual Studio Code")
        """
        return self.replace_entity(text)

    def replace_entity(self, text: str) -> str:
        """
        Replace entity phrase with canonical name.

        Args:
            text: Natural language text

        Returns:
            Text with entity replaced by canonical name (or original text if no match)
        """
        result = self.resolve_entity(text)
        if result is None:
            return text

        words = text.lower().split()
        start = result["start"]
        length = result["length"]
        words[start : start + length] = [result["match"]]
        return " ".join(words)

    # ------------------------------------------------------------------
    # Matching
    # ------------------------------------------------------------------

    def resolve_entity(self, text: str) -> dict | None:
        """
        Resolve best entity from text.

        Tests all phrase variations and returns the best match.

        Args:
            text: Natural language text

        Returns:
            Dict with match info, or None if no match found
        """
        phrases = self.generate_phrases(text)
        best = None

        logger.debug("========== Entity Resolver ==========")

        for phrase, start, length in phrases:
            words = phrase.lower().split()
            if all(word in self.STOP_WORDS for word in words):
                continue

            result = self.fuzzy_match(phrase)
            if result is None:
                continue
            if result["confidence"] < self.MIN_CONFIDENCE:
                continue

            result["score"] = result["confidence"] + (length * 5)
            result["start"] = start
            result["length"] = length

            logger.debug(f"{phrase:<20} -> {result['match']:<12} {result['confidence']:.1f}")

            if best is None or result["score"] > best["score"]:
                best = result

        return best

    def fuzzy_match(self, phrase: str) -> dict | None:
        """
        Find best matching entity for a phrase.

        Args:
            phrase: Text to match

        Returns:
            Dict with match info, or None
        """
        cleaned_phrase = self.clean(phrase)

        match = process.extractOne(cleaned_phrase, self.entity_names, scorer=fuzz.WRatio)
        if match is None:
            return None

        _, score, index = match
        entity = self.entities[index]

        # Exact alias match = 100 confidence
        for alias in entity.get("aliases", []):
            if self.clean(alias) == cleaned_phrase:
                score = 100
                break

        return {
            "input": phrase,
            "match": entity.get("name", ""),
            "category": entity.get("category", ""),
            "confidence": score,
        }

    # ------------------------------------------------------------------
    # Phrase generation
    # ------------------------------------------------------------------

    def generate_phrases(self, text: str, max_words: int = 3) -> list[tuple[str, int, int]]:
        """
        Generate phrase variations from text.

        Args:
            text: Input text to parse
            max_words: Maximum phrase length

        Returns:
            List of (phrase, start_position, length) tuples
        """
        words = text.lower().split()
        phrases = []

        for length in range(1, max_words + 1):
            for start in range(len(words) - length + 1):
                phrase = " ".join(words[start : start + length])
                phrases.append((phrase, start, length))

        return phrases

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def clean(self, text: str) -> str:
        """
        Remove spaces/punctuation, lowercase.

        Examples:
            "Git Hub" -> "github"
            "VS Code" -> "vscode"
        """
        return "".join(c.lower() for c in text if c.isalnum())

    def _build_index(self, entities: list[dict]) -> None:
        """Build fast lookup index for fuzzy matching."""
        self.entities = entities
        self.entity_names = [self.clean(entity.get("name", "")) for entity in self.entities]
        logger.debug(f"Built entity resolver index with {len(self.entities)} entities")
