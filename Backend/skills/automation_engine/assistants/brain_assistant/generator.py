"""
brain_assistant/generator.py
"""

import json
from pathlib import Path

from .constants import STOPWORDS


class AssistantGenerator:
    def generate(
        self,
        manifest_path: Path,
        output_path: Path,
    ) -> None:
        manifest = self._load_manifest(manifest_path)

        assistant = self._build_assistant(manifest)

        self._save(output_path, assistant)

    # --------------------------------------------------

    def _load_manifest(self, path: Path) -> dict:
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    # --------------------------------------------------

    def _build_assistant(self, manifest: dict) -> dict:
        commands = []

        for command in manifest.get("commands", []):
            commands.append(self._parse_command(command))

        return {"id": manifest["id"], "brain": {"commands": commands}}

    # --------------------------------------------------

    def _parse_command(self, command: str) -> dict:
        original = command

        words = command.lower().replace("?", "").split()

        if not words:
            return {"text": original, "action": "", "target": ""}

        action = words[0]

        target = [word for word in words[1:] if word not in STOPWORDS]

        return {"text": original, "action": action, "target": " ".join(target)}

    # --------------------------------------------------

    def _save(
        self,
        path: Path,
        assistant: dict,
    ) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(
                assistant,
                f,
                indent=4,
                ensure_ascii=False,
            )
