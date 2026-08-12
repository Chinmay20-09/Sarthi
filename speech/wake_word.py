"""
Wake word detection for Sarthi.

Listens for configured wake word phrases and reacts when they are spoken.
The phrases are supplied by the caller — the root-level launcher
(wakeword.py) reads them from variable.py so they can be changed without
touching any code.

Components:
    wake_word_matches(text, wake_words)  — Pure matching logic
    WakeWordListener                     — Continuous listener with callback
    detect_wake_word(wake_words)         — One-shot check (used by SpeechSkill)

Usage:
    from speech.wake_word import WakeWordListener

    listener = WakeWordListener(["hey sarthi"], on_wake=lambda text: print("Woke up!"))
    listener.listen_forever()
"""

import logging
import re
import time
from collections.abc import Callable
from typing import Any

import numpy as np
import sounddevice as sd

from config import SAMPLE_RATE
from events import EventBus, get_bus
from speech.speech_to_text import transcribe

logger = logging.getLogger(__name__)

WakeWordCallback = Callable[[str], Any]


def wake_word_matches(text: str, wake_words: list[str]) -> bool:
    """
    Return True if any wake word phrase appears in the transcribed text.

    Matching is case-insensitive and tolerant of punctuation (Whisper often
    inserts commas) and surrounding words. Single-word phrases match on word
    boundaries so "hey" does not match inside "they".
    """
    if not text or not wake_words:
        return False

    normalized = " ".join(re.sub(r"[^\w\s]", " ", text.lower()).split())
    words = set(normalized.split())

    for phrase in wake_words:
        phrase = " ".join(phrase.lower().split())
        if not phrase:
            continue
        if " " in phrase:
            if phrase in normalized:
                return True
        elif phrase in words:
            return True
    return False


