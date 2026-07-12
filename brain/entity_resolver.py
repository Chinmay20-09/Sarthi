
"""
Entity Resolver for Sarthi.

Performs fuzzy matching on entities to extract intents from natural language.

IMPORTANT: This module uses DEPENDENCY INJECTION.
Entities are passed in at construction time.
This resolver has NO knowledge of where entities come from.

It doesn't import knowledge.loader or knowledge.manager directly.
Instead, it receives entities from KnowledgeManager.
"""

import logging
from typing import Dict, List, Optional, Tuple
from rapidfuzz import process, fuzz

logger = logging.getLogger(__name__)


class EntityResolver:
    """
    Fuzzy entity matcher using RapidFuzz.

    Receives entities via dependency injection.
    Has no direct knowledge of data sources.

    Responsibilities:
    - Store entities
    - Perform fuzzy matching
    - Generate phrase variations
    - Resolve entities from natural language

    What this does NOT do:
    - Load data
    - Search data
    - Save data
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

    def __init__(self, entities: Optional[List[Dict]] = None):
        """
        Initialize resolver with entities.

        Args:
            entities: List of entity dicts with 'name', 'aliases', 'category'
                     If None, will load from KnowledgeManager
        """
        self.entities: List[Dict] = []
        self.entity_names: List[str] = []

        if entities is None:
            # Lazy load from KnowledgeManager if not provided
            from knowledge.manager import get_manager
            manager = get_manager()
            entities = manager.get_all_entities()

        self._build_index(entities)

    def _build_index(self, entities: List[Dict]) -> None:
        """
        Build fast lookup index for fuzzy matching.

        Args:
            entities: List of entity dicts
        """
        self.entities = entities

        # Pre-clean all names for fuzzy matching
        self.entity_names = [
            self.clean(entity.get("name", ""))
            for entity in self.entities
        ]

        logger.debug(
            f"Built entity resolver index with {len(self.entities)} entities"
        )

    def clean(self, text: str) -> str:
        """
        Remove spaces/punctuation, lowercase.

        Examples:
        "Git Hub" -> "github"
        "VS Code" -> "vscode"
        """
        return "".join(c.lower() for c in text if c.isalnum())

    def generate_phrases(self, text: str, max_words: int = 3) -> List[Tuple[str, int, int]]:
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

    def fuzzy_match(self, phrase: str) -> Optional[Dict]:
        """
        Find best matching entity for phrase.

        Args:
            phrase: Text to match

        Returns:
            Dict with match info or None
        """
        cleaned_phrase = self.clean(phrase)

        match = process.extractOne(
            cleaned_phrase, self.entity_names, scorer=fuzz.WRatio
        )

        if match is None:
            return None

        _, score, index = match
        entity = self.entities[index]

        # Check if phrase exactly matches an alias
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

    def resolve_entity(self, text: str) -> Optional[Dict]:
        """
        Resolve best entity from text.

        Tests all phrase variations and returns best match.

        Args:
            text: Natural language text

        Returns:
            Best matching entity or None
        """
        phrases = self.generate_phrases(text)
        best = None

        logger.debug("========== Entity Resolver ==========")

        for phrase, start, length in phrases:
            words = phrase.lower().split()

            # Ignore phrases made entirely of stop words
            if all(word in self.STOP_WORDS for word in words):
                continue
            
            result = self.fuzzy_match(phrase)

            if result is None:
                continue

            if result["confidence"] < self.MIN_CONFIDENCE:
                continue

            # Prefer longer phrases slightly
            result["score"] = result["confidence"] + (length * 5)
            result["start"] = start
            result["length"] = length

            logger.debug(
                f"{phrase:<20} -> {result['match']:<12} {result['confidence']:.1f}"
            )

            if best is None or result["score"] > best["score"]:
                best = result

        return best

    def replace_entity(self, text: str) -> str:
        """
        Replace entity phrase with canonical name.

        Args:
            text: Natural language text

        Returns:
            Text with entity replaced by canonical name
        """
        result = self.resolve_entity(text)

        if result is None:
            return text

        words = text.lower().split()

        start = result["start"]
        length = result["length"]

        words[start : start + length] = [result["match"]]

        return " ".join(words)

    def resolve(self, text: str) -> str:
        """
        Public API - resolve entities in text.

        Args:
            text: Natural language text

        Returns:
            Text with entities replaced
        """
        return self.replace_entity(text)
