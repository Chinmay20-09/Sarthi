"""
ai_chain/storage.py

Per-run result storage for AI chains.

Each run gets its own folder under <project>/results/ai_chain/ (git-ignored):

    results/ai_chain/20260903_121530_image-of-the-sarthi-workflow/
        ├── 01_query.txt
        ├── 02_step1_chatgpt_response.txt
        ├── 03_step2_gemini_response.txt
        └── gemini_image_1.png        (downloaded image, if any)
"""

from __future__ import annotations

import re
import shutil
from datetime import datetime
from pathlib import Path

from config import PROJECT_ROOT

RESULTS_ROOT = PROJECT_ROOT / "results" / "ai_chain"


def slugify(text: str, limit: int = 40) -> str:
    """Turn free text into a safe filename fragment."""
    cleaned = re.sub(r"[^A-Za-z0-9]+", "-", (text or "").strip().lower()).strip("-")
    return cleaned[:limit].rstrip("-") or "run"


class ChainRun:
    """A single chain execution's output folder."""

    def __init__(self, query: str, root: Path | None = None):
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.dir = (root or RESULTS_ROOT) / f"{stamp}_{slugify(query)}"
        self.dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------

    def write_text(self, name: str, content: str) -> Path:
        """Write a text artifact (prompt/response) into the run folder."""
        path = self.dir / name
        path.write_text(content or "", encoding="utf-8")
        return path

    def harvest_file(self, source: Path, name: str | None = None) -> Path:
        """
        Move a file (e.g. an image the browser just downloaded) into the
        run folder. Falls back to a copy when the source cannot be moved.
        """
        target = self.dir / (name or source.name)
        if source == target:
            return target
        try:
            shutil.move(str(source), str(target))
        except OSError:
            shutil.copy2(str(source), str(target))
        return target
