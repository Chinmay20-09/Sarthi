"""
Telemetry collector for the Sarthi test runner.

Captures hardware snapshots before/after each test with graceful failure.
GPU VRAM usage and GPU utilization are tracked as separate metrics.
No metric collection failure should ever cause a test to fail.

Usage:
    from utils.telemetry import TelemetryCollector
    tc = TelemetryCollector()
    baseline = tc.snapshot()
    # ... run test ...
    post = tc.snapshot()
    result = tc.build_test_record(baseline, post)
"""

import threading
import time
from datetime import datetime


class TelemetryCollector:
    """Lightweight hardware telemetry collector for test runs.

    Each snapshot captures what is available; unavailable metrics are None.
    Periodic background sampling is optional and non-blocking.
    """

    def __init__(self):
        # Suite-level accumulators
        self._gpu_temp_history: list[float] = []
        self._gpu_vram_used_history: list[float] = []
        self._gpu_util_history: list[float] = []
        self._cpu_util_history: list[float] = []
        self._cpu_temp_history: list[float] = []
        self._ram_used_history: list[float] = []
        self._periodic_samples: list[dict] = []
        self._periodic_thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    # ------------------------------------------------------------------
    # Core snapshot
    # ------------------------------------------------------------------

    def snapshot(self) -> dict:
        """Capture a hardware snapshot. Never raises — unavailable metrics are None."""
        ts = datetime.now().isoformat(timespec="milliseconds")
        cpu = self._safe_read_cpu()
        cpu_temp = self._safe_read_cpu_temp()
        gpu = self._safe_read_gpu()
        ram = self._safe_read_ram()

        return {
            "timestamp": ts,
            "gpu_temperature_c": gpu.get("temperature_c"),
            "gpu_vram_used_gb": gpu.get("vram_used_gb"),
            "gpu_vram_total_gb": gpu.get("vram_total_gb"),
            "gpu_utilization_percent": gpu.get("utilization_percent"),
            "cpu_utilization_percent": cpu.get("percent"),
            "gpu_power_watts": gpu.get("power_watts"),
            "cpu_temperature_c": cpu_temp,
            "system_ram_used_gb": ram.get("used_gb"),
            "system_ram_total_gb": ram.get("total_gb"),
        }

    def build_test_record(
        self,
        baseline: dict,
        post: dict,
        *,
        peak_gpu_temp: float | None = None,
        peak_gpu_vram: float | None = None,
        peak_gpu_util: float | None = None,
        peak_cpu_util: float | None = None,
    ) -> dict:
        """Build a hardware record for a single test from baseline/post snapshots.

        Records the delta (post - baseline) for VRAM usage (how much the test
        added) and the absolute post-test values for instantaneous readings.
        Peak values from the interval can be provided by the caller.
        """
        # Use the higher of post-test reading or provided peak
        gpu_temp = self._max_none(peak_gpu_temp, post.get("gpu_temperature_c"))
        gpu_vram_used = self._max_none(peak_gpu_vram, post.get("gpu_vram_used_gb"))
        gpu_vram_total = post.get("gpu_vram_total_gb")
        gpu_util = self._max_none(peak_gpu_util, post.get("gpu_utilization_percent"))
        cpu_util = self._max_none(peak_cpu_util, post.get("cpu_utilization_percent"))
        cpu_temp = post.get("cpu_temperature_c")
        ram_used = post.get("system_ram_used_gb")
        ram_total = post.get("system_ram_total_gb")
        gpu_power = post.get("gpu_power_watts")

        # Accumulate for suite-level stats
        if gpu_temp is not None:
            self._gpu_temp_history.append(gpu_temp)
        if gpu_vram_used is not None:
            self._gpu_vram_used_history.append(gpu_vram_used)
        if gpu_util is not None:
            self._gpu_util_history.append(gpu_util)
        if cpu_util is not None:
            self._cpu_util_history.append(cpu_util)
        if cpu_temp is not None:
            self._cpu_temp_history.append(cpu_temp)
        if ram_used is not None:
            self._ram_used_history.append(ram_used)

        return {
            "gpu_temperature_c": gpu_temp,
            "gpu_vram_used_gb": gpu_vram_used,
            "gpu_vram_total_gb": gpu_vram_total,
            "gpu_utilization_percent": gpu_util,
            "cpu_utilization_percent": cpu_util,
            "gpu_power_watts": gpu_power,
            "cpu_temperature_c": cpu_temp,
            "ram_used_gb": ram_used,
            "ram_total_gb": ram_total,
        }

    # ------------------------------------------------------------------
    # Suite-level statistics
    # ------------------------------------------------------------------

    def suite_summary(self) -> dict:
        """Compute suite-level hardware statistics from accumulated history."""
        return {
            "gpu_temperature": {
                "current": self._last(self._gpu_temp_history),
                "max": self._max_of(self._gpu_temp_history),
                "avg": self._avg(self._gpu_temp_history),
            },
            "gpu_vram": {
                "current": self._last(self._gpu_vram_used_history),
                "peak": self._max_of(self._gpu_vram_used_history),
                "total": None,  # filled by caller if available
            },
            "cpu_utilization": {
                "avg": self._avg(self._cpu_util_history),
                "peak": self._max_of(self._cpu_util_history),
            },
            "gpu_utilization": {
                "avg": self._avg(self._gpu_util_history),
                "peak": self._max_of(self._gpu_util_history),
            },
            "cpu_temperature": {
                "current": self._last(self._cpu_temp_history),
                "max": self._max_of(self._cpu_temp_history),
                "avg": self._avg(self._cpu_temp_history),
            },
        }

    def get_vram_total(self) -> float | None:
        """Return the VRAM total from the most recent snapshot, if available."""
        if self._gpu_vram_used_history:
            # We store used values; total is tracked per-snapshot.
            # Return None here — the caller should track total separately.
            pass
        return None

    # ------------------------------------------------------------------
    # Periodic background sampler
    # ------------------------------------------------------------------

    def start_periodic_sampling(self, interval_seconds: float = 2.0):
        """Start a background thread that samples hardware at a fixed interval.

        Does not block test execution. Samples are stored in
        _periodic_samples and can be retrieved via get_periodic_samples().
        """
        self._stop_event.clear()

        def _loop():
            while not self._stop_event.is_set():
                sample = self.snapshot()
                sample["source"] = "periodic"
                self._periodic_samples.append(sample)
                self._stop_event.wait(interval_seconds)

        self._periodic_thread = threading.Thread(target=_loop, daemon=True)
        self._periodic_thread.start()

    def stop_periodic_sampling(self):
        """Stop the background periodic sampler."""
        self._stop_event.set()
        if self._periodic_thread and self._periodic_thread.is_alive():
            self._periodic_thread.join(timeout=5)

    def get_periodic_samples(self) -> list[dict]:
        """Return all periodic samples collected during the test run."""
        return list(self._periodic_samples)

    # ------------------------------------------------------------------
    # Safe readers (never raise)
    # ------------------------------------------------------------------

    def _safe_read_cpu(self) -> dict:
        try:
            from reading import read_cpu
            return read_cpu()
        except Exception:
            return {"percent": None}

    def _safe_read_ram(self) -> dict:
        try:
            from reading import read_ram
            ram = read_ram()
            return {"used_gb": ram.get("used_gb"), "total_gb": ram.get("total_gb")}
        except Exception:
            return {"used_gb": None, "total_gb": None}

    def _safe_read_cpu_temp(self) -> float | None:
        try:
            from reading import read_cpu_temperature
            data = read_cpu_temperature()
            if data and data.get("current"):
                return data["current"]
        except Exception:
            pass
        return None

    def _safe_read_gpu(self) -> dict:
        """Read GPU data, extracting temperature and VRAM separately from utilization."""
        try:
            from reading import read_gpu
            gpu = read_gpu()
            if gpu is None:
                return {}

            result: dict = {}

            # Utilization (percentage)
            result["utilization_percent"] = gpu.get("utilization_percent")

            # VRAM (separate from utilization!)
            mem_total_mb = gpu.get("mem_total_mb")
            mem_used_mb = gpu.get("mem_used_mb")
            if mem_total_mb and mem_total_mb > 0:
                result["vram_total_gb"] = round(mem_total_mb / 1024, 2)
                result["vram_used_gb"] = round(mem_used_mb / 1024, 2) if mem_used_mb else 0.0
            else:
                result["vram_total_gb"] = None
                result["vram_used_gb"] = None

            # GPU temperature — try nvidia-smi extra query
            result["temperature_c"] = self._try_nvidia_temp()

            # GPU power — try nvidia-smi extra query
            result["power_watts"] = self._try_nvidia_power()

            return result
        except Exception:
            return {}

    def _try_nvidia_temp(self) -> float | None:
        """Try to get GPU temperature from nvidia-smi."""
        try:
            import subprocess
            r = subprocess.run(
                [
                    "nvidia-smi",
                    "--query-gpu=temperature.gpu",
                    "--format=csv,noheader,nounits",
                ],
                capture_output=True,
                text=True,
                timeout=3,
            )
            if r.returncode == 0 and r.stdout.strip():
                return float(r.stdout.strip().split("\n")[0])
        except (FileNotFoundError, subprocess.TimeoutExpired, ValueError, Exception):
            pass
        return None

    def _try_nvidia_power(self) -> float | None:
        """Try to get GPU power draw from nvidia-smi."""
        try:
            import subprocess
            r = subprocess.run(
                [
                    "nvidia-smi",
                    "--query-gpu=power.draw",
                    "--format=csv,noheader,nounits",
                ],
                capture_output=True,
                text=True,
                timeout=3,
            )
            if r.returncode == 0 and r.stdout.strip():
                return float(r.stdout.strip().split("\n")[0])
        except (FileNotFoundError, subprocess.TimeoutExpired, ValueError, Exception):
            pass
        return None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _max_none(a: float | None, b: float | None) -> float | None:
        vals = [v for v in (a, b) if v is not None]
        return max(vals) if vals else None

    @staticmethod
    def _max_of(lst: list[float]) -> float | None:
        return max(lst) if lst else None

    @staticmethod
    def _avg(lst: list[float]) -> float | None:
        return round(sum(lst) / len(lst), 2) if lst else None

    @staticmethod
    def _last(lst: list[float]) -> float | None:
        return lst[-1] if lst else None


