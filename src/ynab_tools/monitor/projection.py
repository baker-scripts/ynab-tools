"""Day-by-day balance projection with CC dedup."""

from __future__ import annotations

from datetime import date, timedelta

from loguru import logger

from ynab_tools.core.models import CreditCardPayment, TransactionOccurrence


def project_minimum_balance(
    current_balance: float,
    scheduled_transactions: list[TransactionOccurrence],
    cc_payments: dict[str, CreditCardPayment],
    end_date: date,
    today: date,
    covered_cc_ids: set[str] | None = None,
) -> tuple[float, date]:
    """Walk day-by-day to find the minimum projected balance.

    CC payments with scheduled transfers are excluded from the day-1 lump sum.
    Only truly unscheduled CC payments are applied on day 1 as a conservative
    estimate.

    Returns:
        Tuple of (min_balance, min_date).
    """
    if covered_cc_ids is None:
        covered_cc_ids = set()

    # Unscheduled CC payment total — apply on day 1
    unscheduled_cc_total = sum(p.amount for cc_id, p in cc_payments.items() if cc_id not in covered_cc_ids)
    if unscheduled_cc_total > 0:
        logger.info(f"Unscheduled CC payments (applied today): ${unscheduled_cc_total:,.2f}")
    else:
        logger.info("All CC payments are scheduled.")

    # Build day-by-day projection
    balance = current_balance - unscheduled_cc_total
    min_balance = balance
    min_date = today

    # Group scheduled transactions by date
    txn_by_date: dict[date, list[TransactionOccurrence]] = {}
    for txn in scheduled_transactions:
        txn_by_date.setdefault(txn.date, []).append(txn)

    day = today
    while day <= end_date:
        if day in txn_by_date:
            for txn in txn_by_date[day]:
                balance += txn.amount
        if balance < min_balance:
            min_balance = balance
            min_date = day
        day += timedelta(days=1)

    logger.info(f"Projected minimum balance: ${min_balance:,.2f} on {min_date}")
    return min_balance, min_date
