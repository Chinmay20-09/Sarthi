"""
Action executors for Sarthi (DEPRECATED).

MIGRATION NOTICE: The old actions/ system has been deprecated in favor
of a proper skill-based architecture via skills/ and brain/executor.py.

Legacy modules preserved for backward compatibility:
    apps.py   — Delegates to skills/app_launcher/ (shim for old code)
    browser.py — Delegates to skills/browser/ (shim for old code)

NEW CODE SHOULD USE:
    from brain.engine import BrainEngine
    engine = BrainEngine()
    response = engine.process("open Chrome")
"""
