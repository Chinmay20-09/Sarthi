"""Session-wide pytest hooks — voice feedback for the test suite.

TO-DO item 1: announce "test_<file>.py passed" aloud at the end of each
test file, so a full-suite run can be followed without watching the
screen (same spirit as the ABSOLUTE.md automation contract: voice tells
you the state without reading it).

Implementation notes:

    - Uses the existing utils.voice.announce() helper (Windows SAPI via
      pywin32, PowerShell System.Speech fallback, log line elsewhere).
      announce() is best-effort and never raises.
    - One announcement per FILE, not per test — per-test speech would
      take longer than the tests themselves. pytest runs the tests of a
      file consecutively, so we announce when the first report of the
      next file arrives (and for the last file at session end).
      A file that had any failure (test, fixture or teardown) is
      announced with its failure count instead.
    - Silent when TTS is unavailable (non-Windows/CI): announce()
      degrades to a log line; the SARTHI_TEST_VOICE=0 env var silences
      it entirely.

Announcements are synchronous (blocking) by design — the voice finishes
before the next test file starts.
"""

from __future__ import annotations

import os

import pytest

# Backend/ is on sys.path via pyproject pythonpath, so the flat import
# the whole codebase uses works here too.
try:
    from utils.voice import announce
except ImportError:  # pragma: no cover - only when run outside pyproject env

    def announce(message: str) -> None:
        return None


def _voice_enabled() -> bool:
    """TTS on by default; opt out with SARTHI_TEST_VOICE=0 (or on CI)."""
    if os.environ.get("CI"):
        return False
    return os.environ.get("SARTHI_TEST_VOICE", "1") != "0"


# Per-file outcome tracking (module-level: pytest hooks are callbacks).
_file: str | None = None
_failed = 0


def _flush() -> None:
    """Speak the tracked file's result and reset the counters."""
    global _file, _failed
    if _file is None:
        return
    name = os.path.basename(_file)
    if _failed:
        plural = "s" if _failed != 1 else ""
        message = f"{name} failed. {_failed} test{plural} failed."
    else:
        message = f"{name} passed"
    try:
        announce(message)
    except Exception:  # pragma: no cover - announce is best-effort by design
        pass
    _file, _failed = None, 0


def pytest_runtest_logreport(report: pytest.TestReport) -> None:
    """Accumulate outcomes; announce when a new test file starts."""
    global _file, _failed
    if not _voice_enabled():
        return
    fspath = str(getattr(report, "fspath", "") or "")
    if not fspath:
        return
    if _file is not None and fspath != _file:
        _flush()
    _file = fspath
    # Only failures are counted — a passed file says "passed".
    # Any failing phase (setup/call/teardown) means the file did not
    # fully pass, so fixture errors fail the file too.
    if report.failed:
        _failed += 1


@pytest.hookimpl(trylast=True)
def pytest_sessionfinish(session: pytest.Session, exitstatus: int):
    """Announce the last file's result (its successor never arrives)."""
    del exitstatus
    if _voice_enabled():
        _flush()
