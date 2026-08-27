"""
reading.py — System hardware readings.

Pure data-gathering: CPU, RAM, disk, GPU, and temperature.
No FastAPI, no HTTP — just psutil and subprocess calls.

Usage:
    from reading import get_system_metrics
    metrics = get_system_metrics()   # dict ready for the API response
"""

import glob
import json
import os
import subprocess

import psutil


# ---------------------------------------------------------------------------
# CPU
# ---------------------------------------------------------------------------

def read_cpu() -> dict:
    """Return CPU percent, core count, and frequency."""
    percent = psutil.cpu_percent(interval=0.3)
    count = psutil.cpu_count(logical=True)
    freq = psutil.cpu_freq()
    return {
        "percent": percent,
        "count": count,
        "freq_mhz": round(freq.current, 0) if freq else None,
    }


# ---------------------------------------------------------------------------
# CPU Temperature
# ---------------------------------------------------------------------------

def read_cpu_temperature() -> dict | None:
    """Read CPU temperature from hardware sensors.

    Prefers well-known sensor names (coretemp for Intel, k10temp/zenpower
    for AMD) then falls back to the hottest reading across all sensors.
    Returns None when no sensor data is available (e.g. Windows).
    """
    try:
        temps = psutil.sensors_temperatures()
    except (AttributeError, Exception):
        return None

    if not temps:
        return None

    # Priority-ordered sensor names
    for name in ("coretemp", "k10temp", "zenpower", "acpitz", "it87"):
        if name in temps and temps[name]:
            readings = [s.current for s in temps[name] if s.current and s.current > 0]
            if readings:
                return {
                    "current": round(max(readings), 1),
                    "high": round(max((s.high or 0) for s in temps[name] if s.high), 1) or None,
                    "critical": round(
                        max((s.critical or 0) for s in temps[name] if s.critical), 1
                    )
                    or None,
                    "sensor": name,
                }
            break

    # Fallback: hottest reading from any sensor
    all_readings = []
    for entries in temps.values():
        for s in entries:
            if s.current and s.current > 0:
                all_readings.append(s)
    if all_readings:
        hottest = max(all_readings, key=lambda s: s.current)
        return {
            "current": round(hottest.current, 1),
            "high": round(hottest.high, 1) if hottest.high else None,
            "critical": round(hottest.critical, 1) if hottest.critical else None,
            "sensor": "mixed",
        }
    return None


# ---------------------------------------------------------------------------
# RAM
# ---------------------------------------------------------------------------

def read_ram() -> dict:
    """Return RAM percent, total, used, and available in GB."""
    mem = psutil.virtual_memory()
    return {
        "percent": mem.percent,
        "total_gb": round(mem.total / (1024**3), 1),
        "used_gb": round(mem.used / (1024**3), 1),
        "available_gb": round(mem.available / (1024**3), 1),
    }


# ---------------------------------------------------------------------------
# Disk / SSD
# ---------------------------------------------------------------------------

def read_disks() -> list[dict]:
    """Return usage for every mounted physical partition."""
    parts = []
    for part in psutil.disk_partitions(all=False):
        try:
            usage = psutil.disk_usage(part.mountpoint)
            parts.append({
                "device": part.device,
                "mountpoint": part.mountpoint,
                "total_gb": round(usage.total / (1024**3), 1),
                "used_gb": round(usage.used / (1024**3), 1),
                "free_gb": round(usage.free / (1024**3), 1),
                "percent": usage.percent,
            })
        except PermissionError:
            continue
    return parts


# ---------------------------------------------------------------------------
# GPU — detection cascade
# ---------------------------------------------------------------------------

def _try_nvidia() -> dict | None:
    """Query NVIDIA GPUs via nvidia-smi."""
    try:
        r = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.total,memory.used,memory.free,utilization.gpu",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=3,
        )
        if r.returncode == 0 and r.stdout.strip():
            line = r.stdout.strip().split("\n")[0]
            p = [x.strip() for x in line.split(",")]
            if len(p) >= 5:
                mem_total = int(p[1])
                mem_used = int(p[2])
                return {
                    "name": p[0],
                    "mem_total_mb": mem_total,
                    "mem_used_mb": mem_used,
                    "mem_free_mb": int(p[3]),
                    "utilization_percent": int(p[4]),
                    "mem_percent": round(mem_used / max(mem_total, 1) * 100, 1),
                    "vendor": "nvidia",
                }
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return None


def _try_rocm() -> dict | None:
    """Query AMD GPUs via rocm-smi (ROCm stack, Linux)."""
    try:
        r = subprocess.run(
            [
                "rocm-smi",
                "--showuse",
                "--showmemuse",
                "--showid",
                "--showmeminfo",
                "vram",
                "--json",
            ],
            capture_output=True,
            text=True,
            timeout=3,
        )
        if r.returncode == 0 and r.stdout.strip():
            data = json.loads(r.stdout)
            gpu_key = None
            for k in data:
                if k.startswith("card"):
                    gpu_key = k
                    break
            if gpu_key:
                card = data[gpu_key]
                name = card.get("GPU", {}).get("Card series", "AMD GPU")
                if not name or name == "":
                    name = card.get("GPU", {}).get("Card model", "AMD GPU")
                use_pct = card.get("GPU use (%)", "0")
                try:
                    util_pct = int(float(str(use_pct).replace("%", "").strip()))
                except ValueError:
                    util_pct = 0
                vram = card.get("vram", {})
                mem_total = int(vram.get("total", {}).get("amount", 0)) // (1024 * 1024)
                mem_used = int(vram.get("used", {}).get("amount", 0)) // (1024 * 1024)
                mem_free = mem_total - mem_used if mem_total > 0 else 0
                return {
                    "name": str(name),
                    "mem_total_mb": mem_total,
                    "mem_used_mb": mem_used,
                    "mem_free_mb": mem_free,
                    "utilization_percent": util_pct,
                    "mem_percent": round(mem_used / max(mem_total, 1) * 100, 1),
                    "vendor": "amd",
                }
    except (FileNotFoundError, subprocess.TimeoutExpired, Exception):
        pass
    return None


