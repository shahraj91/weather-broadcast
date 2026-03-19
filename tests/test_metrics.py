"""
Tests for utils/metrics.py — SQLite-backed persistent metrics collector.
Each test gets an isolated DB via tmp_path so tests never share state.
"""

import pytest
import utils.metrics as metrics


@pytest.fixture(autouse=True)
def isolated_metrics_db(tmp_path, monkeypatch):
    """
    Point the metrics module at a fresh per-test SQLite DB.
    Also clears in-memory latency windows so tests start clean.

    Note: we do NOT close _conn in teardown. _init() at the start of each
    test already closes the previous connection. Closing it in teardown would
    leave the module with a dead connection for subsequent test files.
    """
    db_path = str(tmp_path / "test_metrics.db")
    monkeypatch.setenv("DB_PATH", db_path)
    metrics._init(db_path)

    for window in metrics._latency_windows.values():
        window.clear()

    yield


# ── Increment ──────────────────────────────────────────────────────────────

class TestIncrement:

    def test_increment_increases_counter_by_one(self):
        """TM-01: increment() adds 1 to the named counter."""
        metrics.increment("messages_sent_total")
        assert metrics.get_summary()["messages_sent_total"] == 1

    def test_increment_twice(self):
        """TM-02: Calling increment() twice gives count of 2."""
        metrics.increment("messages_sent_total")
        metrics.increment("messages_sent_total")
        assert metrics.get_summary()["messages_sent_total"] == 2

    def test_increment_all_standard_counters(self):
        """TM-03: All standard counter names are incrementable."""
        for name in [
            "messages_sent_total",
            "messages_failed_total",
            "hallucination_fallbacks_total",
            "safety_blocks_total",
            "webhook_requests_total",
            "webhook_rejected_total",
        ]:
            metrics.increment(name)
            assert metrics.get_summary()[name] == 1

    def test_increment_unknown_key_creates_counter(self):
        """TM-04: Unknown metric name is created dynamically."""
        metrics.increment("custom_counter")
        assert metrics.get_summary()["custom_counter"] == 1


# ── Record latency ─────────────────────────────────────────────────────────

class TestRecordLatency:

    def test_record_single_latency(self):
        """TM-05: Single latency sample sets the average."""
        metrics.record_latency("llama_latency_ms", 500.0)
        assert metrics.get_summary()["llama_latency_ms"] == 500.0

    def test_record_latency_rolling_average(self):
        """TM-06: Average is computed over all samples in the window."""
        metrics.record_latency("llama_latency_ms", 100.0)
        metrics.record_latency("llama_latency_ms", 200.0)
        assert metrics.get_summary()["llama_latency_ms"] == 150.0

    def test_empty_latency_window_is_zero(self):
        """TM-07: No samples recorded returns 0.0."""
        assert metrics.get_summary()["llama_latency_ms"] == 0.0

    def test_latency_average_persisted_to_db(self):
        """TM-P1: The rolling average is written to the DB (readable after window cleared)."""
        metrics.record_latency("llama_latency_ms", 400.0)
        # Clear in-memory window to simulate reading from DB only
        metrics._latency_windows["llama_latency_ms"].clear()
        assert metrics.get_summary()["llama_latency_ms"] == 400.0


# ── Get summary ────────────────────────────────────────────────────────────

class TestGetSummary:

    def test_summary_has_all_required_keys(self):
        """TM-08: get_summary() always includes all expected keys."""
        summary = metrics.get_summary()
        expected = [
            "messages_sent_total",
            "messages_failed_total",
            "hallucination_fallbacks_total",
            "safety_blocks_total",
            "llama_latency_ms",
            "fallback_rate",
            "webhook_requests_total",
            "webhook_rejected_total",
        ]
        for key in expected:
            assert key in summary, f"Missing key: {key}"

    def test_fallback_rate_zero_when_no_sends(self):
        """TM-09: fallback_rate is 0.0 when no messages have been sent."""
        assert metrics.get_summary()["fallback_rate"] == 0.0

    def test_fallback_rate_computed_correctly(self):
        """TM-10: fallback_rate = failed / sent."""
        metrics.increment("messages_sent_total")
        metrics.increment("messages_sent_total")
        metrics.increment("messages_failed_total")
        summary = metrics.get_summary()
        assert summary["fallback_rate"] == 0.5

    def test_summary_returns_dict(self):
        """TM-11: get_summary() always returns a dict."""
        assert isinstance(metrics.get_summary(), dict)


# ── Reset ──────────────────────────────────────────────────────────────────

class TestReset:

    def test_reset_sets_counter_to_zero(self):
        """TM-R1: reset() sets a counter back to 0."""
        metrics.increment("messages_sent_total")
        metrics.increment("messages_sent_total")
        assert metrics.get_summary()["messages_sent_total"] == 2
        metrics.reset("messages_sent_total")
        assert metrics.get_summary()["messages_sent_total"] == 0

    def test_reset_clears_latency_window(self):
        """TM-R2: reset() also clears the in-memory latency window."""
        metrics.record_latency("llama_latency_ms", 800.0)
        metrics.reset("llama_latency_ms")
        assert metrics.get_summary()["llama_latency_ms"] == 0.0

    def test_reset_unknown_key_does_not_raise(self):
        """TM-R3: reset() on an unknown metric creates it at 0."""
        metrics.reset("brand_new_counter")
        assert metrics.get_summary()["brand_new_counter"] == 0.0


# ── Persistence across restarts ────────────────────────────────────────────

class TestPersistence:

    def test_counters_survive_restart(self, tmp_path):
        """TM-P2: Counters written to DB are readable after re-initialisation."""
        db_path = str(tmp_path / "persist.db")

        # First "session"
        metrics._init(db_path)
        metrics.increment("messages_sent_total")
        metrics.increment("messages_sent_total")
        assert metrics.get_summary()["messages_sent_total"] == 2

        # Simulate process restart — re-initialise pointing at the same DB
        metrics._latency_windows["llama_latency_ms"].clear()
        metrics._init(db_path)

        assert metrics.get_summary()["messages_sent_total"] == 2

    def test_multiple_counter_types_survive_restart(self, tmp_path):
        """TM-P3: All incremented counters are readable after re-initialisation."""
        db_path = str(tmp_path / "multi.db")

        metrics._init(db_path)
        metrics.increment("messages_sent_total")
        metrics.increment("messages_failed_total")
        metrics.increment("webhook_requests_total")

        # Restart
        metrics._init(db_path)

        summary = metrics.get_summary()
        assert summary["messages_sent_total"]    == 1
        assert summary["messages_failed_total"]  == 1
        assert summary["webhook_requests_total"] == 1

    def test_latency_average_readable_after_restart(self, tmp_path):
        """TM-P4: Last-persisted latency average is returned after restart (empty window)."""
        db_path = str(tmp_path / "latency.db")

        metrics._init(db_path)
        metrics.record_latency("llama_latency_ms", 300.0)
        metrics.record_latency("llama_latency_ms", 500.0)
        # Average = 400.0

        # Restart — in-memory window is gone
        metrics._latency_windows["llama_latency_ms"].clear()
        metrics._init(db_path)

        assert metrics.get_summary()["llama_latency_ms"] == 400.0
