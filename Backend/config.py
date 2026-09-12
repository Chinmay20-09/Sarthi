"""
Central configuration for Sarthi.

All packages should read configuration from here.
Avoid scattered configuration across packages.
"""

from pathlib import Path

# Project paths
PROJECT_ROOT = Path(__file__).parent
SKILLS_DIR = PROJECT_ROOT / "skills"
KNOWLEDGE_DIR = PROJECT_ROOT / "knowledge"
UI_DIR = PROJECT_ROOT / "UI"

# Speech settings
SAMPLE_RATE = 16000
RECORDING_DURATION = 5  # seconds
RECORDING_FILE = "temp.wav"

# Whisper model settings
WHISPER_MODEL = "small"
WHISPER_DEVICE = "cpu"
WHISPER_COMPUTE_TYPE = "int8"

# API settings
API_HOST = "127.0.0.1"
API_PORT = 8000

# Logging
LOG_LEVEL = "INFO"
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
