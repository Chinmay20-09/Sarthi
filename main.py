"""
Sarthi MVP — Desktop AI Assistant.

Entry point for the command-line interface.
Uses BrainEngine for the full pipeline: interpret → plan → resolve → execute.
"""

from brain.engine import BrainEngine
from speech.recorder import record_audio
from speech.speech_to_text import transcribe
from utils.logger import setup_logging

setup_logging()

engine = BrainEngine()


def main() -> None:
    """Main CLI loop — record, transcribe, process, respond."""
    print("=" * 60)
    print("🎙️  Sarthi MVP")
    print("=" * 60)

    while True:
        input("\nPress ENTER to speak...")

        audio = record_audio()
        raw_text = transcribe(audio)

        print("\n📝 Whisper :", raw_text)

        response = engine.process(raw_text)

        print(f"\n🧠 Intent  : {response.intent.model_dump()}")
        print(f"🎯 Result  : {response.status} ({response.execution_ms:.0f}ms)")
        print(f"✅ Success : {response.success}")


if __name__ == "__main__":
    main()
