"""
Skill discovery and loading for Sarthi.

Provides two levels of skill loading:
    1. load_skills() — reads manifest.json metadata only (for UI display)
    2. load_skill_instances() — dynamically imports and instantiates skill classes
"""

import importlib
import json
import logging
import os
from pathlib import Path

from skills.base import BaseSkill

logger = logging.getLogger(__name__)

SKILLS_DIR = Path(__file__).parent


def load_skills():
    """Load skill metadata from manifest.json files (for UI / listing)."""
    skills = []

    for folder in SKILLS_DIR.iterdir():
        if not folder.is_dir():
            continue

        manifest = folder / "manifest.json"

        if not manifest.exists():
            continue

        try:
            with open(manifest, encoding="utf-8") as f:
                skills.append(json.load(f))
        except Exception:
            continue

    return skills


def load_skill_instances() -> list[BaseSkill]:
    """
    Dynamically import and instantiate all installed skills.

    Scans each subdirectory under skills/ for a main.py module,
    discovers classes that inherit from BaseSkill, and attempts
    to instantiate them.

    Constructor requirements are handled gracefully:
        - No-arg constructors are instantiated directly.
        - Skill classes that need config can read environment variables.

    Returns:
        List of instantiated skill objects that are ready for execution.
    """
    instances: list[BaseSkill] = []

    for folder in SKILLS_DIR.iterdir():
        if not folder.is_dir() or folder.name.startswith("_"):
            continue

        manifest_file = folder / "manifest.json"
        main_file = folder / "main.py"

        if not manifest_file.exists() or not main_file.exists():
            continue

        try:
            with open(manifest_file, encoding="utf-8") as f:
                manifest = json.load(f)

            if not manifest.get("enabled", True):
                logger.debug(f"Skill '{folder.name}' is disabled in manifest, skipping")
                continue

            # Dynamically import the main module
            module_name = f"skills.{folder.name}.main"
            module = importlib.import_module(module_name)

            # Find the BaseSkill subclass in the module
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if isinstance(attr, type) and issubclass(attr, BaseSkill) and attr is not BaseSkill:
                    # Try to instantiate the skill
                    instance = _instantiate_skill(attr, folder.name)
                    if instance is not None:
                        instances.append(instance)
                    break  # One skill class per module

        except Exception as e:
            logger.warning(f"Failed to load skill '{folder.name}': {e}")
            continue

    logger.info(f"Loaded {len(instances)} skill(s): {[s.name for s in instances]}")
    return instances


def _instantiate_skill(skill_class: type[BaseSkill], folder_name: str) -> BaseSkill | None:
    """
    Attempt to instantiate a skill class.

    Tries several strategies in order:
        1. No-arg constructor
        2. Constructor with env-var-based kwargs
        3. Constructor with positional args from env vars
    """
    import inspect

    try:
        # Strategy 1: No-arg constructor
        return skill_class()
    except TypeError:
        pass

    try:
        # Strategy 2: Read constructor signature and try env vars
        sig = inspect.signature(skill_class.__init__)
        params = sig.parameters

        kwargs = {}
        for param_name, param in params.items():
            if param_name == "self":
                continue
            # Try env var: SKILL_{FOLDER}_{PARAM} in UPPERCASE
            env_key = f"SKILL_{folder_name.upper()}_{param_name.upper()}"
            env_val = os.environ.get(env_key)
            if env_val is not None:
                kwargs[param_name] = env_val

        if kwargs:
            return skill_class(**kwargs)
    except Exception:
        pass

    logger.warning(
        f"Could not instantiate skill '{folder_name}' — "
        f"missing required constructor args. "
        f"Set env vars like SKILL_{folder_name.upper()}_USERNAME"
    )
    return None
