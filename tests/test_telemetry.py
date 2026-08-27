"""Tests for utils/telemetry.py — TelemetryCollector, HardwareThresholds, classify_failure."""

from utils.telemetry import HardwareThresholds, TelemetryCollector, classify_failure

# ---------------------------------------------------------------------------
# TelemetryCollector
# ---------------------------------------------------------------------------


class TestTelemetryCollector:
    def test_snapshot_never_raises(self):
        """snapshot() must always succeed, even if hardware reads fail."""
        tc = TelemetryCollector()
        snap = tc.snapshot()
        assert isinstance(snap, dict)
        assert "timestamp" in snap
        assert "gpu_temperature_c" in snap
        assert "gpu_vram_used_gb" in snap
        assert "gpu_vram_total_gb" in snap
        assert "gpu_utilization_percent" in snap
        assert "cpu_utilization_percent" in snap
        assert "system_ram_used_gb" in snap
        assert "system_ram_total_gb" in snap

    def test_build_test_record_basic(self):
        """build_test_record should return a dict with all hw fields."""
        tc = TelemetryCollector()
        baseline = {
            "timestamp": "2026-01-01T00:00:00",
            "gpu_temperature_c": 45.0,
            "gpu_vram_used_gb": 1.0,
            "gpu_vram_total_gb": 8.0,
            "gpu_utilization_percent": 30,
            "cpu_utilization_percent": 20,
            "gpu_power_watts": None,
            "cpu_temperature_c": None,
            "system_ram_used_gb": 4.0,
            "system_ram_total_gb": 16.0,
        }
        post = {
            "timestamp": "2026-01-01T00:00:01",
            "gpu_temperature_c": 47.0,
            "gpu_vram_used_gb": 1.2,
            "gpu_vram_total_gb": 8.0,
            "gpu_utilization_percent": 50,
            "cpu_utilization_percent": 35,
            "gpu_power_watts": None,
            "cpu_temperature_c": None,
            "system_ram_used_gb": 4.5,
            "system_ram_total_gb": 16.0,
        }
        record = tc.build_test_record(baseline, post)
        assert record["gpu_temperature_c"] == 47.0
        assert record["gpu_vram_used_gb"] == 1.2
        assert record["gpu_vram_total_gb"] == 8.0
        assert record["gpu_utilization_percent"] == 50
        assert record["cpu_utilization_percent"] == 35

    def test_build_test_record_uses_peak_when_provided(self):
        """Peak values should override post values if higher."""
        tc = TelemetryCollector()
        baseline = {"gpu_temperature_c": 45.0, "gpu_vram_used_gb": 1.0}
        post = {"gpu_temperature_c": 47.0, "gpu_vram_used_gb": 1.2}
        record = tc.build_test_record(baseline, post, peak_gpu_temp=55.0, peak_gpu_vram=2.0)
        assert record["gpu_temperature_c"] == 55.0
        assert record["gpu_vram_used_gb"] == 2.0

    def test_build_test_record_handles_none_values(self):
        """None values should remain None."""
        tc = TelemetryCollector()
        baseline = {"gpu_temperature_c": None, "gpu_vram_used_gb": None}
        post = {"gpu_temperature_c": None, "gpu_vram_used_gb": None}
        record = tc.build_test_record(baseline, post)
        assert record["gpu_temperature_c"] is None
        assert record["gpu_vram_used_gb"] is None

    def test_suite_summary_accumulates(self):
        """Suite summary should compute stats from accumulated history."""
        tc = TelemetryCollector()
        baseline = {"gpu_temperature_c": 40.0, "gpu_vram_used_gb": 1.0}
        post1 = {"gpu_temperature_c": 45.0, "gpu_vram_used_gb": 1.5}
        post2 = {"gpu_temperature_c": 50.0, "gpu_vram_used_gb": 2.0}
        tc.build_test_record(baseline, post1)
        tc.build_test_record(baseline, post2)
        summary = tc.suite_summary()
        assert summary["gpu_temperature"]["max"] == 50.0
        assert summary["gpu_temperature"]["avg"] == 47.5
        assert summary["gpu_vram"]["peak"] == 2.0

    def test_periodic_sampling_start_stop(self):
        """Periodic sampling should start and stop without error."""
        tc = TelemetryCollector()
        tc.start_periodic_sampling(interval_seconds=0.1)
        import time

        time.sleep(0.3)
        tc.stop_periodic_sampling()
        samples = tc.get_periodic_samples()
        assert len(samples) > 0
        assert samples[0]["source"] == "periodic"


# ---------------------------------------------------------------------------
# HardwareThresholds
# ---------------------------------------------------------------------------


