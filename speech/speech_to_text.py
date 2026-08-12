"""
Speech-to-text for Sarthi — Whisper transcription.

The Whisper model is loaded lazily (on first transcription) so that
importing this module is cheap and the model settings stay in one
place: config.py.
"""

import logging
from typing import Any

from config import WHISPER_COMPUTE_TYPE, WHISPER_DEVICE, WHISPER_MODEL

logger = logging.getLogger(__name__)

_model = None


def get_model() -> Any:
    """
    Load the Whisper model once and return the cached instance.

    Returns:
        faster_whisper.WhisperModel instance
    """
    global _model
    if _model is None:
        logger.info(
            "Loading Whisper model '%s' (device=%s, compute_type=%s)...",
            WHISPER_MODEL,
            WHISPER_DEVICE,
            WHISPER_COMPUTE_TYPE,
        )
        from faster_whisper import WhisperModel

        _model = WhisperModel(
            WHISPER_MODEL,
            device=WHISPER_DEVICE,
            compute_type=WHISPER_COMPUTE_TYPE,
        )
    return _model


def transcribe(audio: Any, language: str = "en", beam_size: int = 5) -> str:
    """
    Transcribe audio to text.

    Args:
        audio: Path to an audio file, a file-like object, or a float32
            numpy array sampled at the rate in config.SAMPLE_RATE.
        language: Expected spoken language (default "en").
        beam_size: Decoder beam size (default 5).

    Returns:
        Transcribed text
    """
    segments, info = get_model().transcribe(
        audio,
        language=language,
        beam_size=beam_size,
        vad_filter=True,
    )

    print(f"Language: {info.language}")
    print(f"Probability: {info.language_probability:.2f}")

    text = []

    for segment in segments:
        print(segment.text)
        text.append(segment.text.strip())

    return " ".join(text)
