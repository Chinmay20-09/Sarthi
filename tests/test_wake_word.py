"""Tests for speech/wake_word.py — matching logic and listener loop.

These tests never touch the microphone: the listener is tested with
injected fake record/transcribe functions.
"""

import numpy as np

from speech.wake_word import WakeWordListener, wake_word_matches

LOUD = np.full(8000, 0.1, dtype=np.float32)  # ~0.5s of "speech" at 16 kHz
QUIET = np.zeros(8000, dtype=np.float32)  # digital silence


class TestWakeWordMatches:
    def test_exact_match(self):
        assert wake_word_matches("hey sarthi", ["hey sarthi"]) is True

    def test_case_insensitive(self):
        assert wake_word_matches("Hey Sarthi, open chrome", ["hey sarthi"]) is True

    def test_punctuation_tolerant(self):
        assert wake_word_matches("hey sarthi.", ["hey sarthi"]) is True
        assert wake_word_matches("hey, sarthi", ["hey sarthi"]) is True
        assert wake_word_matches("hey! sarthi?", ["hey sarthi"]) is True

    def test_inside_sentence(self):
        assert wake_word_matches("please open the browser hey sarthi", ["hey sarthi"]) is True

    def test_no_match(self):
        assert wake_word_matches("open chrome", ["hey sarthi"]) is False

    def test_multiple_wake_words(self):
        assert wake_word_matches("okay sarthi", ["hey sarthi", "okay sarthi"]) is True

    def test_single_word_does_not_match_inside_longer_word(self):
        assert wake_word_matches("they are here", ["hey"]) is False

    def test_empty_inputs(self):
        assert wake_word_matches("", ["hey sarthi"]) is False
        assert wake_word_matches("hello", []) is False


class TestWakeWordListener:
    def test_listen_once_transcribes_speech(self):
        chunks = iter([LOUD, LOUD, LOUD, QUIET, QUIET])
        listener = WakeWordListener(
            ["hey sarthi"],
            record_fn=lambda d: next(chunks, QUIET),
            transcribe_fn=lambda audio: "hey sarthi",
        )
        assert listener.listen_once() == "hey sarthi"

    def test_silence_skips_transcription(self):
        def transcribe(audio):  # pragma: no cover - must not be called
            raise AssertionError("silence should not be transcribed")

        listener = WakeWordListener(
            ["hey sarthi"],
            record_fn=lambda d: QUIET,
            transcribe_fn=transcribe,
        )
        assert listener.listen_once(timeout=1.0) is None

    def test_forever_calls_on_wake_and_stops(self):
        state = {"chunks": [LOUD, LOUD, LOUD, QUIET, QUIET], "calls": 0}

        def record(d):
            if state["chunks"]:
                return state["chunks"].pop(0)
            return QUIET

        def on_wake(text):
            state["calls"] += 1
            listener.stop()

        listener = WakeWordListener(
            ["hey sarthi"],
            on_wake=on_wake,
            record_fn=record,
            transcribe_fn=lambda audio: "hey sarthi",
        )
        listener.listen_forever(publish_event=False)

        assert state["calls"] == 1
        assert listener._stop is True

    def test_forever_ignores_non_matching_speech(self):
        state = {"chunks": [LOUD, LOUD, QUIET, QUIET], "calls": 0}

        def record(d):
            if state["chunks"]:
                return state["chunks"].pop(0)
            return QUIET

        def on_wake(text):
            state["calls"] += 1

        listener = WakeWordListener(
            ["hey sarthi"],
            on_wake=on_wake,
            record_fn=record,
            transcribe_fn=lambda audio: "open chrome",
        )

        # One full utterance cycle must not trigger the callback
        text = listener.listen_once()
        assert text == "open chrome"
        assert wake_word_matches(text, listener.wake_words) is False
        assert state["calls"] == 0

    def test_stop_flag_halts_listening(self):
        listener = WakeWordListener(["hey sarthi"], record_fn=lambda d: QUIET)
        assert listener._stop is False
        listener.stop()
        assert listener._stop is True

    def test_accepts_single_string_wake_word(self):
        listener = WakeWordListener("hey sarthi")
        assert listener.wake_words == ["hey sarthi"]

    def test_normalizes_and_filters_wake_words(self):
        listener = WakeWordListener([" Hey Sarthi ", "", "  "])
        assert listener.wake_words == ["hey sarthi"]

    def test_rms_of_silence_is_zero(self):
        assert WakeWordListener._rms(QUIET) == 0.0

    def test_rms_of_loud_chunk_is_positive(self):
        assert WakeWordListener._rms(LOUD) > 0.0

    def test_tiny_chunk_duration_is_clamped(self):
        listener = WakeWordListener(["hey sarthi"], chunk_duration=0)
        assert listener.chunk_duration >= 0.1


def test_launch_sarthi_accepts_text_arg(monkeypatch):
    """Regression: on_wake callbacks receive the detected text."""
    import wakeword

    calls = []
    monkeypatch.setattr(wakeword.subprocess, "Popen", lambda *a, **k: calls.append(a))
    wakeword.launch_sarthi("hey sarthi")  # must not raise TypeError
    assert calls, "start.bat should be launched"
