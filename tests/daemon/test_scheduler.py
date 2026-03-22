"""Tests for daemon scheduler utilities."""

from __future__ import annotations

import heapq
from datetime import datetime


def _fixed_datetime(hour: int, minute: int = 0):
    """Return a datetime class substitute that pins now() to a fixed hour."""

    class _FakeDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            base = datetime(2026, 3, 22, hour, minute, 0)
            return base

    return _FakeDatetime


from ynab_tools.daemon.scheduler import (
    DaemonConfig,
    Feature,
    ScheduleEntry,
    _build_queue,
    _execute_entry,
    _in_window,
    _next_window_start,
    _parse_schedule,
    _parse_windows,
)


class TestParseSchedule:
    def test_hours_suffix(self):
        assert _parse_schedule("2h") == 7200

    def test_minutes_suffix(self):
        assert _parse_schedule("30m") == 1800

    def test_empty_string(self):
        assert _parse_schedule("") == 0

    def test_bare_number_as_hours(self):
        assert _parse_schedule("3") == 10800

    def test_time_format(self):
        """HH:MM returns a positive number of seconds."""
        result = _parse_schedule("06:00")
        assert result > 0
        assert result <= 86400


class TestParseWindows:
    def test_single_window(self):
        assert _parse_windows("6-8") == [(6, 8)]

    def test_multiple_windows(self):
        assert _parse_windows("6-8,18-20") == [(6, 8), (18, 20)]

    def test_empty(self):
        assert _parse_windows("") == []

    def test_whitespace(self):
        assert _parse_windows(" 6-8 , 18-20 ") == [(6, 8), (18, 20)]


class TestInWindow:
    def test_empty_windows_always_true(self):
        assert _in_window([]) is True

    def test_in_window(self, monkeypatch):
        monkeypatch.setattr("ynab_tools.daemon.scheduler.datetime", _fixed_datetime(10))
        assert _in_window([(10, 12)]) is True

    def test_outside_window(self, monkeypatch):
        monkeypatch.setattr("ynab_tools.daemon.scheduler.datetime", _fixed_datetime(14))
        assert _in_window([(10, 12)]) is False

    def test_cross_midnight_inside_before_midnight(self, monkeypatch):
        monkeypatch.setattr("ynab_tools.daemon.scheduler.datetime", _fixed_datetime(23))
        assert _in_window([(22, 2)]) is True

    def test_cross_midnight_inside_after_midnight(self, monkeypatch):
        monkeypatch.setattr("ynab_tools.daemon.scheduler.datetime", _fixed_datetime(1))
        assert _in_window([(22, 2)]) is True

    def test_cross_midnight_outside(self, monkeypatch):
        monkeypatch.setattr("ynab_tools.daemon.scheduler.datetime", _fixed_datetime(15))
        assert _in_window([(22, 2)]) is False

    def test_cross_midnight_at_end_hour_excluded(self, monkeypatch):
        monkeypatch.setattr("ynab_tools.daemon.scheduler.datetime", _fixed_datetime(2))
        assert _in_window([(22, 2)]) is False


class TestScheduleEntry:
    def test_ordering(self):
        early = ScheduleEntry(datetime(2026, 1, 1, 9, 0), Feature.MONITOR, 3600)
        late = ScheduleEntry(datetime(2026, 1, 1, 10, 0), Feature.AMAZON, 3600)
        assert early < late

    def test_heapq_ordering(self):
        late = ScheduleEntry(datetime(2026, 1, 1, 10, 0), Feature.AMAZON, 3600)
        early = ScheduleEntry(datetime(2026, 1, 1, 9, 0), Feature.MONITOR, 3600)
        heap: list[ScheduleEntry] = []
        heapq.heappush(heap, late)
        heapq.heappush(heap, early)
        assert heapq.heappop(heap).feature == Feature.MONITOR


