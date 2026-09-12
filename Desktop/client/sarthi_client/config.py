"""Sarthi Desktop client configuration.

Single source of truth for where the Desktop client finds the Sarthi
Backend. Resolution order (first match wins):

1. ``SARTHI_BACKEND_URL`` environment variable
2. ``backend_url`` key in ``sarthi_client.json`` next to this package
   (or next to the frozen exe — see ``config_file_candidates``)
3. the built-in default (the locally running backend)

Change the URL in exactly one place (env var or JSON file) to point the
client at a LAN/remote/cloud backend — no code changes.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# Default: the locally running Backend (sarthi.bat / start.bat).
# Loopback on purpose — the backend is never exposed publicly by default.
DEFAULT_BACKEND_URL = "http://127.0.0.1:8000"

# Network settings
REQUEST_TIMEOUT = 300.0  # seconds; Hermes-backed commands can be slow

ENV_BACKEND_URL = "SARTHI_BACKEND_URL"
CONFIG_FILE_NAME = "sarthi_client.json"


def config_file_candidates() -> list[Path]:
    """Where the optional client config file may live, in priority order.

    - next to the frozen executable (PyInstaller, sys.frozen)
    - next to this package (source checkout: Desktop/client/)
    """
    candidates: list[Path] = []

    if getattr(sys, "frozen", False):  # running as sarthi.exe
        exe_dir = Path(sys.executable).resolve().parent
        candidates.append(exe_dir / CONFIG_FILE_NAME)

    candidates.append(Path(__file__).resolve().parent / CONFIG_FILE_NAME)
    return candidates


def load_configured_backend_url() -> str | None:
    """Read ``backend_url`` from the first config file that exists."""
    for path in config_file_candidates():
        try:
            if not path.is_file():
                continue
            data = json.loads(path.read_text(encoding="utf-8"))
            url = data.get("backend_url")
            if isinstance(url, str) and url.strip():
                return url.strip()
        except (OSError, ValueError):
            continue  # unreadable/malformed file — try the next candidate
    return None


def get_backend_url() -> str:
    """Resolve the backend URL (env var > config file > default).

    Never hardcode the URL anywhere else — everything reads it from here.
    """
    env_url = os.environ.get(ENV_BACKEND_URL, "").strip()
    if env_url:
        return env_url.rstrip("/")

    file_url = load_configured_backend_url()
    if file_url:
        return file_url.rstrip("/")

    return DEFAULT_BACKEND_URL