# ------------------------------------------------------------------
# Configurable hardware thresholds
# ------------------------------------------------------------------

class HardwareThresholds:
    """Configurable thresholds for hardware safety warnings.

    No hardcoded danger thresholds. If no threshold is configured,
    values are simply displayed without alarming.
    """

    def __init__(self):
        self.gpu_temp_warning_c: float | None = None
        self.gpu_temp_critical_c: float | None = None
        self.gpu_vram_warning_gb: float | None = None
        self.cpu_util_warning_percent: float | None = None
        self.gpu_util_warning_percent: float | None = None
        # Sustained detection: how many consecutive violations = sustained
        self.sustained_count: int = 3

    def check(self, history: list[dict]) -> dict:
        """Analyze test history for sustained abnormal readings.

        Returns a dict of warning flags. A single spike does NOT trigger
        a sustained warning.
        """
        warnings: dict = {}

        if not history:
            return warnings

        # GPU temperature sustained check
        if self.gpu_temp_warning_c is not None:
            consecutive = 0
            max_consecutive = 0
            for record in history:
                t = record.get("gpu_temperature_c")
                if t is not None and t >= self.gpu_temp_warning_c:
                    consecutive += 1
                    max_consecutive = max(max_consecutive, consecutive)
                else:
                    consecutive = 0
            if max_consecutive >= self.sustained_count:
                warnings["gpu_temp_sustained"] = {
                    "level": "critical" if self.gpu_temp_critical_c and max(
                        (r.get("gpu_temperature_c") or 0) for r in history
                    ) >= self.gpu_temp_critical_c else "warning",
                    "consecutive_count": max_consecutive,
                    "threshold_c": self.gpu_temp_warning_c,
                    "peak_c": max((r.get("gpu_temperature_c") or 0) for r in history),
                }

        # GPU VRAM sustained check
        if self.gpu_vram_warning_gb is not None:
            consecutive = 0
            max_consecutive = 0
            for record in history:
                v = record.get("gpu_vram_used_gb")
                if v is not None and v >= self.gpu_vram_warning_gb:
                    consecutive += 1
                    max_consecutive = max(max_consecutive, consecutive)
                else:
                    consecutive = 0
            if max_consecutive >= self.sustained_count:
                warnings["gpu_vram_sustained"] = {
                    "level": "warning",
                    "consecutive_count": max_consecutive,
                    "threshold_gb": self.gpu_vram_warning_gb,
                    "peak_gb": max((r.get("gpu_vram_used_gb") or 0) for r in history),
                }

        # CPU utilization sustained check
        if self.cpu_util_warning_percent is not None:
            consecutive = 0
            max_consecutive = 0
            for record in history:
                c = record.get("cpu_utilization_percent")
                if c is not None and c >= self.cpu_util_warning_percent:
                    consecutive += 1
                    max_consecutive = max(max_consecutive, consecutive)
                else:
                    consecutive = 0
            if max_consecutive >= self.sustained_count:
                warnings["cpu_util_sustained"] = {
                    "level": "warning",
                    "consecutive_count": max_consecutive,
                    "threshold_percent": self.cpu_util_warning_percent,
                    "peak_percent": max(
                        (r.get("cpu_utilization_percent") or 0) for r in history
                    ),
                }

        return warnings


