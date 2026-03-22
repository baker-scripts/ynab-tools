"""Tests for daemon scheduler utilities."""

from __future__ import annotations

import heapq
from datetime import datetime

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

    def test_in_window(self):
        hour = datetime.now().hour
        assert _in_window([(hour, hour + 1)]) is True

    def test_outside_window(self):
        hour = datetime.now().hour
        # Use a window that doesn't contain the current hour
        start = (hour + 2) % 24
        end = (hour + 3) % 24
        if start < end:
            assert _in_window([(start, end)]) is False


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
    def test_next_window_today(self):
        now = datetime.now()
        # Window 2 hours from now
        future_hour = (now.hour + 2) % 24
        if future_hour > now.hour:  # only test if doesn't wrap past midnight
            result = _next_window_start([(future_hour, future_hour + 1)])
            assert result.hour == future_hour
            assert result.date() == now.date()

    def test_next_window_tomorrow(self):
        now = datetime.now()
        # Window 1 hour ago (already passed today)
        past_hour = (now.hour - 1) % 24
        if past_hour < now.hour:  # only test if doesn't wrap
            result = _next_window_start([(past_hour, past_hour + 1)])
            assert result.hour == past_hour
            assert result.date() > now.date()

    def test_picks_earliest_future_window(self):
        now = datetime.now()
        h1 = (now.hour + 2) % 24
        h2 = (now.hour + 5) % 24
        if h1 > now.hour and h2 > h1:
            result = _next_window_start([(h2, h2 + 1), (h1, h1 + 1)])
            assert result.hour == h1


class TestExecuteEntry:
    def test_monitor_returns_none(self, monkeypatch):
        monkeypatch.setattr("ynab_tools.daemon.scheduler._run_monitor", lambda: None)
        entry = ScheduleEntry(datetime.now(), Feature.MONITOR, 3600)
        config = DaemonConfig(monitor_interval_seconds=3600)
        assert _execute_entry(entry, config) is None

    def test_amazon_outside_window_returns_next_open(self, monkeypatch):
        now = datetime.now()
        # Use a window that's NOT the current hour
        future_hour = (now.hour + 3) % 24
        if future_hour <= now.hour:
            return  # skip if wraps (edge case)
        config = DaemonConfig(
            amazon_interval_seconds=86400,
            amazon_windows=[(future_hour, future_hour + 1)],
        )
        entry = ScheduleEntry(now, Feature.AMAZON, 86400)
        result = _execute_entry(entry, config)
        assert result is not None
        assert result.hour == future_hour

    def test_amazon_inside_window_returns_none(self, monkeypatch):
        monkeypatch.setattr("ynab_tools.daemon.scheduler._run_amazon", lambda: None)
        now = datetime.now()
        config = DaemonConfig(
            amazon_interval_seconds=86400,
            amazon_windows=[(now.hour, now.hour + 1)],
        )
        entry = ScheduleEntry(now, Feature.AMAZON, 86400)
        assert _execute_entry(entry, config) is None


class TestFeatureEnum:
    def test_values(self):
        assert Feature.MONITOR == "monitor"
        assert Feature.AMAZON == "amazon"
