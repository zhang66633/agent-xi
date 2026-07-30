"""测试 UsageTracker — 用量统计 & 成本追踪。"""

from __future__ import annotations

import tempfile
from pathlib import Path

from agent_xi.server.usage_tracker import UsageTracker


class TestUsageTracker:
    def test_record_and_summary(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tracker = UsageTracker(Path(tmpdir))
            try:
                tracker.record("deepseek-chat", "deepseek", 1500, 800)
                tracker.record("deepseek-chat", "deepseek", 2000, 1200)
                tracker.record("claude-sonnet-4-20250514", "claude", 100, 50)
                summary = tracker.get_summary(days=30)
                assert summary.total_calls == 3
                assert summary.total_input_tokens == 3600
                assert summary.total_output_tokens == 2050
                assert summary.total_cost_usd > 0
                assert "deepseek-chat" in summary.by_model
                assert summary.by_model["deepseek-chat"]["calls"] == 2
            finally:
                tracker.close()

    def test_daily_breakdown(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tracker = UsageTracker(Path(tmpdir))
            try:
                tracker.record("deepseek-chat", "deepseek", 100, 50)
                tracker.record("deepseek-chat", "deepseek", 200, 100)
                daily = tracker.get_daily_breakdown(days=7)
                assert len(daily) >= 1
                total_calls = sum(d["calls"] for d in daily)
                assert total_calls == 2
            finally:
                tracker.close()

    def test_recent_calls(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tracker = UsageTracker(Path(tmpdir))
            try:
                tracker.record("deepseek-chat", "deepseek", 100, 50)
                calls = tracker.get_recent_calls(limit=10)
                assert len(calls) == 1
                assert calls[0]["model"] == "deepseek-chat"
                assert calls[0]["input_tokens"] == 100
                assert calls[0]["output_tokens"] == 50
            finally:
                tracker.close()

    def test_total_summary(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tracker = UsageTracker(Path(tmpdir))
            try:
                tracker.record("deepseek-chat", "deepseek", 500, 300)
                tracker.record("gpt-4o", "openai", 200, 100)
                total = tracker.get_total_summary()
                assert total.total_calls == 2
                assert total.total_input_tokens == 700
                assert total.total_output_tokens == 400
            finally:
                tracker.close()

    def test_zero_tokens_not_recorded(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tracker = UsageTracker(Path(tmpdir))
            try:
                tracker.record("deepseek-chat", "deepseek", 0, 0)
                summary = tracker.get_summary(days=30)
                assert summary.total_calls == 0
            finally:
                tracker.close()

    def test_cost_estimation_default_model(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tracker = UsageTracker(Path(tmpdir))
            try:
                tracker.record("unknown-model", "unknown", 1000000, 1000000)
                summary = tracker.get_summary(days=30)
                assert summary.total_cost_usd == 0.0
            finally:
                tracker.close()

    def test_close(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tracker = UsageTracker(Path(tmpdir))
            tracker.record("deepseek-chat", "deepseek", 100, 50)
            tracker.close()
