from speech.recorder import record_audio
from speech.speech_to_text import transcribe


def listen() -> str:
    """
    Record audio and return the transcribed text.
    """

    audio = record_audio()

    text = transcribe(audio)

    return text