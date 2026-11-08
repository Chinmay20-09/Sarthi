"""Lightweight, non-persistent user mood detection."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class UserMood:
    mood: str
    confidence: float
    evidence: str
    secondary: str | None = None


# A category is selected from contextual phrases, not a lone mood keyword.
_PATTERNS: dict[str, tuple[tuple[str, float, str], ...]] = {
    "happy": (
        (r"\b(i got the job|i got promoted|we did it|that worked|i'm so happy|i am so happy)\b", 0.9, "positive personal outcome"),
        (r"\b(excited|thrilled|delighted|over the moon)\b", 0.72, "expressed positive excitement"),
        (r"\b(love this|this is great|that's wonderful|amazing news)\b", 0.68, "positive evaluation"),
    ),
    "frustrated": (
        (r"\b(nothing works|keeps? failing|still (doesn't|does not) work|tried (it )?\d+ times)\b", 0.88, "repeated unsuccessful attempts"),
        (r"\b(i'm frustrated|i am frustrated|i feel frustrated|this is frustrating|so frustrating|fed up|i'm angry|i am angry)\b", 0.9, "explicit frustration"),
        (r"\b(again|another)\b.{0,45}\b(broke|failed|error|not working)\b", 0.75, "repeated failure"),
    ),
    "sad": (
        (r"\b(my .* (died|passed away)|i lost (my|a) .*|feels? so empty)\b", 0.9, "loss or emptiness"),
        (r"\b(i'm sad|i am sad|feeling down|disappointed|heartbroken|miss them)\b", 0.82, "expressed sadness or disappointment"),
    ),
    "confused": (
        (r"\b(i don't understand|i do not understand|i'm confused|i am confused|doesn't make sense)\b", 0.84, "explicit confusion"),
        (r"\b(unclear|what does .* mean|not sure what .* means)\b", 0.7, "uncertainty about meaning"),
    ),
    "tired": (
        (r"\b(i'm exhausted|i am exhausted|i'm (?:just )?tired|i am (?:just )?tired|no energy|worn out)\b", 0.86, "explicit low energy"),
        (r"\b(been up all night|barely slept|can't keep my eyes open)\b", 0.8, "sleep-related fatigue"),
    ),
    "stressed": (
        (r"\b(i'm stressed|i am stressed|overwhelmed|too much to do|can't keep up|under a lot of pressure)\b", 0.85, "expressed overload or pressure"),
        (r"\b(deadline)\b.{0,55}\b(panic|stressed|too much|overwhelmed)\b", 0.78, "deadline-related pressure"),
    ),
    "playful": (
        (r"\b(just kidding|i'm joking|i am joking|kidding aside)\b", 0.86, "explicitly playful framing"),
        (r"\b(lol|lmao)\b.{0,35}\b(joking|kidding|teasing)\b", 0.72, "joking language"),
    ),
}
_NEGATION = re.compile(r"\b(?:not|never|isn't|aren't|wasn't|was not)\s+(?:really\s+)?(?:very\s+)?(frustrated|angry|sad|confused|tired|stressed|overwhelmed|happy|excited|playful)\b")
_AMBIGUOUS = re.compile(r"\b(well,? that was unexpected|interesting|huh|i don't know how to feel)\b", re.I)


def detect_user_mood(text: str, history: list[dict] | None = None) -> UserMood:
    """Return an ephemeral mood estimate with confidence and concise evidence."""
    message = (text or "").strip().lower()
    if not message:
        return UserMood("unknown", 0.0, "No user text was provided.")

    scores: list[tuple[str, float, str]] = []
    negated = set(_NEGATION.findall(message))
    negates_mood = {
        "frustrated": {"frustrated", "angry"},
        "sad": {"sad"},
        "confused": {"confused"},
        "tired": {"tired"},
        "stressed": {"stressed", "overwhelmed"},
        "happy": {"happy", "excited"},
        "playful": {"playful"},
    }
    for mood, patterns in _PATTERNS.items():
        # Explicit negation cancels that mood for this utterance.
        if negated & negates_mood.get(mood, set()):
            continue
        for pattern, confidence, evidence in patterns:
            if re.search(pattern, message, re.I):
                scores.append((mood, confidence, evidence))
                break

    if not scores:
        if _AMBIGUOUS.search(message):
            return UserMood("unknown", 0.3, "The message is open to several interpretations.")
        return UserMood("calm", 0.52, "No clear emotional cue; defaulting to a neutral reading.")

    scores.sort(key=lambda row: row[1], reverse=True)
    mood, confidence, evidence = scores[0]
    secondary = None
    if len(scores) > 1 and scores[1][1] >= confidence - 0.16:
        secondary = scores[1][0]
        confidence = min(confidence, 0.76)
        evidence = f"Mixed cues: {evidence}; also {scores[1][2]}"

    # Context may strengthen a cue only when the current message already has
    # evidence; earlier temporary moods are never copied or persisted.
    if history and confidence < 0.8:
        recent_user_text = " ".join(
            str(turn.get("content", "")) for turn in history[-4:] if turn.get("role") == "user"
        ).lower()
        if any(term in recent_user_text for term in ("still", "again", "tried", "same issue")) and mood == "frustrated":
            confidence = min(0.9, confidence + 0.08)
            evidence += "; consistent with recent conversation context"
    return UserMood(mood, round(confidence, 2), evidence, secondary)
