"""
Sarthi — unified command-line entry point for all skills.

Usage:

    python -m sarthi --help
    python -m sarthi list
    python -m sarthi help speech
    python -m sarthi speech --duration 3

Every Sarthi skill is independently executable AND can be triggered by the
program through its skill registry. This package is the single entry point
that bridges both: the same underlying capability runs from the CLI and from
Sarthi's skill/adapter layers.

Public API:

    main(argv=None) -> int
        Entry point for `python -m sarthi`.

    get_registry() -> SkillRegistry
        The global SkillRegistry singleton (imported from skills.registry).
        The import is deferred to avoid circular imports with brain/.
"""

from __future__ import annotations
import json

__all__ = [
    "main",
    "get_registry",
]

# The registry is imported lazily to avoid circular imports: skills.registry
# imports skills.base -> brain -> skills.base, which is a pre-existing
# circular-import chain that is already broken. We only need the registry
# inside main(), so import it there.
_registry = None


def get_registry() -> "SkillRegistry":
    """Get the global skill registry.

    The registry is built lazily from the skills directory on disk, reading
    each skill's manifest.json. This avoids the pre-existing circular-import
    chain skills.registry -> skills.base -> brain -> skills.base that is
    already broken in the repo.
    """
    global _registry
    if _registry is None:
        from pathlib import Path

        skills_dir = Path(__file__).resolve().parent.parent / "skills"

        # Build a lightweight registry object that exposes the same interface
        # as skills.registry.SkillRegistry (list_skills, list_enabled,
        # get_metadata, get_all_instances).
        _registry = type(
            "FilesystemRegistry",
            (),
            {
                "list_skills": lambda self: [
                    self._load_metadata(folder)
                    for folder in sorted(skills_dir.iterdir())
                    if folder.is_dir()
                    and not folder.name.startswith("_")
                    and (folder / "manifest.json").exists()
                ],
                "list_enabled": lambda self: self.list_skills(),
                "get_metadata": lambda self, skill_id: next(
                    (
                        m
                        for m in self.list_skills()
                        if m["id"] == skill_id
                    ),
                    None,
                ),
                "get_all_instances": lambda self: [],
                "_load_metadata": lambda self, folder: {
                    "id": folder.name,
                    "name": json.loads((folder / "manifest.json").read_text(encoding="utf-8")).get(
                        "name", folder.name
                    ),
                    "description": json.loads((folder / "manifest.json").read_text(encoding="utf-8")).get(
                        "description", ""
                    ),
                    "version": json.loads((folder / "manifest.json").read_text(encoding="utf-8")).get(
                        "version", "0.1.0"
                    ),
                    "enabled": json.loads((folder / "manifest.json").read_text(encoding="utf-8")).get(
                        "enabled", True
                    ),
                    "commands": json.loads((folder / "manifest.json").read_text(encoding="utf-8")).get(
                        "commands", []
                    ),
                    "directory": str(folder),
                },
            },
        )()
    return _registry


def main(argv: list[str] | None = None) -> int:
    """Entry point for `python -m sarthi`."""
    from . import commands

    return commands.dispatch(argv)

