---
name: laptop-power-status
description: Check whether the current laptop is connected to AC power or running on battery, using read-only operating-system power information.
---

# Laptop power status

Use this skill when asked whether this computer or laptop is plugged into electrical power, charging, or running on battery.

## Identify the power source

Inspect the current machine with a read-only native status source. Choose the method for the operating system actually being queried:

- **Windows:** Read `[System.Windows.Forms.SystemInformation]::PowerStatus` from PowerShell. Its `PowerLineStatus` reports `Online`, `Offline`, or `Unknown`; `BatteryLifePercent` gives the reported charge level. If needed, inspect `Win32_Battery` with `Get-CimInstance` for additional battery details.
- **macOS:** Read `pmset -g batt`; report whether the battery is charging, discharging, or fully charged while connected to AC.
- **Linux:** Read the `online` value for an AC power supply under `/sys/class/power_supply/` (commonly `AC`, `ACAD`, or `ADP`). If the supply interface is absent or unclear, query `upower` when available.

Do not change power settings, initiate sleep, or run commands that require elevated privileges. Prefer a direct OS status value over inferring power source from battery percentage or charging behavior.

## Report the result

State plainly whether AC power is connected or the system is running on battery. Include charge percentage only when the OS reports it. Distinguish “plugged in and charging” from “plugged in and fully charged” when that information is available.

If the status is unknown, the device has no battery, or the inspected environment may be a virtual/remote machine rather than the user's laptop, say that the current evidence cannot confirm the laptop's physical power connection. Do not guess; ask for an appropriate local check only if needed.
