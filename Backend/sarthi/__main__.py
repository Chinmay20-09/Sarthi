"""
Unified Sarthi command-line entry point.

Usage (from the Backend directory):

    python -m sarthi --help
    python -m sarthi list
    python -m sarthi help speech
    python -m sarthi speech --duration 3

The entry point is a thin dispatcher that uses the global SkillRegistry to
discover every installed skill. It exposes two surfaces:

    1. Skill management commands:
         list              — list all skills (id, name, description, version)
         help <skill>      — show a skill's CLI usage / manifest

    2. Skill execution passthrough:
         <skill-id> <args> — run a skill directly, forwarding arguments

Each skill is both independently executable (from this CLI) and triggerable
by Sarthi through its skill registry/adapter layer. The capability logic
lives in the skill, not in this dispatcher — this module only routes.

Example:
    python -m sarthi speech --duration 3
    python -m sarthi scanner --quiet
    python -m sarthi browser --open google --test
"""

from __future__ import annotations

from . import commands

__all__ = ["main"]


def main(argv: list[str] | None = None) -> int:
    """Entry point for `python -m sarthi`."""
    return commands.dispatch(argv)


if __name__ == "__main__":
    import sys

    sys.exit(main())