# ------------------------------------------------------------------
# Failure classification
# ------------------------------------------------------------------

def classify_failure(result: dict) -> str:
    """Classify the failure type of a test result.

    Returns one of:
        - pass
        - executor_unsupported_action
        - app_not_found
        - no_target
        - entity_resolution
        - interpreter
        - conversational_nlp
        - execution_error
        - timeout
    """
    if result.get("passed") and result.get("success"):
        return "pass"

    actual = (result.get("actual") or "").lower()
    action = (result.get("action") or "").lower()
    target = (result.get("target") or "")
    success = result.get("success", False)

    # No target specified
    if not target and action in ("open", "search", "play", "close"):
        return "no_target"

    # Executor reports unknown action (action recognized but not implemented)
    if "unknown action:" in actual:
        return "executor_unsupported_action"

    # Entity resolution issue (target contains filler/address words)
    # Check BEFORE app_not_found because entity resolution failures
    # also produce "Application not found" messages with bad targets.
    filler_in_target = any(
        word in target.lower()
        for word in ("hey", "sarthi", "i want", "i need", "i'd like", "i would like", "mind", "start")
    )
    if filler_in_target and action != "unknown":
        return "entity_resolution"

    # Application not found
    if "application not found" in actual:
        return "app_not_found"

    # Execution error / pipeline error
    if not success and action != "unknown":
        return "execution_error"

    # NLP / conversational (action is unknown, handled by fallback NLP)
    if action == "unknown" and success:
        return "pass"  # Conversational response was successful

    if action == "unknown" and not success:
        return "conversational_nlp"

    return "execution_error"
