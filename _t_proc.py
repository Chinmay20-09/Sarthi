"""Temp probe: does `cmd /c pythonw ...` wait for pythonw to exit?"""
import subprocess
import time

t = time.monotonic()
p = subprocess.Popen(["cmd", "/c", "pythonw", "-c", "import time; time.sleep(3)"])
print("spawned cmd /c pythonw", flush=True)
p.wait()
print(f"cmd returned after {time.monotonic() - t:.1f}s (3 = waits, 0 = detaches)", flush=True)
