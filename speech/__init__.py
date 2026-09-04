"""
Speech package for Sarthi — audio capture and transcription.

Components:
    recorder.py       — Record audio from microphone
    speech_to_text.py — Transcribe audio via Whisper

Public API:
    record_audio() -> str      — Record and save audio file
    transcribe(path) -> str    — Transcribe audio to text
"""