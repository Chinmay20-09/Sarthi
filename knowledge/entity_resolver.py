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

    # Minimum WRatio confidence. Kept high (80) to reject weak partial
    # matches like "time it" -> "timeout" (76.9); real references still
    # score 90+ thanks to indexed aliases, so recall is not hurt.
    MIN_CONFIDENCE = 80
    # Reject fuzzy matches where one side is much shorter than the other.
    # WRatio's partial scoring lets a short phrase attach to a much longer
    # name through a shared substring (e.g. "hello" -> "ShellMcpServers.Packaging"
    # via the "hell" fragment, or "time" -> "timeout" via the "time" prefix).
    MIN_LENGTH_RATIO = 0.62
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
        self._name_owners: list[int] = []

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

        Applies two quality guards on the raw WRatio score:
            1. Minimum confidence threshold.
            2. Length proportionality — a phrase and candidate must be of
               comparable length, otherwise the partial match is rejected.

        Args:
            phrase: Text to match

        Returns:
            Dict with match info, or None
        """
        cleaned_phrase = self.clean(phrase)
        if not cleaned_phrase:
            return None

        match = process.extractOne(cleaned_phrase, self.entity_names, scorer=fuzz.WRatio)
        if match is None:
            return None

        _, score, index = match
        entity = self.entities[self._name_owners[index]]
        candidate_clean = self.entity_names[index]

        # Length guard (both directions): reject substring-style partial
        # matches between a short phrase and a much longer candidate (or
        # vice versa), e.g. "chrome" latching onto a junk "MEM" utility.
        if len(cleaned_phrase) < self.MIN_LENGTH_RATIO * len(candidate_clean):
            return None
        if len(candidate_clean) < self.MIN_LENGTH_RATIO * len(cleaned_phrase):
            return None

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
        """Build fast lookup index for fuzzy matching.

        Indexes both canonical names and aliases (mapping each candidate
        string back to its owning entity via ``_name_owners``, which stays
        in lockstep with ``entity_names``) so partial references like
        "chrome" can reach "Google Chrome" through its alias.

        All canonical names are indexed before any aliases, and candidates
        are deduplicated, so an exact name match always wins over an alias
        that happens to contain the same string (extractOne returns the
        first candidate on a tie).
        """
        self.entities = entities
        self.entity_names = []
        self._name_owners = []
        seen: set[str] = set()

        # Pass 1: canonical names (exact names must beat aliases)
        for index, entity in enumerate(entities):
            name = self.clean(entity.get("name", ""))
            if name and name not in seen:
                seen.add(name)
                self.entity_names.append(name)
                self._name_owners.append(index)

        # Pass 2: aliases
        for index, entity in enumerate(entities):
            for alias in entity.get("aliases", []):
                alias_clean = self.clean(alias)
                if alias_clean and alias_clean not in seen:
                    seen.add(alias_clean)
                    self.entity_names.append(alias_clean)
                    self._name_owners.append(index)

        logger.debug(
            f"Built entity resolver index: {len(self.entities)} entities, "
            f"{len(self.entity_names)} unique names+aliases"
        )
