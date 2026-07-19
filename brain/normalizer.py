"""
Normalizer for Sarthi's Brain.

DEPRECATED: This module performed fuzzy matching on action words,
which duplicated the brain/interpreter.py logic.

The interpreter now handles action detection directly.
This module is preserved for backward compatibility only.

New code should NOT use this module.
Use brain.interpreter.interpret() for intent parsing.
"""

import warnings

from rapidfuzz import fuzz, process

from brain.interpreter import ACTION_WORDS

SIMILARITY_THRESHOLD = 75


def fuzzy_match(word: str):
    """DEPRECATED: Use brain.interpreter.interpret() instead."""
    warnings.warn(
        "brain.normalizer is deprecated. Use brain.interpreter.interpret() instead.",
        DeprecationWarning,
        stacklevel=2,
    )

    match = process.extractOne(word, ACTION_WORDS, scorer=fuzz.ratio)
    if match is None:
        return word

    candidate, score, _ = match
    if score >= SIMILARITY_THRESHOLD:
        return candidate

    return word


def normalize(text: str):
    """DEPRECATED: Use brain.interpreter.interpret() instead."""
    warnings.warn(
        "brain.normalizer is deprecated. Use brain.interpreter.interpret() instead.",
        DeprecationWarning,
        stacklevel=2,
    )

    words = text.lower().split()
    normalized = []
    for word in words:
        normalized.append(fuzzy_match(word))
    return " ".join(normalized)
