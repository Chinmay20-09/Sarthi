"""
ai_chain — laptop-controlled AI chains for the Automation Engine.

Sarthi takes over the keyboard and mouse to drive two AI websites in
sequence: the user's query goes to AI1 (e.g. ChatGPT), AI1's reply is
pasted into AI2 (e.g. Gemini) as the prompt, and every response (plus
any generated image) is saved into a run folder.

Public API:
    run_ai_chain(query, ai1, ai2) — orchestrate (or plan) a chain
    parse_chain_command(text)     — parse a spoken "chain ... from A to B"
    resolve_site(name)            — map an AI name/alias to its SiteSpec
    ScreenController              — low-level laptop-control primitives

Safety:
    - prints a HANDS-OFF warning + countdown before taking control
    - Ctrl+Alt+X aborts at any time
    - PyAutoGUI failsafe: moving the mouse into a screen corner aborts

Calibration:
    run ``python -m skills.automation_engine.ai_chain.calibrate`` to
    record exact on-screen points for your monitor & browser.
"""

from .calibration import resolve_site
from .chain import run_ai_chain
from .control import ScreenController
from .models import ChainOutcome, ChainRequest, SiteSpec, StepOutcome
from .parsing import parse_chain_command

__all__ = [
    "run_ai_chain",
    "parse_chain_command",
    "resolve_site",
    "ScreenController",
    "ChainRequest",
    "ChainOutcome",
    "StepOutcome",
    "SiteSpec",
]
