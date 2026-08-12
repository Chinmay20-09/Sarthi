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
WAKE_WORDS = ["Open","I am here"]

# ════════════════════════════════════════════════════════════════════
# LAUNCH SETTINGS
# ════════════════════════════════════════════════════════════════════
# Seconds to wait after a wake word before another wake word is accepted.
# Prevents accidental double-launches (browser tabs).
LAUNCH_COOLDOWN = 30

# ════════════════════════════════════════════════════════════════════
# DORMANT MODE — pause the listener while Sarthi is running
# ════════════════════════════════════════════════════════════════════
# After a wake word launches Sarthi, the listener goes dormant (stops
# using the microphone) until Sarthi has been closed, then it listens
# again automatically. Sarthi's API health endpoint tells us whether it
# is still running.
DORMANT_WHILE_RUNNING = True

# Health endpoint used to detect whether Sarthi is still running.
SARTHI_HEALTH_URL = "http://127.0.0.1:8000/health"

# Max seconds to wait for Sarthi to finish booting after a wake word.
SARTHI_START_TIMEOUT = 90

# How often (seconds) the watcher checks Sarthi's status while dormant.
SARTHI_POLL_INTERVAL = 3.0

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

# ════════════════════════════════════════════════════════════════════
# PERFORMANCE — lighter model = less CPU/RAM while listening
# ════════════════════════════════════════════════════════════════════
# Whisper model used by the wake word listener. The background launcher
# (wakeword.bat) uses this, so a small model keeps the system light.
#   "tiny"  → lightest & fastest, ~40MB RAM (recommended for background)
#   "base"  → middle ground
#   "small" → most accurate but heaviest (~250MB RAM, more CPU)
WHISPER_MODEL = "tiny"
