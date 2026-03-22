"""Notification context model — collects all data needed for alert/update messages."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

from ynab_tools.core.models import CreditCardPayment, TransactionOccurrence


@dataclass(frozen=True)
class InflowSummary:
    """Aggregated scheduled inflow by payee."""

    payee: str
    amount: float
    count: int


@dataclass(frozen=True)
class NotificationContext:
    """All data needed to build alert or update notifications."""

    current_balance: float
    accounts: list[dict[str, object]]
    min_balance: float
    min_date: date
    end_date: date
    alert_threshold: float
    target_threshold: float
    alert_buffer_days: int
    target_buffer_days: int
    avg_daily_expenses: float
    buffer_days_remaining: float
    shortfall: float
    transfer_to_target: float
    upcoming_outflows: list[TransactionOccurrence]
    scheduled_inflows: list[InflowSummary]
    cc_payments: dict[str, CreditCardPayment] = field(default_factory=dict)


def build_notification_context(
    *,
    current_balance: float,
    accounts: list[dict[str, object]],
    min_balance: float,
    min_date: date,
    end_date: date,
    alert_threshold: float,
    target_threshold: float,
    alert_buffer_days: int,
    target_buffer_days: int,
    avg_daily_expenses: float,
    transactions: list[TransactionOccurrence],
    cc_payments: dict[str, CreditCardPayment],
    covered_cc_ids: set[str] | None = None,
    today: date | None = None,
) -> NotificationContext:
    """Build a NotificationContext from monitor results.

    Aggregates inflows by payee, picks top 5 upcoming outflows in next 7 days,
    and tags CC payments as scheduled/unscheduled.
    """
    if today is None:
        from datetime import datetime

        today = datetime.now().date()

    shortfall = max(0.0, alert_threshold - min_balance)
    transfer_to_target = max(0.0, target_threshold - min_balance)
    buffer_days = min_balance / avg_daily_expenses if avg_daily_expenses > 0 else 0.0

    # Top 5 largest outflows in next 7 days (exclude CC payment transfers
    # that are already shown in the CC Payments section)
    covered = covered_cc_ids or set()
    week_out = today + timedelta(days=7)
    upcoming = sorted(
        [
            t
            for t in transactions
            if today <= t.date <= week_out and t.amount < 0 and t.transfer_account_id not in covered
        ],
        key=lambda t: t.amount,
    )[:5]

    # Aggregate inflows by payee
    inflow_totals: dict[str, tuple[float, int]] = {}
    for t in transactions:
        if t.amount > 0:
            existing = inflow_totals.get(t.payee, (0.0, 0))
            inflow_totals[t.payee] = (existing[0] + t.amount, existing[1] + 1)

    inflow_summaries = [
        InflowSummary(payee=payee, amount=amount, count=count) for payee, (amount, count) in inflow_totals.items()
    ]

    # Tag CC payments as scheduled/unscheduled
    tagged_cc = {
        cc_id: payment.model_copy(update={"scheduled": cc_id in covered}) for cc_id, payment in cc_payments.items()
    }

    return NotificationContext(
        current_balance=current_balance,
        accounts=accounts,
        min_balance=min_balance,
        min_date=min_date,
        end_date=end_date,
        alert_threshold=alert_threshold,
        target_threshold=target_threshold,
        alert_buffer_days=alert_buffer_days,
        target_buffer_days=target_buffer_days,
        avg_daily_expenses=avg_daily_expenses,
        buffer_days_remaining=buffer_days,
        shortfall=shortfall,
        transfer_to_target=transfer_to_target,
        upcoming_outflows=upcoming,
        scheduled_inflows=inflow_summaries,
        cc_payments=tagged_cc,
    )
