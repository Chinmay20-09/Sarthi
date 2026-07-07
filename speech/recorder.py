import sounddevice as sd
from scipy.io.wavfile import write

SAMPLE_RATE = 16000


def record_audio(
    filename="temp.wav",
    duration=5,
):
    print("🎤 Listening...")

    recording = sd.rec(
        int(duration * SAMPLE_RATE),
        samplerate=SAMPLE_RATE,
        channels=1,
        dtype="int16",
    )

    sd.wait()

    write(filename, SAMPLE_RATE, recording)

    print("✅ Audio saved:", filename)

    return filename