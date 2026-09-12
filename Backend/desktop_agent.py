"""
Desktop agent — standalone entry point for the Desktop hand.

Runs the physical execution layer without the Brain: useful for
diagnostics today and the seam for a future ``Sarthi.exe`` desktop
runtime. The long-term architecture is:

    Sarthi Brain  ↔  (local IPC: DesktopRequest / DesktopResult)  ↔  Desktop Agent  →  Windows

No IPC server is implemented yet — this process currently offers:
    - ``--capabilities``  print the implemented/planned capability report
    - ``--self-test``     run read-only actions (active window, clipboard,
                          process list) and print the structured results
    - ``--exec ACTION [key=value ...]``  run one explicit action
                          (e.g. ``--exec open_url url=https://example.com``)

Every action still passes the hand's validation gate: only registered
actions with valid arguments run, and there is no shell or code
execution path in this process.

Usage:
    python desktop_agent.py --capabilities
    python desktop_agent.py --self-test
    python desktop_agent.py --exec get_active_window
"""

from __future__ import annotations

import argparse
import json
import sys


def _parse_exec_args(pairs: list[str]) -> dict:
    """Parse key=value pairs into action kwargs (values stay strings)."""
    kwargs: dict = {}
    for pair in pairs or []:
        if "=" not in pair:
            raise SystemExit(f"Invalid action argument (expected key=value): {pair!r}")
        key, value = pair.split("=", 1)
        kwargs[key] = value
    return kwargs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Sarthi Desktop hand — standalone agent")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--capabilities", action="store_true", help="print the capability report")
    group.add_argument("--self-test", action="store_true", help="run read-only actions")
    group.add_argument(
        "--exec",
        nargs="+",
        metavar=("ACTION", "KEY=VALUE"),
        help="run one explicit action with key=value arguments",
    )
    args = parser.parse_args(argv)

    # Import here so --help stays fast and dependency-free.
    from hands.desktop import DesktopHand

    desktop = DesktopHand()

    if args.capabilities:
        print(json.dumps(desktop.capabilities(), indent=2))
        return 0

    if args.self_test:
        checks = [
            ("get_active_window", {}),
            ("list_windows", {}),
            ("get_processes", {}),
            ("read_clipboard", {}),
        ]
        for action, kwargs in checks:
            result = desktop.execute(action, **kwargs)
            print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
        return 0

    action = args.exec[0]
    kwargs = _parse_exec_args(args.exec[1:])
    result = desktop.execute(action, **kwargs)
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    return 0 if result.get("success") else 1


if __name__ == "__main__":
    sys.exit(main())
