"""Sarthi command dispatcher.

Routes top-level Sarthi commands to the appropriate subsystem:

    list                 -- list all skills (registry)
    help <skill>         -- show a skill's help
    <skill-id> ...       -- run a skill directly (passthrough to its CLI)

Skills are executed through their own `__main__.py`, so the same capability
logic runs for both the CLI and the Sarthi skill/adapter layers.
"""

import json
import subprocess
import sys

__all__ = ["dispatch", "build_parser"]


def build_parser() -> argparse.ArgumentParser:
    """Configure the top-level Sarthi CLI."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Sarthi -- unified entry point for all skills (independent + programmatic).",
        prog="python -m sarthi",
    )
    parser.add_argument(
        "--version",
        action="version",
        version="Sarthi 1.0.0",
        help="Show the Sarthi version and exit.",
    )
    parser.add_argument(
        "--registry",
        action="store_true",
        help="Print the discovered skill registry as JSON and exit.",
    )
    # The top-level parser uses a single positional `command` that accepts any
    # value. Skills are invoked directly with `python -m sarthi <skill-id> ...`.
    parser.add_argument(
        "command",
        nargs="?",
        default=None,
        help=(
            "The command: a skill ID (e.g. speech, scanner) to run directly, "
            "or one of: list, help, registry."
        ),
    )
    # Sub-options that apply to the `list` command
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the skill list as JSON.",
    )
    parser.add_argument(
        "--enabled-only",
        action="store_true",
        help="List only enabled skills.",
    )
    return parser


    return parser


def dispatch(argv: list[str] | None = None) -> int:
    """Dispatch a command to the appropriate subsystem.

    Parses the top-level Sarthi command and routes it to list/help or a
    skill's own CLI. Registers the skill registry (filesystem-based due to
    the pre-existing circular-import issue) on first use.
    """
    import argparse

    parser = build_parser()
    # Use parse_known_args so that skill-specific flags (e.g. --duration,
    # --language) pass through to the skill's own CLI instead of being
    # consumed here as sub-options. Known flags (--json, --enabled-only)
    # are consumed normally; everything else goes to the skill.
    args, unknown = parser.parse_known_args(argv)

    # Build the registry (filesystem-based discovery)
    from . import get_registry

    registry = get_registry()

    command = args.command
    # Known flags for the `list` command must be extracted from the
    # unknown args. parse_known_args puts them in `unknown`, so check.
    list_json = getattr(args, "json", False)
    list_enabled = getattr(args, "enabled_only", False)
    rest = unknown if command not in ("list", "registry") else []

    # If command is `help`, the skill ID is the first arg in `rest`
    # (e.g. `sarthi help speech` -> command=help, rest=['speech'])
    if command == "help" and rest:
        args.skill_id = rest[0]
        rest = rest[1:]

    args.json = list_json
    args.enabled_only = list_enabled

    # `list` handled by sarthi itself
    if command == "list":
        if args.json:
            print(json.dumps(registry.list_skills(), indent=2, ensure_ascii=False))
        elif args.enabled_only:
            for meta in registry.list_skills():
                print(f"  {meta['id']:<22} {meta['name']}")
        else:
            for meta in registry.list_skills():
                print(f"  {meta['id']:<22} {meta['name']}")
        return 0

    if command == "registry":
        print(json.dumps(registry.list_skills(), indent=2, ensure_ascii=False))
        return 0

    # `help` handled by sarthi itself (need skill_id which may be in `rest`)
    if command == "help" and rest:
        args.skill_id = rest[0]
        rest = rest[1:]
    if command == "help":
        from .commands import _print_help
        return _print_help(args.skill_id, registry)

    # Pass everything else through to the skill's own CLI
    return _run_skill(command, registry, rest)


def _print_help(skill_id: str | None, registry: "SkillRegistry") -> int:
    """Print help for a skill or a general overview."""
    if skill_id is None:
        print("Sarthi -- unified entry point for all skills.")
        print()
        print("Usage:")
        print("    python -m sarthi list              List all installed skills.")
        print("    python -m sarthi help <skill>      Show help for a skill.")
        print("    python -m sarthi <skill> <args>    Run a skill directly.")
        print()
        print("Installed skills:")
        for meta in registry.list_skills():
            print(f"  - {meta['id']:<22} {meta['name']}")
        return 0

    metadata = registry.get_metadata(skill_id)
    if metadata is None:
        print(f"ERROR: unknown skill: {skill_id}", file=sys.stderr)
        print(f"Run `python -m sarthi list` to see installed skills.", file=sys.stderr)
        return 1

    print(f"Sarthi help: {metadata['name']} ({metadata['id']})")
    print("-" * 40)
    print(f"Version : {metadata['version']}")
    print(f"Enabled : {metadata['enabled']}")
    print(f"Description:")
    print(f"  {metadata['description']}")
    print()
    print("CLI reference:")
    print(f"    python -m sarthi {skill_id} --help")
    print()
    print("Manifest commands:")
    for cmd in metadata.get("commands", []):
        print(f"    {cmd}")
    return 0


def _run_skill(skill_id: str, registry: "SkillRegistry", args: list[str]) -> int:
    """Run a skill directly by invoking its own __main__.py."""
    # Build the command: `python -m skills.<skill_id>` followed by the remaining
    # arguments from the sarthi invocation.
    module = f"skills.{skill_id}"

    # Reconstruct the original argv for the subprocess
    sarthi_argv = sys.argv[1:]
    # Find the index of the skill id in sys.argv
    try:
        idx = sarthi_argv.index(skill_id)
    except ValueError:
        idx = 0

    # Use args.rest (the REMAINDER args) as the payload
    leftover = args

    cmd = [sys.executable, "-m", module] + leftover
    return _run_subprocess(cmd)


def _run_subprocess(cmd: list[str]) -> int:
    """Run a subprocess and propagate its exit code."""
    result = subprocess.run(cmd)
    return result.returncode
