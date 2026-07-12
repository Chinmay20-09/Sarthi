from speech.recorder import record_audio
from speech.speech_to_text import transcribe

from brain.entity_resolver import EntityResolver
from brain.interpreter import interpret

from actions.executor import execute


resolver = EntityResolver()


def main():

    print("=" * 60)
    print("🎙️  Sarthi MVP")
    print("=" * 60)

    while True:

        input("\nPress ENTER to speak...")

        audio = record_audio()

        raw_text = transcribe(audio)

        print("\n📝 Whisper :", raw_text)

        intent = interpret(raw_text)
        if intent.target:
         intent.target = resolver.resolve(intent.target)
        print("🧩 Resolved Target:", intent.target)

        print("\n🧠 Interpreter:", intent.model_dump())

        print("🎯 Intent  :", intent.model_dump())

        execute(intent)


if __name__ == "__main__":
    main()