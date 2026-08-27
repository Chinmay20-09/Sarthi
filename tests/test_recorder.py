"""Tests for speech/recorder.py — recording audio to a WAV file.

The microphone is never touched: sounddevice.rec is monkeypatched to
return synthetic audio, so the tests are fast and work without hardware.
"""

import wave

import numpy as np

import speech.recorder as recorder

SAMPLE_RATE = 16000


def test_record_audio_writes_wav(tmp_path, monkeypatch):
    """record_audio() should write a valid mono 16-bit WAV and return its path."""
    path = tmp_path / "out.wav"

    # Fake microphone: 0.1s of int16 audio
    fake = np.zeros(int(0.1 * SAMPLE_RATE), dtype=np.int16)
    monkeypatch.setattr(recorder.sd, "rec", lambda *a, **k: fake)
    monkeypatch.setattr(recorder.sd, "wait", lambda: None)

    result = recorder.record_audio(filename=str(path), duration=0.1)
    assert result == str(path)
    assert path.exists() and path.stat().st_size > 0

    with wave.open(str(path), "rb") as w:
        assert w.getnchannels() == 1
        assert w.getframerate() == SAMPLE_RATE
        assert w.getsampwidth() == 2  # int16
        assert w.getnframes() == len(fake)


def test_record_audio_forwards_duration(tmp_path, monkeypatch):
    """The requested duration should be forwarded to the recorder as frames."""
    captured = {}

    def fake_rec(frames, **kwargs):
        captured["frames"] = frames
        return np.zeros(frames, dtype=np.int16)

    monkeypatch.setattr(recorder.sd, "rec", fake_rec)
    monkeypatch.setattr(recorder.sd, "wait", lambda: None)

    path = tmp_path / "duration.wav"
    recorder.record_audio(filename=str(path), duration=2)
    assert captured["frames"] == 2 * SAMPLE_RATE
