import json
from pathlib import Path

SKILLS_DIR = Path(__file__).parent


def load_skills():
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
