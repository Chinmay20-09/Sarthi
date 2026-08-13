"""Windowless static UI server for Sarthi.

Used by start.bat's ``background`` mode (the wake-word flow), where the
UI folder is served on port 5500 exactly like ``python -m http.server
5500 --directory UI`` in dev mode — except under pythonw, where
sys.stdout/sys.stderr are None and would crash the request handler.

Under pythonw there is no console window, so this process never shows a
terminal. Log output goes to devnull (the UI server itself is legacy —
nothing in the repo references port 5500; the dashboard is served by the
API at :8000).
"""

import os
import sys

if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")

from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

os.chdir(Path(__file__).resolve().parent.parent / "UI")
print(f"Serving Sarthi UI from {os.getcwd()} on http://127.0.0.1:5500")
HTTPServer(("", 5500), SimpleHTTPRequestHandler).serve_forever()
