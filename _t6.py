"""Temp probe: does closing PEB std handles under pythonw release a pipe?"""
import os
import sys

log = open(r"C:\Sarthi\_t6_out.txt", "w")
log.write("started\n")
log.flush()
try:
    for fd in (0, 1, 2):
        try:
            os.close(fd)
            log.write(f"closed fd {fd}\n")
        except OSError as e:
            log.write(f"close fd {fd} failed: {e}\n")
        log.flush()
except Exception as e:  # pragma: no cover
    log.write(f"EXC {e!r}\n")
    log.flush()

import ctypes

try:
    kernel32 = ctypes.windll.kernel32
    for std in (-10, -11, -12):  # STD_INPUT_HANDLE, STD_OUTPUT_HANDLE, STD_ERROR_HANDLE
        h = kernel32.GetStdHandle(std)
        if h and int(h) not in (-1, 0):
            kernel32.CloseHandle(h)
            log.write(f"closed PEB std handle {std}\n")
            log.flush()
except Exception as e:  # pragma: no cover
    log.write(f"PEB close EXC {e!r}\n")
    log.flush()

import time

time.sleep(30)
log.write("still alive at 30s\n")
log.flush()
