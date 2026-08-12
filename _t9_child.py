"""Temp probe: writes a unique marker per spawn, then lingers."""
import os
import time

with open(r"C:\Sarthi\_t9_marker_%d.txt" % os.getpid(), "w") as f:
    f.write("spawned")
time.sleep(15)
