"""Tests for dynamic threshold calculation."""

from __future__ import annotations

from ynab_tools.monitor.thresholds import get_dynamic_thresholds


class TestGetDynamicThresholds:
    def test_basic(self):
        alert, target = get_dynamic_thresholds(
            avg_daily_expenses=100.0,
            alert_buffer_days=5,
            target_buffer_days=10,
            min_balance=0,
        )
        assert alert == 500.0
        assert target == 1000.0

    def test_rounds_to_nearest_hundred(self):
        alert, target = get_dynamic_thresholds(
            avg_daily_expenses=123.45,
            alert_buffer_days=5,
            target_buffer_days=10,
            min_balance=0,
        )
        assert alert == 600.0
        assert target == 1200.0

    def test_min_balance_floor(self):
        alert, target = get_dynamic_thresholds(
            avg_daily_expenses=10.0,
            alert_buffer_days=5,
            target_buffer_days=10,
            min_balance=500,
        )
        assert alert == 500.0
        assert target == 500.0

    def test_zero_expenses(self):
        alert, target = get_dynamic_thresholds(
            avg_daily_expenses=0.0,
            alert_buffer_days=5,
            target_buffer_days=10,
            min_balance=0,
        )
        assert alert == 0.0
        assert target == 0.0

    def test_high_expenses(self):
        alert, target = get_dynamic_thresholds(
            avg_daily_expenses=500.0,
            alert_buffer_days=5,
            target_buffer_days=10,
            min_balance=0,
        )
        assert alert == 2500.0
        assert target == 5000.0
