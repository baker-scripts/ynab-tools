"""Unified daemon scheduler for monitor and Amazon sync.

Runs one or both features on configurable schedules using a priority queue
of (next_run_time, feature) entries. Handles SIGTERM/SIGINT for graceful
shutdown and never crashes on transient errors.
"""

from __future__ import annotations

import heapq
import signal
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any

from loguru import logger


class Feature(StrEnum):
    MONITOR = "monitor"
    AMAZON = "amazon"


@dataclass
class ScheduleEntry:
    """A scheduled feature with its next run time."""

    next_run: datetime
    feature: Feature
    interval_seconds: float

    def __lt__(self, other: ScheduleEntry) -> bool:
        return self.next_run < other.next_run


@dataclass
class DaemonConfig:
    """Parsed daemon configuration."""

    monitor_interval_seconds: float = 0
    amazon_interval_seconds: float = 0
    amazon_windows: list[tuple[int, int]] = field(default_factory=list)
    monitor_only: bool = False
    amazon_only: bool = False


def _parse_schedule(schedule_str: str) -> float:
    """Parse schedule string to seconds.

    Supports:
        "HH:MM" → seconds until that time (runs daily)
        "Nh" → N hours in seconds
        "Nm" → N minutes in seconds
    """
    if not schedule_str:
        return 0

    schedule_str = schedule_str.strip()

    if schedule_str.endswith("h"):
        return float(schedule_str[:-1]) * 3600
    if schedule_str.endswith("m"):
        return float(schedule_str[:-1]) * 60

    if ":" in schedule_str:
        parts = schedule_str.split(":")
        target_hour = int(parts[0])
        target_minute = int(parts[1])
        now = datetime.now()
        target = now.replace(hour=target_hour, minute=target_minute, second=0, microsecond=0)
        if target <= now:
            target += timedelta(days=1)
        return (target - now).total_seconds()

    return float(schedule_str) * 3600


def _parse_windows(windows_str: str) -> list[tuple[int, int]]:
    """Parse time windows like '6-8,18-20' into list of (start_hour, end_hour)."""
    if not windows_str:
        return []

    result: list[tuple[int, int]] = []
    for window in windows_str.split(","):
        parts = window.strip().split("-")
        if len(parts) == 2:
            result.append((int(parts[0]), int(parts[1])))
    return result


def _in_window(windows: list[tuple[int, int]]) -> bool:
    """Check if current time is within any of the specified windows."""
    if not windows:
        return True
    hour = datetime.now().hour
    return any(start <= hour < end for start, end in windows)


def _next_window_start(windows: list[tuple[int, int]]) -> datetime:
    """Compute the next datetime when a configured window opens.

    Checks remaining windows today first, then wraps to tomorrow's first window.
    """
    now = datetime.now()
    today = now.date()

    # Check if any window opens later today
    for start, _end in sorted(windows):
        candidate = datetime.combine(today, datetime.min.time().replace(hour=start))
        if candidate > now:
            return candidate

    # No window opens later today — use first window tomorrow
    first_start = min(start for start, _end in windows)
    tomorrow = today + timedelta(days=1)
    return datetime.combine(tomorrow, datetime.min.time().replace(hour=first_start))


def _build_config(
    monitor_schedule: str,
    amazon_interval: float,
    amazon_windows: str,
    monitor_only: bool,
    amazon_only: bool,
) -> DaemonConfig:
    """Build DaemonConfig from CLI arguments, falling back to env settings."""
    from ynab_tools.config.settings import get_settings

    s = get_settings()

    config = DaemonConfig(
        monitor_only=monitor_only,
        amazon_only=amazon_only,
    )

    # Monitor schedule: CLI > env > default 1h
    schedule_str = monitor_schedule or s.schedule
    config.monitor_interval_seconds = _parse_schedule(schedule_str) if schedule_str else 3600

    # Amazon interval: CLI > env > default 24h
    if amazon_interval > 0:
        config.amazon_interval_seconds = amazon_interval * 3600
    else:
        config.amazon_interval_seconds = 24 * 3600

    config.amazon_windows = _parse_windows(amazon_windows)

    return config


