"""
Skill Registry — formal discovery and registration system for Sarthi skills.

Provides:
    1. Automatic discovery of installed skills from the skills/ directory
    2. Metadata-based registration (reads manifest.json)
    3. Plugin-style support (drop a folder into skills/, it gets picked up)
    4. Clean interface for Brain to discover and load skills
    5. Skill lifecycle management (enable, disable, list)

Usage:
    from skills.registry import SkillRegistry

    registry = SkillRegistry()

    # Discover all installed skills
    registry.discover()

    # Get a specific skill instance
    skill = registry.get_skill("project_tracker")

    # List all registered skills (metadata only)
    for meta in registry.list_skills():
        print(f"{meta['name']} v{meta['version']}")

    # Get all skill instances for the executor
    instances = registry.get_all_instances()
"""

import importlib
import inspect
import json
import logging
import os
from pathlib import Path
from typing import Any

from skills.base import BaseSkill

logger = logging.getLogger(__name__)

# Default skills directory
SKILLS_DIR = Path(__file__).parent


class SkillMetadata:
    """
    Metadata for a discovered skill.

    Contains information from manifest.json and runtime discovery.
    This is the SKILL's identity card — no code is imported.
    """

    def __init__(
        self,
        skill_id: str,
        name: str,
        description: str,
        version: str,
        directory: Path,
        enabled: bool = True,
        icon: str = "extension",
        commands: list[str] | None = None,
    ):
        self.skill_id = skill_id
        self.name = name
        self.description = description
        self.version = version
        self.directory = directory
        self.enabled = enabled
        self.icon = icon
        self.commands = commands or []

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary (for UI display)."""
        return {
            "id": self.skill_id,
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "enabled": self.enabled,
            "icon": self.icon,
            "commands": self.commands,
        }

    @classmethod
    def from_manifest(cls, manifest_path: Path) -> "SkillMetadata | None":
        """
        Create from a manifest.json file.

        Args:
            manifest_path: Path to manifest.json

        Returns:
            SkillMetadata instance, or None if invalid
        """
        try:
            with open(manifest_path, encoding="utf-8") as f:
                data = json.load(f)

            return cls(
                skill_id=data.get("id", manifest_path.parent.name),
                name=data.get("name", manifest_path.parent.name),
                description=data.get("description", ""),
                version=data.get("version", "0.1.0"),
                directory=manifest_path.parent,
                enabled=data.get("enabled", True),
                icon=data.get("icon", "extension"),
                commands=data.get("commands", []),
            )
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Invalid manifest {manifest_path}: {e}")
            return None

    def __repr__(self) -> str:
        return f"<SkillMetadata '{self.skill_id}' v{self.version}>"


class SkillRegistry:
    """
    Formal registry for all Sarthi skills.

    Responsibilities:
        - Discover skills from the filesystem
        - Load skill metadata (no code execution)
        - Instantiate skills on demand
        - Provide lifecycle management (enable/disable)
        - Support plugin-style installation

    The registry is the SINGLE source of truth for what skills exist.
    No other module should scan the skills/ directory directly.
    """

    def __init__(self, skills_dir: Path | None = None):
        """
        Initialize the registry.

        Args:
            skills_dir: Directory containing skill packages.
                       Defaults to the parent of this file (skills/).
        """
        self._skills_dir = skills_dir or SKILLS_DIR
        self._metadata: dict[str, SkillMetadata] = {}  # skill_id -> metadata
        self._instances: dict[str, BaseSkill] = {}  # skill_id -> instance
        self._discovered = False

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    def discover(self) -> list[SkillMetadata]:
        """
        Scan the skills directory for installed skills.

        Scans each subdirectory for a manifest.json file.
        If found, loads metadata. If not, attempts to discover
        the skill class directly from main.py.

        Returns:
            List of discovered SkillMetadata objects
        """
        self._metadata = {}
        self._instances = {}

        if not self._skills_dir.exists():
            logger.warning(f"Skills directory not found: {self._skills_dir}")
            self._discovered = True
            return []

        for folder in sorted(self._skills_dir.iterdir()):
            if not folder.is_dir() or folder.name.startswith("_"):
                continue

            metadata = self._discover_skill(folder)
            if metadata is not None:
                self._metadata[metadata.skill_id] = metadata
                logger.debug(f"Discovered skill: {metadata}")

        self._discovered = True
        logger.info(f"Discovered {len(self._metadata)} skill(s)")
        return list(self._metadata.values())

    def _discover_skill(self, folder: Path) -> SkillMetadata | None:
        """
        Try to discover a skill from a directory.

        Priority:
            1. manifest.json (metadata only — preferred)
            2. main.py + manifest.json (fallback for old style)

        Args:
            folder: Skill directory

        Returns:
            SkillMetadata or None
        """
        manifest_path = folder / "manifest.json"
        main_path = folder / "main.py"

        # Strategy 1: manifest.json
        if manifest_path.exists():
            metadata = SkillMetadata.from_manifest(manifest_path)
            if metadata is not None:
                return metadata

        # Strategy 2: main.py exists but no valid manifest
        if main_path.exists():
            # Generate metadata from the module
            skill_id = folder.name
            return SkillMetadata(
                skill_id=skill_id,
                name=skill_id.replace("_", " ").title(),
                description=f"Skill: {skill_id}",
                version="0.1.0",
                directory=folder,
                enabled=True,
            )

        # Neither manifest nor main.py — not a skill
        return None

    # ------------------------------------------------------------------
    # Instantiation
    # ------------------------------------------------------------------

    def instantiate(self, skill_id: str) -> BaseSkill | None:
        """
        Create an instance of a skill by its ID.

        Dynamically imports the skill's main module and finds
        the BaseSkill subclass.

        Args:
            skill_id: The skill's ID (folder name or manifest id)

        Returns:
            Instantiated BaseSkill, or None if failed
        """
        # Return cached instance if available
        if skill_id in self._instances:
            return self._instances[skill_id]

        metadata = self._metadata.get(skill_id)
        if metadata is None:
            logger.warning(f"Unknown skill: {skill_id}")
            return None

        if not metadata.enabled:
            logger.debug(f"Skill '{skill_id}' is disabled, skipping")
            return None

        main_path = metadata.directory / "main.py"
        if not main_path.exists():
            logger.warning(f"Skill '{skill_id}' has no main.py")
            return None

        try:
            module_name = f"skills.{metadata.directory.name}.main"
            module = importlib.import_module(module_name)

            # Find the BaseSkill subclass
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if isinstance(attr, type) and issubclass(attr, BaseSkill) and attr is not BaseSkill:
                    instance = self._instantiate_class(attr, metadata.directory.name)
                    if instance is not None:
                        self._instances[skill_id] = instance
                        logger.info(f"Instantiated skill: {instance.name} v{instance.version}")
                        return instance

            logger.warning(f"No BaseSkill subclass found in {module_name}")
            return None

        except Exception as e:
            logger.warning(f"Failed to instantiate skill '{skill_id}': {e}")
            return None

    def _instantiate_class(
        self, skill_class: type[BaseSkill], folder_name: str
    ) -> BaseSkill | None:
        """
        Attempt to instantiate a skill class.

        Tries several strategies:
            1. No-arg constructor
            2. Constructor with env-var-based kwargs
            3. Constructor with positional args from env vars
        """
        try:
            return skill_class()
        except TypeError:
            pass

        try:
            sig = inspect.signature(skill_class.__init__)
            params = sig.parameters

            kwargs = {}
            for param_name, param in params.items():
                if param_name == "self":
                    continue
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

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_skill(self, skill_id: str) -> BaseSkill | None:
        """
        Get a skill instance by ID (auto-instantiates if needed).

        Args:
            skill_id: The skill's ID

        Returns:
            Instantiated BaseSkill, or None
        """
        if not self._discovered:
            self.discover()

        if skill_id in self._instances:
            return self._instances[skill_id]

        return self.instantiate(skill_id)

    def get_metadata(self, skill_id: str) -> SkillMetadata | None:
        """Get metadata for a skill by ID."""
        if not self._discovered:
            self.discover()
        return self._metadata.get(skill_id)

    def list_skills(self) -> list[dict[str, Any]]:
        """List all discovered skills as dictionaries (for UI display)."""
        if not self._discovered:
            self.discover()
        return [meta.to_dict() for meta in self._metadata.values()]

    def list_enabled(self) -> list[SkillMetadata]:
        """List only enabled skills."""
        if not self._discovered:
            self.discover()
        return [meta for meta in self._metadata.values() if meta.enabled]

    def get_all_instances(self) -> list[BaseSkill]:
        """
        Get instances of all enabled skills.

        Returns:
            List of instantiated BaseSkill objects
        """
        if not self._discovered:
            self.discover()

        instances = []
        for skill_id, metadata in self._metadata.items():
            if not metadata.enabled:
                continue

            instance = self.get_skill(skill_id)
            if instance is not None:
                instances.append(instance)

        return instances

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def enable(self, skill_id: str) -> bool:
        """Enable a skill (sets enabled=True in manifest)."""
        metadata = self._metadata.get(skill_id)
        if metadata is None:
            return False
        metadata.enabled = True
        return self._update_manifest(skill_id)

    def disable(self, skill_id: str) -> bool:
        """Disable a skill (sets enabled=False in manifest)."""
        metadata = self._metadata.get(skill_id)
        if metadata is None:
            return False
        metadata.enabled = False
        self._instances.pop(skill_id, None)
        return self._update_manifest(skill_id)

    def _update_manifest(self, skill_id: str) -> bool:
        """Update the manifest.json file with current metadata."""
        metadata = self._metadata.get(skill_id)
        if metadata is None:
            return False

        manifest_path = metadata.directory / "manifest.json"
        if not manifest_path.exists():
            return False

        try:
            with open(manifest_path, encoding="utf-8") as f:
                data = json.load(f)

            data["enabled"] = metadata.enabled

            with open(manifest_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4, ensure_ascii=False)

            return True
        except (OSError, json.JSONDecodeError) as e:
            logger.error(f"Failed to update manifest for '{skill_id}': {e}")
            return False

    def refresh(self) -> list[SkillMetadata]:
        """Re-discover all skills (clears cache)."""
        self._metadata = {}
        self._instances = {}
        self._discovered = False
        return self.discover()

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def count(self) -> int:
        """Number of discovered skills."""
        if not self._discovered:
            self.discover()
        return len(self._metadata)

    @property
    def skills_dir(self) -> Path:
        """The skills directory path."""
        return self._skills_dir


# Global singleton instance
_registry: SkillRegistry | None = None


def get_registry() -> SkillRegistry:
    """
    Get the global SkillRegistry instance.

    Singleton pattern for efficiency.

    Returns:
        SkillRegistry instance
    """
    global _registry
    if _registry is None:
        _registry = SkillRegistry()
        _registry.discover()
    return _registry
