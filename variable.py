"""
Sarthi user configuration.

Edit this file to customize Sarthi — no code changes needed.
The wake word launcher (wakeword.py) reads its settings from here.
"""

# ════════════════════════════════════════════════════════════════════
# WAKE WORD — the phrase(s) that launch Sarthi
# ════════════════════════════════════════════════════════════════════
# Say any of these phrases out loud to boot Sarthi (runs start.bat)
# and open the website. Matching is case-insensitive, so lowercase is
# fine. Add extra variations if Whisper sometimes mishears your voice.
WAKE_WORDS = ["hey sarthi", "hey sarti", "hey sarthy"]

# ════════════════════════════════════════════════════════════════════
# LAUNCH SETTINGS
# ════════════════════════════════════════════════════════════════════
# Seconds to wait after a wake word before another wake word is accepted.
# Prevents accidental double-launches (browser tabs).
LAUNCH_COOLDOWN = 30

# ════════════════════════════════════════════════════════════════════
# LISTENING SETTINGS — tune only if detection feels off
# ════════════════════════════════════════════════════════════════════
# Minimum loudness (0.0–1.0) treated as speech. Raise it if background
# noise triggers false detections; lower it if you speak softly.
ENERGY_THRESHOLD = 0.015

# How often the microphone is sampled (seconds).
CHUNK_DURATION = 0.5

# Longest single utterance that will be transcribed (seconds).
MAX_UTTERANCE = 6.0

# Silence this long (seconds) marks the end of your utterance.
SILENCE_PAUSE = 0.8
