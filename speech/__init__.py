"""
Speech package for Sarthi — Audio capture and transcription.

Components:
    recorder.py       — Record audio from microphone
    speech_to_text.py — Transcribe audio via Whisper
    wake_word.py      — Wake word detection (future)

Public API:
    record_audio() -> str  — Record and save audio file
    transcribe(path) -> str — Transcribe audio file to text
"""
