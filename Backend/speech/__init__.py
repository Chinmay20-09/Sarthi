"""
Speech package for Sarthi — audio capture and transcription.
 
Components:
    recorder.py       — Record audio from microphone
    speech_to_text.py — Transcribe audio via Whisper
    cli.py            — Standalone command-line entry point (single command)
 
Public API:
    record_audio() -> str      — Record and save audio file
    transcribe(path) -> str    — Transcribe audio to text
    main()                     — Standalone STT entry point
    record_transcribe()        — Shared record + transcribe capability
"""

from .cli import main, record_transcribe
from .recorder import record_audio
from .speech_to_text import transcribe

__all__ = [
"record_audio",
"transcribe",
"main",
"record_transcribe",
]
