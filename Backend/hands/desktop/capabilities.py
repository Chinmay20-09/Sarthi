"""
Desktop capabilities — the explicit allow-list of what the hand may do.

A capability is a declared, auditable permission. Every Desktop action
belongs to a capability; ``DesktopHand.execute`` refuses any action that
is not registered. The registry is intentionally static data: adding an
action means editing the table AND implementing its backend — nothing is
discovered dynamically, nothing is inferred.

Argument rules per action:
    - "required"                    → must be present (any type)
    - ("required", type)            → must be present and an instance of type
    - ("optional", default)         → optional, filled with default when absent
    - ("choices", [..])             → must be one of the listed values
Anything not in the spec is rejected: no arbitrary kwargs pass through.

Planned-but-not-implemented capabilities are listed in
``PLANNED_CAPABILITIES`` so documentation and the capability report can
distinguish real from aspirational.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Capability:
    """One auditable permission: an id, a description, and its actions."""

    id: str
    description: str
    actions: dict[str, dict[str, Any]] = field(default_factory=dict)


CAPABILITIES: dict[str, Capability] = {
    cap.id: cap
    for cap in (
        Capability(
            id="APPLICATION_LAUNCH",
            description="Launch installed applications by absolute path.",
            actions={
                "open_application": {
                    "path": ("required", str),
                    "name": ("optional", None),
                },
            },
        ),
        Capability(
            id="APPLICATION_CLOSE",
            description="Close an application by explicit process id.",
            actions={
                "close_application": {"pid": ("required", int), "name": ("optional", None)},
            },
        ),
        Capability(
            id="WINDOW_READ",
            description="Read the window list and foreground window (Win32).",
            actions={
                "list_windows": {},
                "get_active_window": {},
            },
        ),
        Capability(
            id="BROWSER_CONTROL",
            description="Open a URL in the default browser (http/https only).",
            actions={
                "open_url": {"url": ("required", str)},
            },
        ),
        Capability(
            id="KEYBOARD",
            description="Type text and send keys to the foreground window.",
            actions={
                "type_text": {"text": ("required", str)},
                "press_key": {"key": ("required", str)},
                "hotkey": {"keys": ("required", list)},
            },
        ),
        Capability(
            id="MOUSE",
            description="Move the mouse and click explicit coordinates.",
            actions={
                "move_mouse": {"x": ("required", (int, float)), "y": ("required", (int, float))},
                "click": {"x": ("required", (int, float)), "y": ("required", (int, float))},
            },
        ),
        Capability(
            id="CLIPBOARD",
            description="Read and write the system clipboard.",
            actions={
                "read_clipboard": {},
                "copy": {"text": ("required", str)},
                "paste": {},
            },
        ),
        Capability(
            id="FILESYSTEM_READ",
            description="Read files and list directories under configured roots.",
            actions={
                "read_file": {"path": ("required", str)},
                "list_directory": {"path": ("required", str)},
            },
        ),
        Capability(
            id="FILESYSTEM_WRITE",
            description="Create/delete files under configured allowed roots.",
            actions={
                "write_file": {"path": ("required", str), "content": ("required", str)},
                "delete_file": {"path": ("required", str)},
            },
        ),
        Capability(
            id="PROCESS_CONTROL",
            description="List processes; launch/terminate by explicit path/pid.",
            actions={
                "get_processes": {},
                "launch_process": {"path": ("required", str)},
                "terminate_process": {"pid": ("required", int)},
            },
        ),
    )
}

# Declared for the future, deliberately NOT registered on the hand yet.
PLANNED_CAPABILITIES: tuple[str, ...] = (
    "WINDOW_CONTROL",  # close/minimize/maximize/focus windows (Win32)
    "SHELL",  # explicit, allow-listed commands — needs a review gate
)

# Action name -> owning capability id (reverse index).
ACTIONS: dict[str, str] = {
    action: cap_id for cap_id, cap in CAPABILITIES.items() for action in cap.actions
}


def action_spec(action: str) -> dict[str, Any]:
    """Argument spec for one action; empty dict when the action is unknown."""
    cap_id = ACTIONS.get(action)
    if cap_id is None:
        return {}
    return CAPABILITIES[cap_id].actions.get(action, {})


def describe_capabilities() -> list[dict[str, Any]]:
    """JSON-friendly capability report (implemented only — see PLANNED_CAPABILITIES)."""
    return [
        {
            "id": cap.id,
            "description": cap.description,
            "actions": sorted(cap.actions),
        }
        for cap in CAPABILITIES.values()
    ]
