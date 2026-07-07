from faster_whisper import WhisperModel

model = WhisperModel(
    "small",
    device="cpu",
    compute_type="int8",
)


def transcribe(audio_path):

    segments, info = model.transcribe(
        audio_path,
        language="en",
        beam_size=5,
        vad_filter=True,
    )

    print(f"Language: {info.language}")
    print(f"Probability: {info.language_probability:.2f}")

    text = []

    for segment in segments:
        print(segment.text)
        text.append(segment.text.strip())

    return " ".join(text)