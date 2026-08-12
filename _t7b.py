"""Temp probe: with `start` (cmd doesn't wait), does pythonw hold the pipe?"""
import subprocess
import time

t = time.monotonic()
try:
    p = subprocess.Popen(
        ["cmd", "/c", "start", "", "pythonw", r"C:\Sarthi\_t6.py"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    out, _ = p.communicate(timeout=15)
    print(f"RETURNED after {time.monotonic() - t:.1f}s (pipe NOT held)", flush=True)
    print(out.decode(errors="replace"), flush=True)
except subprocess.TimeoutExpired:
    print(f"HUNG >15s (pythonw inherited and holds the pipe)", flush=True)
    p.kill()