def _try_sysfs_amd() -> dict | None:
    """Query AMD GPU via Linux sysfs (works without ROCm)."""
    try:
        for card_path in sorted(glob.glob("/sys/class/drm/card[0-9]*")):
            device = card_path + "/device"
            driver_path = card_path + "/device/driver"
            try:
                driver_target = os.readlink(driver_path)
            except OSError:
                continue
            if "amdgpu" not in driver_target:
                continue

            busy_path = device + "/gpu_busy_percent"
            util_pct = 0
            if os.path.exists(busy_path):
                with open(busy_path) as f:
                    util_pct = int(f.read().strip().replace("%", ""))

            vram_total_path = device + "/mem_info_vram_total"
            vram_used_path = device + "/mem_info_vram_used"
            mem_total = 0
            mem_used = 0
            if os.path.exists(vram_total_path):
                with open(vram_total_path) as f:
                    mem_total = int(f.read().strip()) // (1024 * 1024)
            if os.path.exists(vram_used_path):
                with open(vram_used_path) as f:
                    mem_used = int(f.read().strip()) // (1024 * 1024)

            name = "AMD GPU"
            uevent_path = device + "/uevent"
            if os.path.exists(uevent_path):
                with open(uevent_path) as f:
                    for line in f:
                        if line.startswith("PCI_ID="):
                            vendor_id = line.strip().split("=")[1]
                            if vendor_id.startswith("1002"):
                                name = "AMD Radeon GPU"
                            break

            try:
                lspci_r = subprocess.run(
                    ["lspci"], capture_output=True, text=True, timeout=2
                )
                if lspci_r.returncode == 0:
                    for l in lspci_r.stdout.splitlines():
                        if "VGA" in l and ("AMD" in l or "Radeon" in l):
                            if ":" in l:
                                name = l.split(":", 1)[1].strip()
                            break
            except (FileNotFoundError, subprocess.TimeoutExpired):
                pass

            return {
                "name": name,
                "mem_total_mb": mem_total,
                "mem_used_mb": mem_used,
                "mem_free_mb": mem_total - mem_used,
                "utilization_percent": util_pct,
                "mem_percent": round(mem_used / max(mem_total, 1) * 100, 1),
                "vendor": "amd",
            }
    except Exception:
        pass
    return None


def _try_windows_wmi() -> dict | None:
    """Query any GPU via PowerShell/WMI on Windows."""
    if os.name != "nt":
        return None
    try:
        ps_cmd = (
            "Get-CimInstance Win32_VideoController | "
            "Select-Object Name, AdapterRAM, Utilization | "
            "ConvertTo-Json -Compress"
        )
        r = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_cmd],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if r.returncode == 0 and r.stdout.strip():
            data = json.loads(r.stdout)
            cards = data if isinstance(data, list) else [data]
            for card in cards:
                adapter_ram = card.get("AdapterRAM", 0)
                mem_total_mb = (adapter_ram or 0) // (1024 * 1024)
                util_pct = card.get("Utilization", None)
                if isinstance(util_pct, dict):
                    util_pct = util_pct.get("GPU", 0)
                else:
                    util_pct = 0
                return {
                    "name": card.get("Name", "GPU"),
                    "mem_total_mb": mem_total_mb,
                    "mem_used_mb": 0,
                    "mem_free_mb": mem_total_mb,
                    "utilization_percent": int(util_pct) if util_pct else 0,
                    "mem_percent": 0,
                    "vendor": "unknown",
                }
    except (FileNotFoundError, subprocess.TimeoutExpired, Exception):
        pass
    return None


def read_gpu() -> dict | None:
    """Detect GPU via NVIDIA → AMD ROCm → AMD sysfs → Windows WMI."""
    gpu = _try_nvidia()
    if gpu is not None:
        return gpu
    gpu = _try_rocm()
    if gpu is not None:
        return gpu
    gpu = _try_sysfs_amd()
    if gpu is not None:
        return gpu
    return _try_windows_wmi()


# ---------------------------------------------------------------------------
# Aggregate
# ---------------------------------------------------------------------------

def get_system_metrics() -> dict:
    """Collect all hardware readings into a single dict.

    Returns a dict with keys: success, cpu, ram, disks, gpu.
    Ready to return directly from a FastAPI endpoint.
    """
    cpu = read_cpu()
    cpu["temperature"] = read_cpu_temperature()

    return {
        "success": True,
        "cpu": cpu,
        "ram": read_ram(),
        "disks": read_disks(),
        "gpu": read_gpu(),
    }
