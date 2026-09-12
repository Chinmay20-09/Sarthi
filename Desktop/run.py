"""Launcher for the Sarthi Desktop client.

Double-click equivalent for development (the real double-click target is
Desktop/sarthi.exe, built from Desktop/sarthi_client.spec):

    python Desktop/run.py            # or: python Desktop/client/run.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# Allow running this file directly (python Desktop/run.py) without
# installing anything: put Desktop/client on sys.path so the
# sarthi_client package resolves.
_CLIENT_DIR = Path(__file__).resolve().parent / "client"
if str(_CLIENT_DIR) not in sys.path:
    sys.path.insert(0, str(_CLIENT_DIR))

from sarthi_client.gui import main  # noqa: E402

if __name__ == "__main__":
    main()
