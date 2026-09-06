"""
ai_chain/calibrate.py

Calibration helper for the AI chain.

Because the bot clicks by *fractions* of the browser window, one-time
calibration makes it far more reliable on your monitor and layout.
For each site you record a few points by positioning the browser the
way it looks during a run and clicking exactly on the target:

    python -m skills.automation_engine.ai_chain.calibrate                     # status
    python -m skills.automation_engine.ai_chain.calibrate --site gemini --point composer --record
    python -m skills.automation_engine.ai_chain.calibrate --site chatgpt --point read_point --record
    python -m skills.automation_engine.ai_chain.calibrate --site gemini --point image_download_point --record

Points are stored in calibration.json (git-ignored) as window fractions
so they stay valid across screen sizes. While recording, move the mouse
over the exact spot and press Enter — the current cursor position is
converted to a fraction of the browser window.

Known points:
    composer             — the message input box (where prompts are pasted)
    read_point           — a click spot inside the chat (not the composer),
                           used before Select-All + Copy
    copy_point           — the "Copy" button of the newest assistant
                           message (browser-awareness registry). Clicking
                           it copies just the reply, not the whole page.
    image_download_point — the download button of the newest generated
                           image in Gemini (skip to use the auto-estimate)
"""

from __future__ import annotations

import sys
import time

from .calibration import (
    DEFAULT_SITES,
    EXAMPLE_CALIBRATION,
    get_site,
    save_calibration,
)
from .control import ScreenController

POINTS = ("composer", "read_point", "copy_point", "image_download_point")


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    site = _arg(args, "--site")
    point = _arg(args, "--point")
    record = "--record" in args

    if record:
        if site not in DEFAULT_SITES:
            print(f"Unknown site '{site}'. Known: {', '.join(DEFAULT_SITES)}")
            return 2
        if point not in POINTS:
            print(f"Unknown point '{point}'. Known: {', '.join(POINTS)}")
            return 2
        return _record(site, point)

    _print_status()
    return 0


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------


def _print_status() -> None:
    print("AI-chain calibration")
    print(f"  example file : {EXAMPLE_CALIBRATION}")
    print("  runtime file : calibration.json (created on first record)\n")
    for key, spec in DEFAULT_SITES.items():
        current = get_site(key)
        print(f"  {spec.label} ({key}):")
        print(f"    url                 = {current.url}")
        print(f"    composer            = {_fmt(current.composer)}")
        print(f"    read_point          = {_fmt(current.read_point)}")
        print(f"    copy_point          = {_fmt(_copy_point_for(key))}")
        print(f"    copy_scan_region    = {_fmt_region(_scan_region_for(key))}")
        print(f"    image_download_point= {_fmt(current.image_download_point)}")
    print("\nTo record a point run, e.g.:")
    print("  python -m skills.automation_engine.ai_chain.calibrate \\")
    print("      --site gemini --point image_download_point --record")


def _copy_point_for(site_key: str):
    """The Copy button point from the browser-awareness registry."""
    from .registry import get_copy_point

    return get_copy_point(site_key)


def _scan_region_for(site_key: str):
    """The Copy button scan region from the browser-awareness registry."""
    from .registry import get_scan_region

    return get_scan_region(site_key)


def _fmt_region(region) -> str:
    if region is None:
        return "auto (around copy_point)"
    x0, y0, x1, y1 = region
    return f"({x0:.2f}, {y0:.2f})-({x1:.2f}, {y1:.2f})"


def _record(site: str, point: str) -> int:
    ctrl = ScreenController(dry_run=False)
    spec = get_site(site)
    rect = ctrl.window_rect(spec.title_keyword)
    left, top, right, bottom = rect
    print(f"Window '{spec.title_keyword}' found at ({left}, {top})-({right}, {bottom}).")
    print(f"\nMove the mouse to the exact '{point}' spot inside the {spec.label} window,")
    print("then press Enter. (5s to get ready)")
    for i in range(5, 0, -1):
        print(f"  {i}...", end="\r")
        time.sleep(1)
    print(" " * 20)
    print("Now: move the mouse to the spot and press Enter ...")
    ctrl.wait_for_key("enter")
    x, y = ctrl.cursor_position()
    fx = (x - left) / max(1, right - left)
    fy = (y - top) / max(1, bottom - top)
    fx, fy = round(max(0.0, min(1.0, fx)), 4), round(max(0.0, min(1.0, fy)), 4)
    save_calibration({site: {point: [fx, fy]}})
    print(f"Saved {site}.{point} = ({fx}, {fy})  [fraction of window]")
    print("Done! Run the chain — it will now click exactly there.")
    return 0


def _fmt(point) -> str:
    return "auto-estimate" if point is None else f"({point[0]:.2f}, {point[1]:.2f})"


def _arg(args: list[str], name: str) -> str:
    if name in args:
        idx = args.index(name)
        if idx + 1 < len(args):
            return args[idx + 1]
    return ""


if __name__ == "__main__":
    raise SystemExit(main())
