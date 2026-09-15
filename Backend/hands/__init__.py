"""
Hands — Sarthi's physical execution layer.

A "hand" performs real computer interaction (launch apps, type, click,
read the clipboard, manage processes). Hands execute explicit, validated
operations; they never reason. The Brain decides what should happen —
a hand performs it.

    Brain → Executor / Skill → Hand → Windows

Implementations of the ``Hand`` contract (hands/base.py):

    - hands/desktop/  DesktopHand — the local (same-machine) Windows hand
    - hands/remote.py RemoteDesktopHand — the same contract over the
      Brain ↔ Desktop Agent IPC transport (hands/transport.py); the
      Desktop Agent (desktop_agent.py --server) fronts a local DesktopHand
      on the Windows machine

Which one the Brain gets is decided in hands/local.py::get_desktop_hand
(mode ``SARTHI_DESKTOP_AGENT_MODE``: local | remote) — invisible above
the boundary.
"""
