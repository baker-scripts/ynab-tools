"""Recurrence expansion for YNAB scheduled transactions.

Supports all 13 YNAB frequency types including twiceAMonth.
"""

from __future__ import annotations

import calendar
from datetime import date, timedelta
from typing import Any

from loguru import logger

from ynab_tools.core.models import TransactionOccurrence
from ynab_tools.core.money import milliunits_to_dollars


def _add_months(d: date, months: int) -> date:
    """Add months to a date, clamping to the last day of the target month."""
    month = d.month - 1 + months
    year = d.year + month // 12
    month = month % 12 + 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def _expand_occurrences(next_date: date, frequency: str, start: date, end: date) -> list[date]:
    """Generate all occurrence dates of a recurring transaction within [start, end].

    Args:
        next_date: The next scheduled occurrence (from the API).
        frequency: YNAB frequency string.
        start: Start of monitoring window.
        end: End of monitoring window.

    Returns:
        Sorted list of dates within the window.
    """
    deltas: dict[str, Any] = {
        "daily": lambda d: d + timedelta(days=1),
        "weekly": lambda d: d + timedelta(weeks=1),
        "everyOtherWeek": lambda d: d + timedelta(weeks=2),
        "every4Weeks": lambda d: d + timedelta(weeks=4),
        "monthly": lambda d: _add_months(d, 1),
        "everyOtherMonth": lambda d: _add_months(d, 2),
        "every3Months": lambda d: _add_months(d, 3),
        "every4Months": lambda d: _add_months(d, 4),
        "twiceAMonth": None,  # special case
        "twiceAYear": lambda d: _add_months(d, 6),
        "yearly": lambda d: _add_months(d, 12),
        "everyOtherYear": lambda d: _add_months(d, 24),
    }

    if frequency == "never" or frequency not in deltas:
        if start <= next_date <= end:
            return [next_date]
        return []

    # twiceAMonth: YNAB schedules on the original day and ~15 days offset
    if frequency == "twiceAMonth":
        dates: list[date] = []
        day1 = next_date.day
        day2 = day1 + 15 if day1 <= 15 else day1 - 15
        d = next_date.replace(day=1)
        d = _add_months(d, -1)  # back up one month
        while d <= end:
            last_day = calendar.monthrange(d.year, d.month)[1]
            for target_day in (day1, day2):
                clamped = min(target_day, last_day)
                candidate = date(d.year, d.month, clamped)
                if start <= candidate <= end:
                    dates.append(candidate)
            d = _add_months(d, 1)
        return sorted(set(dates))

    # General case: walk forward using the delta function
    advance = deltas[frequency]
    dates = []
    d = next_date
    while d <= end:
        if d >= start:
            dates.append(d)
        d = advance(d)
    return dates


def expand_scheduled_transactions(
    raw_scheduled: list[dict[str, Any]],
    account_ids: list[str],
    today: date,
    end_date: date,
) -> list[TransactionOccurrence]:
    """Expand scheduled transactions into individual occurrences.

    Args:
        raw_scheduled: Raw scheduled transaction dicts from YNAB API.
        account_ids: Monitored account IDs.
        today: Start of projection window.
        end_date: End of projection window.

    Returns:
        Sorted list of TransactionOccurrence models.
    """
    account_set = set(account_ids)
    occurrences: list[TransactionOccurrence] = []

    for txn in raw_scheduled:
        if txn.get("deleted", False):
            continue

        acct_id = txn["account_id"]
        xfer_id = txn.get("transfer_account_id")

        on_checking = acct_id in account_set
        xfer_to_checking = xfer_id in account_set
        if not on_checking and not xfer_to_checking:
            continue

        date_str = txn.get("date_next") or txn.get("date_first", "")
        if not date_str:
            continue
        next_date = date.fromisoformat(date_str)
        frequency = txn.get("frequency", "never")

        raw_amount = milliunits_to_dollars(txn["amount"])
        amount = -raw_amount if xfer_to_checking and not on_checking else raw_amount
        payee = txn.get("payee_name") or "Unknown"
        transfer_account_id = xfer_id if on_checking else acct_id

        for occ_date in _expand_occurrences(next_date, frequency, today, end_date):
            freq_label = f" ({frequency})" if frequency != "never" else ""
            occurrences.append(
                TransactionOccurrence(
                    date=occ_date,
                    amount=amount,
                    payee=payee,
                    transfer_account_id=transfer_account_id,
                    frequency=frequency,
                    label=f"{payee}{freq_label}",
                )
            )

    occurrences.sort(key=lambda t: t.date)
    logger.info(f"Scheduled transactions through {end_date}: {len(occurrences)}")
    return occurrences
