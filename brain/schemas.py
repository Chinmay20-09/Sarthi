"""
Legacy data models for Sarthi's Brain.

Backward-compatibility re-export:
    Intent — Imported from brain/intent.py (the canonical location)

NEW CODE SHOULD IMPORT FROM:
    from brain.intent import Intent
"""

from brain.intent import Intent as _Intent

# Re-export Intent from its canonical location
Intent = _Intent