class TestHardwareThresholds:
    def test_no_thresholds_no_warnings(self):
        """Without configured thresholds, no warnings should appear."""
        ht = HardwareThresholds()
        history = [
            {"gpu_temperature_c": 90.0, "gpu_vram_used_gb": 7.5},
            {"gpu_temperature_c": 92.0, "gpu_vram_used_gb": 7.8},
            {"gpu_temperature_c": 95.0, "gpu_vram_used_gb": 7.9},
        ]
        warnings = ht.check(history)
        assert warnings == {}

    def test_sustained_gpu_temp_warning(self):
        """Consecutive violations above threshold should trigger warning."""
        ht = HardwareThresholds()
        ht.gpu_temp_warning_c = 80.0
        ht.sustained_count = 3
        history = [
            {"gpu_temperature_c": 85.0},
            {"gpu_temperature_c": 87.0},
            {"gpu_temperature_c": 90.0},
        ]
        warnings = ht.check(history)
        assert "gpu_temp_sustained" in warnings
        assert warnings["gpu_temp_sustained"]["level"] == "warning"
        assert warnings["gpu_temp_sustained"]["consecutive_count"] == 3

    def test_single_spike_not_sustained(self):
        """A single temperature spike should NOT trigger sustained warning."""
        ht = HardwareThresholds()
        ht.gpu_temp_warning_c = 80.0
        ht.sustained_count = 3
        history = [
            {"gpu_temperature_c": 60.0},
            {"gpu_temperature_c": 90.0},
            {"gpu_temperature_c": 60.0},
        ]
        warnings = ht.check(history)
        assert "gpu_temp_sustained" not in warnings

    def test_critical_temperature(self):
        """Peak above critical threshold should set level to critical."""
        ht = HardwareThresholds()
        ht.gpu_temp_warning_c = 80.0
        ht.gpu_temp_critical_c = 95.0
        ht.sustained_count = 2
        history = [
            {"gpu_temperature_c": 96.0},
            {"gpu_temperature_c": 97.0},
        ]
        warnings = ht.check(history)
        assert warnings["gpu_temp_sustained"]["level"] == "critical"

    def test_sustained_vram_warning(self):
        """Sustained VRAM usage above threshold should trigger warning."""
        ht = HardwareThresholds()
        ht.gpu_vram_warning_gb = 6.0
        ht.sustained_count = 2
        history = [
            {"gpu_vram_used_gb": 6.5},
            {"gpu_vram_used_gb": 7.0},
        ]
        warnings = ht.check(history)
        assert "gpu_vram_sustained" in warnings

    def test_empty_history(self):
        """Empty history should produce no warnings."""
        ht = HardwareThresholds()
        ht.gpu_temp_warning_c = 80.0
        warnings = ht.check([])
        assert warnings == {}


# ---------------------------------------------------------------------------
# classify_failure
# ---------------------------------------------------------------------------


class TestClassifyFailure:
    def test_pass(self):
        result = {
            "passed": True,
            "success": True,
            "actual": "Done.",
            "action": "open",
            "target": "chrome",
        }
        assert classify_failure(result) == "pass"

    def test_executor_unsupported_action(self):
        result = {
            "passed": False,
            "success": False,
            "actual": "Unknown action: play",
            "action": "play",
            "target": "lo-fi music",
        }
        assert classify_failure(result) == "executor_unsupported_action"

    def test_app_not_found(self):
        result = {
            "passed": False,
            "success": False,
            "actual": "Application not found: chrome",
            "action": "open",
            "target": "chrome",
        }
        assert classify_failure(result) == "app_not_found"

    def test_no_target(self):
        result = {
            "passed": False,
            "success": False,
            "actual": "No target specified",
            "action": "open",
            "target": "",
        }
        assert classify_failure(result) == "no_target"

    def test_entity_resolution_filler_in_target(self):
        result = {
            "passed": False,
            "success": False,
            "actual": "Application not found: hey sarthi, chrome",
            "action": "open",
            "target": "hey sarthi, chrome",
        }
        assert classify_failure(result) == "entity_resolution"

    def test_entity_resolution_i_want(self):
        result = {
            "passed": False,
            "success": False,
            "actual": "Application not found: i want spotify",
            "action": "open",
            "target": "i want spotify",
        }
        assert classify_failure(result) == "entity_resolution"

    def test_conversational_nlp(self):
        result = {
            "passed": False,
            "success": False,
            "actual": "Something went wrong",
            "action": "unknown",
            "target": "something",
        }
        assert classify_failure(result) == "conversational_nlp"

    def test_execution_error(self):
        result = {
            "passed": False,
            "success": False,
            "actual": "Some error",
            "action": "open",
            "target": "chrome",
        }
        assert classify_failure(result) == "execution_error"