def _run_monitor() -> None:
    """Execute a single monitor check cycle."""
    from ynab_tools.cli.monitor import monitor

    logger.info("Running monitor check...")
    try:
        monitor(dry_run=False)
    except Exception:
        logger.exception("Monitor check failed")


def _run_amazon() -> None:
    """Execute a single Amazon sync cycle."""
    from ynab_tools.cli.amazon import amazon

    logger.info("Running Amazon sync...")
    try:
        amazon(dry_run=False)
    except Exception:
        logger.exception("Amazon sync failed")


_shutdown = False


def _handle_signal(signum: int, frame: Any) -> None:
    """Handle shutdown signals gracefully."""
    global _shutdown
    logger.info(f"Received signal {signum}, shutting down gracefully...")
    _shutdown = True


def _build_queue(config: DaemonConfig) -> list[ScheduleEntry]:
    """Build initial priority queue from config."""
    queue: list[ScheduleEntry] = []
    now = datetime.now()

    if not config.amazon_only:
        heapq.heappush(
            queue,
            ScheduleEntry(now, Feature.MONITOR, config.monitor_interval_seconds),
        )
        logger.info(f"Monitor scheduled every {config.monitor_interval_seconds / 3600:.1f}h")

    if not config.monitor_only:
        amazon_start = now
        if config.amazon_windows and not _in_window(config.amazon_windows):
            amazon_start = _next_window_start(config.amazon_windows)
            logger.info(f"Amazon first run aligned to window at {amazon_start.strftime('%Y-%m-%d %H:%M')}")
        heapq.heappush(
            queue,
            ScheduleEntry(amazon_start, Feature.AMAZON, config.amazon_interval_seconds),
        )
        logger.info(f"Amazon sync scheduled every {config.amazon_interval_seconds / 3600:.1f}h")
        if config.amazon_windows:
            logger.info(f"Amazon windows: {config.amazon_windows}")

    return queue


def _wait_until(target: datetime) -> None:
    """Sleep in small increments until target time, checking for shutdown."""
    while not _shutdown:
        remaining = (target - datetime.now()).total_seconds()
        if remaining <= 0:
            break
        time.sleep(min(remaining, 5))


def _execute_entry(entry: ScheduleEntry, config: DaemonConfig) -> datetime | None:
    """Execute a single schedule entry.

    Returns an override for the next run time, or None to use the default interval.
    """
    if entry.feature == Feature.MONITOR:
        _run_monitor()
        return None
    elif entry.feature == Feature.AMAZON:
        if _in_window(config.amazon_windows):
            _run_amazon()
            return None
        else:
            next_open = _next_window_start(config.amazon_windows)
            logger.info(
                f"Amazon sync skipped — outside windows, next attempt at {next_open.strftime('%Y-%m-%d %H:%M')}"
            )
            return next_open
    return None


def run_daemon(
    monitor_schedule: str = "",
    amazon_interval: float = 0,
    amazon_windows: str = "",
    monitor_only: bool = False,
    amazon_only: bool = False,
) -> None:
    """Run the unified daemon with scheduled execution.

    Uses a priority queue to determine which feature to run next.
    Handles SIGTERM/SIGINT for graceful shutdown.
    """
    global _shutdown
    _shutdown = False

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    config = _build_config(monitor_schedule, amazon_interval, amazon_windows, monitor_only, amazon_only)
    queue = _build_queue(config)

    if not queue:
        logger.error("No features enabled. Use --monitor-only or --amazon-only, not both.")
        return

    logger.info("Daemon started. Press Ctrl+C to stop.")

    while not _shutdown:
        entry = heapq.heappop(queue)
        _wait_until(entry.next_run)

        if _shutdown:
            break

        next_run_override = _execute_entry(entry, config)

        # Re-schedule: use override if provided, otherwise default interval
        next_run = next_run_override or (datetime.now() + timedelta(seconds=entry.interval_seconds))
        heapq.heappush(queue, ScheduleEntry(next_run, entry.feature, entry.interval_seconds))

    logger.info("Daemon shutdown complete.")
