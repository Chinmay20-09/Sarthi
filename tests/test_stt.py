"""Tests for speech/speech_to_text.py — the transcribe() wrapper.

The Whisper model itself is never loaded: get_model() is monkeypatched so
these tests stay fast, offline, and deterministic. A real 16-bit PCM WAV
file is still written to disk so the path-handling surface of transcribe()
is exercised.
"""

import wave
from types import SimpleNamespace

import numpy as np
import pytest

from speech import speech_to_text as stt

SAMPLE_RATE = 16000


class FakeModel:
    """Minimal stand-in for faster_whisper.WhisperModel."""

    def __init__(self, segments):
        self._segments = segments
        self.calls = []

    def transcribe(self, audio, language="en", beam_size=5, vad_filter=True):
        self.calls.append((audio, language, beam_size, vad_filter))
        # faster_whisper returns a TranscriptionInfo with attribute access
        info = SimpleNamespace(language="en", language_probability=0.9)
        return self._segments, info


def make_wav(path, duration=0.5, frequency=None):
    """Write a valid 16-bit PCM mono WAV file at the config sample rate."""
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        n = int(SAMPLE_RATE * duration)
        if frequency:
            t = np.arange(n) / SAMPLE_RATE
            data = (np.sin(2 * np.pi * frequency * t) * 0.3 * 32767).astype(np.int16)
        else:
            data = np.zeros(n, dtype=np.int16)
        w.writeframes(data.tobytes())


@pytest.fixture
def wav_path(tmp_path):
    """A small valid WAV file (0.5s of 440 Hz tone)."""
    path = tmp_path / "sample.wav"
    make_wav(path, frequency=440)
    return str(path)


def test_transcribe_returns_joined_text(monkeypatch, wav_path):
    """transcribe() should pass the wav path to the model and join segments."""
    model = FakeModel([SimpleNamespace(text=" hello "), SimpleNamespace(text="world")])
    monkeypatch.setattr(stt, "get_model", lambda: model)

    assert stt.transcribe(wav_path) == "hello world"
    assert model.calls == [(wav_path, "en", 5, True)]


def test_transcribe_empty_result_returns_empty_string(monkeypatch, wav_path):
    """A model producing no segments should yield an empty string."""
    model = FakeModel([])
    monkeypatch.setattr(stt, "get_model", lambda: model)

    assert stt.transcribe(wav_path) == ""


def test_transcribe_accepts_numpy_audio(monkeypatch):
    """transcribe() should also accept a raw float32 audio array."""
    audio = np.zeros(SAMPLE_RATE, dtype=np.float32)
    model = FakeModel([SimpleNamespace(text="silence")])
    monkeypatch.setattr(stt, "get_model", lambda: model)

    assert stt.transcribe(audio) == "silence"
    assert model.calls[0][0] is audio