class TestBuildQueue:
    def test_both_features(self):
        config = DaemonConfig(
            monitor_interval_seconds=3600,
            amazon_interval_seconds=7200,
        )
        queue = _build_queue(config)
        assert len(queue) == 2

    def test_monitor_only(self):
        config = DaemonConfig(
            monitor_interval_seconds=3600,
            amazon_interval_seconds=7200,
            amazon_only=False,
            monitor_only=True,
        )
        queue = _build_queue(config)
        # monitor_only means only monitor, no amazon
        # Wait, monitor_only=True means skip amazon
        # The logic checks: if not config.amazon_only → add monitor; if not config.monitor_only → add amazon
        # So monitor_only=True → skip amazon → queue has only monitor
        assert len(queue) == 1
        assert queue[0].feature == Feature.MONITOR

    def test_amazon_only(self):
        config = DaemonConfig(
            monitor_interval_seconds=3600,
            amazon_interval_seconds=7200,
            amazon_only=True,
            monitor_only=False,
        )
        queue = _build_queue(config)
        assert len(queue) == 1
        assert queue[0].feature == Feature.AMAZON

    def test_both_exclusive_empty(self):
        config = DaemonConfig(
            monitor_interval_seconds=3600,
            amazon_interval_seconds=7200,
            amazon_only=True,
            monitor_only=True,
        )
        queue = _build_queue(config)
        assert len(queue) == 0


class TestNextWindowStart:
    def test_next_window_today(self, monkeypatch):
        monkeypatch.setattr("ynab_tools.daemon.scheduler.datetime", _fixed_datetime(10))
        result = _next_window_start([(14, 16)])
        assert result.hour == 14
        assert result.date() == datetime(2026, 3, 22).date()

    def test_next_window_tomorrow(self, monkeypatch):
        monkeypatch.setattr("ynab_tools.daemon.scheduler.datetime", _fixed_datetime(10))
        result = _next_window_start([(8, 9)])
        assert result.hour == 8
        assert result.date() == datetime(2026, 3, 23).date()

    def test_picks_earliest_future_window(self, monkeypatch):
        monkeypatch.setattr("ynab_tools.daemon.scheduler.datetime", _fixed_datetime(10))
        result = _next_window_start([(18, 20), (14, 16)])
        assert result.hour == 14

    def test_cross_midnight_window_next_start(self, monkeypatch):
        # At 15:00, next opening for window 22-2 should be 22:00 today
        monkeypatch.setattr("ynab_tools.daemon.scheduler.datetime", _fixed_datetime(15))
        result = _next_window_start([(22, 2)])
        assert result.hour == 22
        assert result.date() == datetime(2026, 3, 22).date()

    def test_cross_midnight_inside_no_false_next(self, monkeypatch):
        # At 23:00, inside window 22-2 — _next_window_start shouldn't be
        # called in this case, but if it is, it returns tomorrow's 22:00
        monkeypatch.setattr("ynab_tools.daemon.scheduler.datetime", _fixed_datetime(23))
        result = _next_window_start([(22, 2)])
        assert result.hour == 22
        assert result.date() == datetime(2026, 3, 23).date()


class TestExecuteEntry:
    def test_monitor_returns_none(self, monkeypatch):
        monkeypatch.setattr("ynab_tools.daemon.scheduler._run_monitor", lambda: None)
        entry = ScheduleEntry(datetime(2026, 3, 22, 10), Feature.MONITOR, 3600)
        config = DaemonConfig(monitor_interval_seconds=3600)
        assert _execute_entry(entry, config) is None

    def test_amazon_outside_window_returns_next_open(self, monkeypatch):
        monkeypatch.setattr("ynab_tools.daemon.scheduler.datetime", _fixed_datetime(10))
        config = DaemonConfig(
            amazon_interval_seconds=86400,
            amazon_windows=[(14, 16)],
        )
        entry = ScheduleEntry(datetime(2026, 3, 22, 10), Feature.AMAZON, 86400)
        result = _execute_entry(entry, config)
        assert result is not None
        assert result.hour == 14

    def test_amazon_inside_window_returns_none(self, monkeypatch):
        monkeypatch.setattr("ynab_tools.daemon.scheduler._run_amazon", lambda: None)
        monkeypatch.setattr("ynab_tools.daemon.scheduler.datetime", _fixed_datetime(10))
        config = DaemonConfig(
            amazon_interval_seconds=86400,
            amazon_windows=[(10, 12)],
        )
        entry = ScheduleEntry(datetime(2026, 3, 22, 10), Feature.AMAZON, 86400)
        assert _execute_entry(entry, config) is None


class TestFeatureEnum:
    def test_values(self):
        assert Feature.MONITOR == "monitor"
        assert Feature.AMAZON == "amazon"
