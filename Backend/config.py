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
API_HOST = "0.0.0.0"
API_PORT = 8000

# ---------------------------------------------------------------------------
# Desktop Agent IPC (Brain ↔ Desktop Agent transport)
#
# The Desktop Agent (Backend/desktop_agent.py --server) is a separate process
# — ideally on the Windows laptop — exposing the local DesktopHand over HTTP.
# The Brain reaches it only through hands/transport.py; nothing else in the
# Brain knows the network exists.
#
# Resolution order for every value: environment variable > value below.
# Overridable via Backend/.env (loaded by hermes.config.loader at startup)
# or the process environment.
#
#   SARTHI_DESKTOP_AGENT_HOST     host the agent binds / the client targets
#   SARTHI_DESKTOP_AGENT_PORT     TCP port for the IPC transport
#   SARTHI_DESKTOP_AGENT_TIMEOUT  client request timeout in seconds
#   SARTHI_DESKTOP_AGENT_MODE     Brain-side desktop execution mode:
#                                   "local"  -> in-process DesktopHand (default;
#                                               existing behaviour, unchanged)
#                                   "remote" -> route desktop actions to the
#                                               Desktop Agent over IPC
#
# Security: the transport carries only structured DesktopRequest actions that
# exist in the DesktopHand action registry. No shell, eval, or code execution
# crosses this boundary (see Backend/desktop_agent.py and docs/DESKTOP_AGENT_IPC.md).
# ---------------------------------------------------------------------------
DESKTOP_AGENT_HOST = "127.0.0.1"
DESKTOP_AGENT_PORT = 8765
DESKTOP_AGENT_TIMEOUT = 30.0  # seconds; desktop actions are short, but launches can lag
DESKTOP_AGENT_MODE = "local"  # "local" | "remote"

# Logging
LOG_LEVEL = "INFO"
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
