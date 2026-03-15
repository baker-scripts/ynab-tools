"""Dynamic alert and target threshold calculation."""

from __future__ import annotations


def get_dynamic_thresholds(
    avg_daily_expenses: float,
    alert_buffer_days: int,
    target_buffer_days: int,
    min_balance: int,
) -> tuple[float, float]:
    """Compute alert and target thresholds for the projected minimum.

    Thresholds represent how many days of average spending the cushion
    should cover for unplanned expenses:
    - alert: transfer from HYSA now
    - target: consider transferring

    min_balance is used as a floor.

    Returns:
        Tuple of (alert_threshold, target_threshold).
    """
    alert_threshold = round(max(min_balance, avg_daily_expenses * alert_buffer_days), -2)
    target_threshold = round(max(min_balance, avg_daily_expenses * target_buffer_days), -2)
    return alert_threshold, target_threshold
