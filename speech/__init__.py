"""
Speech package for Sarthi — Audio capture, transcription, and wake words.

Components:
    recorder.py       — Record audio from microphone
    speech_to_text.py — Transcribe audio via Whisper
    wake_word.py      — Wake word detection (WakeWordListener)

Public API:
    record_audio() -> str                 — Record and save audio file
    transcribe(path) -> str               — Transcribe audio to text
    WakeWordListener(wake_words, on_wake) — Continuous wake word listener
    detect_wake_word(wake_words) -> bool  — One-shot wake word check

The wake word phrases are configured in variable.py at the project root
and consumed by wakeword.py.
"""
