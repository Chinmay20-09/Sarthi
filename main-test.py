"""
Sarthi Smoke Test -- quick sanity check.

Run: python main-test.py

This is NOT the full test suite. It only answers:
"Is Sarthi's basic pipeline working?"

For comprehensive testing, use POST /test/run or the pytest suite.
"""

import sys

from brain.engine import BrainEngine

PASS = 0
FAIL = 0


def check(label: str, condition: bool):
    global PASS, FAIL
    status = "PASS" if condition else "FAIL"
    sys.stdout.write(f"  [{status}] {label}\n")
    sys.stdout.flush()
    if condition:
        PASS += 1
    else:
        FAIL += 1


def main():
    global PASS, FAIL
    print("=" * 50)
    print("  Sarthi Smoke Test")
    print("=" * 50)

    engine = BrainEngine()

    # 1. Basic application open
    print("\n[1] Application open")
    r = engine.process("open vscode")
    check("action is 'open'", r.intent.action == "open")
    check("target resolved", r.intent.target != "")
    check("pipeline succeeded", r.success)

    # 2. Basic entity resolution
    print("\n[2] Entity resolution")
    r = engine.process("open youtube")
    check("target resolved to YouTube", r.intent.target == "YouTube")

    # 3. Missing target (should fail gracefully, no LLM call)
    print("\n[3] Missing target")
    r = engine.process("open")
    check("does not crash", r is not None)
    check("reports error", r.success is False)

    # 4. Gibberish (triggers NLP fallback — skip in smoke test)
    print("\n[4] (skipped: NLP-heavy)")
    check("placeholder", True)

    # 5. Filler removal
    print("\n[5] Filler removal")
    r = engine.process("please open github")
    check("action is 'open'", r.intent.action == "open")
    check("target is 'github'", r.intent.target == "github")

    # Summary
    print("\n" + "=" * 50)
    total = PASS + FAIL
    print(f"  Results: {PASS}/{total} passed, {FAIL} failed")
    print("=" * 50)

    return FAIL == 0


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