class WakeWordListener:
    """
    Continuously listens for a wake word and fires a callback when found.

    Uses a simple energy gate: quiet audio is ignored, speech is buffered
    until a pause, and the buffered utterance is transcribed once. The
    transcribed text is then checked against the configured phrases.

    Args:
        wake_words: Phrase(s) that trigger detection (a single string is OK).
        on_wake: Optional callback invoked with the detected text.
        energy_threshold: RMS loudness (0.0–1.0) that counts as speech.
        chunk_duration: Microphone sample chunk length, in seconds.
        max_utterance: Longest utterance to buffer, in seconds.
        silence_pause: Silence after speech that ends the utterance, in seconds.
        samplerate: Sample rate used for recording (config.SAMPLE_RATE).
        record_fn: Injectable recorder (duration_seconds -> np.ndarray).
        transcribe_fn: Injectable transcriber (audio -> text).
    """

    def __init__(
        self,
        wake_words: str | list[str],
        on_wake: WakeWordCallback | None = None,
        *,
        energy_threshold: float = 0.015,
        chunk_duration: float = 0.5,
        max_utterance: float = 6.0,
        silence_pause: float = 0.8,
        samplerate: int = SAMPLE_RATE,
        record_fn: Callable[[float], np.ndarray] | None = None,
        transcribe_fn: Callable[[np.ndarray], str] | None = None,
    ) -> None:
        if isinstance(wake_words, str):
            wake_words = [wake_words]
        self.wake_words = [w.strip().lower() for w in wake_words if w and w.strip()]
        self.on_wake = on_wake
        self.energy_threshold = float(energy_threshold)
        self.chunk_duration = max(float(chunk_duration), 0.1)
        self.max_utterance = float(max_utterance)
        self.silence_pause = float(silence_pause)
        self.samplerate = int(samplerate)
        self._record = record_fn or self._record_chunk
        self._transcribe = transcribe_fn or transcribe
        self._stop = False

        if not self.wake_words:
            logger.warning("No wake words configured — listener will never trigger.")

    # ------------------------------------------------------------------
    # Control
    # ------------------------------------------------------------------

    def stop(self) -> None:
        """Stop the listening loop at the next safe point."""
        self._stop = True

    # ------------------------------------------------------------------
    # Listening
    # ------------------------------------------------------------------

    def _record_chunk(self, duration: float) -> np.ndarray:
        """Record one chunk of audio at the configured sample rate."""
        samples = sd.rec(
            int(duration * self.samplerate),
            samplerate=self.samplerate,
            channels=1,
            dtype="float32",
        )
        sd.wait()
        return samples.flatten()

    @staticmethod
    def _rms(audio: np.ndarray) -> float:
        """Root-mean-square loudness of a chunk (0.0 = digital silence)."""
        if audio.size == 0:
            return 0.0
        return float(np.sqrt(np.mean(np.square(audio.astype(np.float64)))))

    def listen_once(self, timeout: float | None = None) -> str | None:
        """
        Capture one utterance and transcribe it.

        Blocks until speech is detected (then records until the utterance
        ends) or the listener is stopped.

        Args:
            timeout: Optional seconds to wait for speech to start. If nothing
                is said within this window, returns None.

        Returns:
            The transcribed text, or None if no speech started within the
            timeout (or the listener was stopped).
        """
        utterance: list[np.ndarray] = []
        silence_chunks = 0
        max_chunks = max(1, int(round(self.max_utterance / self.chunk_duration)))
        silence_limit = max(1, int(round(self.silence_pause / self.chunk_duration)))
        waiting_started = time.monotonic()

        while not self._stop:
            if not utterance and timeout is not None:
                if time.monotonic() - waiting_started >= timeout:
                    return None
            chunk = np.asarray(self._record(self.chunk_duration), dtype=np.float32)
            if self._rms(chunk) >= self.energy_threshold:
                utterance.append(chunk)
                silence_chunks = 0
                if len(utterance) >= max_chunks:
                    break
            elif utterance:
                silence_chunks += 1
                if silence_chunks >= silence_limit:
                    break

        if not utterance:
            return None

        return self._transcribe(np.concatenate(utterance))

    def listen_forever(self, publish_event: bool = True) -> None:
        """
        Keep listening until stop() is called, firing on_wake on detection.

        Args:
            publish_event: Whether to publish a "wake_word_detected" event
                on the global EventBus when the wake word is heard.
        """
        if not self.wake_words:
            logger.warning("No wake words configured — nothing to listen for.")
            return

        logger.info("Listening for wake word(s): %s", ", ".join(self.wake_words))

        while not self._stop:
            try:
                text = self.listen_once()
            except Exception:
                # e.g. microphone unplugged or transcription error — keep the
                # background listener alive and retry shortly.
                logger.exception("Wake word listening error — retrying...")
                time.sleep(2.0)
                continue
            if text and wake_word_matches(text, self.wake_words):
                logger.info("Wake word detected: %r", text)

                if publish_event:
                    try:
                        get_bus().publish(
                            EventBus.WAKE_WORD_DETECTED,
                            {"text": text, "wake_words": self.wake_words},
                            source="wake_word",
                        )
                    except Exception:
                        logger.exception("Failed to publish wake_word_detected event")

                if self.on_wake:
                    self.on_wake(text)


def detect_wake_word(
    wake_words: str | list[str] | None = None,
    *,
    timeout: float = 30.0,
    energy_threshold: float = 0.015,
    chunk_duration: float = 0.5,
    max_utterance: float = 6.0,
    silence_pause: float = 0.8,
) -> bool:
    """
    Record one utterance and return True if it contained a wake word.

    Convenience one-shot API used by the SpeechSkill's manual check.
    A timeout prevents callers (e.g. an API request) from blocking forever.
    """
    phrases = wake_words if wake_words is not None else ["hey sarthi"]
    listener = WakeWordListener(
        phrases,
        energy_threshold=energy_threshold,
        chunk_duration=chunk_duration,
        max_utterance=max_utterance,
        silence_pause=silence_pause,
    )
    text = listener.listen_once(timeout=timeout)
    return bool(text) and wake_word_matches(text, listener.wake_words)
