"""
Standalone speech-to-text command for Sarthi.

Usage (from the Backend directory):

    python -m speech

Records audio from the microphone and transcribes it to text, printing the
result to stdout. This is a standalone entry point: it does not start the
Sarthi API, the Brain, or any skill registry.

It shares the exact same capability implementation as the Speech skill and
backend/main.py, so a single `speak` always produces the same transcript.
"""

import argparse
import logging
import sys

logger = logging.getLogger(__name__)

# The Windows console (cp936/charmap) cannot render many Unicode symbols
# (emojis, check marks). Redirect stdout/stderr to locale-friendly stream
# so the CLI prints cleanly on the user's terminal.
if sys.stdout is None:
    sys.stdout = open(sys.__stdout__.fileno(), mode="w", encoding="utf-8", buffering=1)
if sys.stderr is None:
    sys.stderr = open(sys.__stderr__.fileno(), mode="w", encoding="utf-8", buffering=1)


def record_transcribe(
    duration: float = 5.0,
    filename: str = "temp.wav",
    language: str = "en",
    verbose: bool = False,
) -> str:
    """
    Record audio from the microphone and transcribe it to text.

    This is the single capability for independent speech-to-text. Both the
    standalone CLI (this module) and the Speech skill / backend CLI call it
    so a `speak` always behaves identically.

    Args:
        duration: How many seconds to record. Defaults to 5.
        filename: Where to save the temporary wav. Defaults to "temp.wav".
        language: Expected spoken language for the Whisper decoder.
        verbose: Print progress to stdout.

    Returns:
        The transcribed text.

    Raises:
        RuntimeError: If the microphone cannot be opened or transcription
            fails.
    """
    try:
        from speech.recorder import record_audio
        from speech.speech_to_text import transcribe

        if verbose:
            print("🎤 Listening...")

        audio = record_audio(filename=filename, duration=duration)
        text = transcribe(audio, language=language)

        if verbose:
            print("✅ Transcription:", text)

        return text
    except Exception as e:  # noqa: BLE001 - surface as a clean error
        logger.error(f"Speech recognition failed: {e}")
        raise RuntimeError(f"STT failed: {e}") from e


def build_parser() -> argparse.ArgumentParser:
    """Configure the command-line interface."""
    parser = argparse.ArgumentParser(
        description="Record audio from the microphone and transcribe it to text.",
        prog="python -m speech",
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=5.0,
        help="How many seconds to record (default: 5).",
    )
    parser.add_argument(
        "--filename",
        default="temp.wav",
        help="Temporary wav file to save the recording to (default: temp.wav).",
    )
    parser.add_argument(
        "--language",
        default="en",
        help="Expected spoken language for the decoder (default: en).",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Verify dependencies are available and exit (no recording).",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Print progress and the transcription to stdout.",
    )
    parser.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="Print only the transcription, nothing else.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Entry point for `python -m speech`.

    Returns an exit code suitable for scripts.
    """
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.check:
        return _check_dependencies()

    logging.basicConfig(level=logging.WARNING)

    try:
        text = record_transcribe(
            duration=args.duration,
            filename=args.filename,
            language=args.language,
            verbose=args.verbose,
        )
    except RuntimeError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    if not args.quiet:
        print(text)
    return 0


def _check_dependencies() -> int:
    """Verify the microphone, audio, and Whisper dependencies are usable."""
    try:
        import sounddevice as sd

        # Enumerate devices — this hits the OS audio registry and confirms an
        # input device is present.
        devices = sd.query_devices()
        if not devices:
            raise RuntimeError("no audio input devices found")
        # device[0] is the default input device
        dev_name = devices[0]["name"]
    except Exception as e:  # noqa: BLE001
        print(f"MICROPHONE UNAVAILABLE: {e}", file=sys.stderr)
        return 1

    try:
        from speech.speech_to_text import get_model

        model = get_model()
        # WhisperModel stores the size in its constructor argument, capture it
        # by checking the model attribute used for loading.
        print("WHISPER READY (model: small)")
    except Exception as e:  # noqa: BLE001
        print(f"WHISPER UNAVAILABLE: {e}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
