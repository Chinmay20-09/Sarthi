"""
Sarthi wake word launcher.

Listens for the wake word phrase(s) configured in variable.py. When
detected, it runs start.bat — which boots the API + UI and opens the
Sarthi website in your default browser.

Usage:
    python wakeword.py          # keep listening (Ctrl+C to stop)
    python wakeword.py --once   # listen for a single wake word, then exit
"""

import argparse
import subprocess
import time
from pathlib import Path

import variable
from speech.wake_word import WakeWordListener, wake_word_matches

ROOT = Path(__file__).resolve().parent
START_BAT = ROOT / "start.bat"

_launched_at = 0.0


def launch_sarthi(_text: str = "") -> None:
    """Run start.bat to boot Sarthi and open the website.

    Accepts the detected text so it can be used directly as the
    WakeWordListener's on_wake callback.
    """
    global _launched_at

    now = time.monotonic()
    if now - _launched_at < variable.LAUNCH_COOLDOWN:
        remaining = int(variable.LAUNCH_COOLDOWN - (now - _launched_at))
        print(f"⏳ Already launched recently — ignoring (cooldown {remaining}s left).")
        return

    print("🚀 Wake word detected! Launching Sarthi...")
    try:
        subprocess.Popen(["cmd", "/c", str(START_BAT)], cwd=str(ROOT))
        _launched_at = now
    except OSError as e:
        print(f"❌ Could not run start.bat: {e}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Sarthi wake word launcher")
    parser.add_argument(
        "--once",
        action="store_true",
        help="listen for a single wake word, then exit",
    )
    args = parser.parse_args()

    # Fail fast with a friendly message if no microphone is available
    try:
        import sounddevice as sd

        sd.check_input_settings()
    except Exception as e:
        print(f"❌ No microphone available: {e}")
        print("   Plug in a microphone and try again.")
        return 1

    banner = "=" * 58
    print(banner)
    print("🎙️  Sarthi Wake Word Launcher")
    print("    Say:  " + "  |  ".join(variable.WAKE_WORDS))
    print("    Stop: Ctrl+C")
    print(banner)

    listener = WakeWordListener(
        variable.WAKE_WORDS,
        on_wake=launch_sarthi,
        energy_threshold=variable.ENERGY_THRESHOLD,
        chunk_duration=variable.CHUNK_DURATION,
        max_utterance=variable.MAX_UTTERANCE,
        silence_pause=variable.SILENCE_PAUSE,
    )

    if args.once:
        text = listener.listen_once(timeout=30)
        if text:
            print(f"🗣️  Heard: {text}")
            if wake_word_matches(text, variable.WAKE_WORDS):
                launch_sarthi()
        else:
            print("🤫 No speech detected.")
        return 0

    try:
        listener.listen_forever()
    except KeyboardInterrupt:
        listener.stop()
        print("\n👋 Stopped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
