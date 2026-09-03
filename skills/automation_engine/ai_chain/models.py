"""
ai_chain/models.py

Data models for the AI-chain automation module.

A chain is a list of AI steps. Each step is a website-backed AI
(ChatGPT, Gemini, ...) that Sarthi drives by controlling the laptop:

    step 1: send the user's query to AI1 (e.g. ChatGPT)
    step 2: paste AI1's response into AI2 (e.g. Gemini) as the prompt
    step 3: save every response (and downloaded images) to a run folder

The models are pure data — no automation imports live here, so this
module is safe to import (and unit-test) anywhere.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class SiteSpec:
    """
    Everything the driver needs to operate one AI website.

    Screen coordinates are stored as *fractions* of the browser window
    (0.0 - 1.0) so a single calibration works across screen sizes. They
    are converted to real pixels against the live window rectangle.
    """

    key: str  # canonical id: "chatgpt", "gemini"
    label: str  # display name: "ChatGPT"
    url: str  # landing URL the driver opens
    title_keyword: str  # substring found in the browser window title
    # Where the message composer sits inside the window (fraction x, y).
    composer: tuple[float, float] = (0.5, 0.95)
    # Where to click before Select-All + Copy so a real caret is NOT in
    # the composer textarea (which would select the textarea, not the page).
    read_point: tuple[float, float] = (0.5, 0.3)
    # Whether this AI can produce images (triggers the download step).
    image_capable: bool = False
    # Where the download/copy affordance of the last generated image sits
    # (fraction x, y). None = estimate from composer position.
    image_download_point: tuple[float, float] | None = None
    # Timings (seconds).
    page_load_wait: float = 6.0
    poll_interval: float = 4.0
    max_wait: float = 180.0
    stable_polls: int = 2  # reads that must match before "done"
    # Text markers that end a copied transcript (footer noise to trim).
    footer_markers: tuple[str, ...] = ()


@dataclass(frozen=True)
class ChainRequest:
    """A user-requested chain: query through AI1 into AI2."""

    query: str
    ai1: str = "chatgpt"
    ai2: str = "gemini"
    save_images: bool = True

    def __post_init__(self) -> None:
        if not self.query.strip():
            raise ValueError("Chain query must not be empty")
        if self.ai1 == self.ai2:
            raise ValueError("AI1 and AI2 must be different sites")


@dataclass
class StepOutcome:
    """Result of one AI step in the chain."""

    index: int
    site_key: str
    site_label: str
    prompt: str
    response: str = ""
    error: str = ""
    artifacts: list[Path] = field(default_factory=list)
    duration_ms: int = 0

    @property
    def success(self) -> bool:
        return not self.error


@dataclass
class ChainOutcome:
    """Result of a full chain run."""

    request: ChainRequest
    success: bool
    status: str  # "planned" | "completed" | "aborted" | "failed"
    steps: list[StepOutcome] = field(default_factory=list)
    run_dir: Path | None = None
    message: str = ""
