"""Temp probe: does a Python pipe caller block while pythonw holds the pipe?"""
import subprocess
import time

t = time.monotonic()
try:
    p = subprocess.Popen(
        ["cmd", "/c", "pythonw", r"C:\Sarthi\_t6.py"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    out, _ = p.communicate(timeout=15)
    print(f"RETURNED after {time.monotonic() - t:.1f}s", flush=True)
    print(out.decode(errors="replace"), flush=True)
except subprocess.TimeoutExpired:
    print(f"HUNG >15s (pipe held by pythonw)", flush=True)
    p.kill()
