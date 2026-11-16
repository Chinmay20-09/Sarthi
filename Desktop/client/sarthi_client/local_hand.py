"""Physical app-launch operation for the Windows client layer."""

from __future__ import annotations

import os
from pathlib import Path


class LocalDesktopHand:
    """Launch one already-resolved Start Menu shortcut or executable."""

    def open_application(self, path: str) -> None:
        """Execute a concrete local inventory entry; never resolve user text."""
        if os.name != "nt":
            raise OSError("Local Windows application launch is unavailable on this platform.")
        launch_path = Path(path)
        if not launch_path.is_absolute() or not launch_path.is_file():
            raise FileNotFoundError(f"Application launch entry is unavailable: {path}")
        if launch_path.suffix.lower() == ".lnk":
            os.startfile(str(launch_path))
        elif launch_path.suffix.lower() == ".exe":
            os.startfile(str(launch_path), "open")
        else:
            raise ValueError("Only discovered Windows shortcuts and executables can be launched.")
