"""
Hands — Sarthi's physical execution layer.

A "hand" performs real computer interaction (launch apps, type, click,
read the clipboard, manage processes). Hands execute explicit, validated
operations; they never reason. The Brain decides what should happen —
a hand performs it.

    Brain → Executor / Skill → Hand → Windows

The Desktop hand lives in hands/desktop/.
"""
