"""Monitor orchestrator — run_check() wires together all monitor modules."""

from __future__ import annotations

import calendar
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any

from loguru import logger

from ynab_tools.core.client import YnabClient
from ynab_tools.core.delta import fetch_scheduled_transactions_delta
from ynab_tools.core.models import Account, CreditCardPayment, TransactionOccurrence
from ynab_tools.monitor.accounts import fetch_account_balances
from ynab_tools.monitor.cc_payments import (
    get_cc_payment_amounts,
    get_covered_cc_ids,
    update_cc_payment_amount,
)
from ynab_tools.monitor.expenses import calculate_monthly_expenses
from ynab_tools.monitor.projection import project_minimum_balance
from ynab_tools.monitor.scheduler import expand_scheduled_transactions
from ynab_tools.monitor.thresholds import get_dynamic_thresholds


@dataclass(frozen=True)
class MonitorResult:
    """Result of a single monitor check cycle."""

    balance: float
    accounts: list[Account]
    min_balance: float
    min_date: date
    end_date: date
    alert_threshold: float
    target_threshold: float
    avg_daily: float
    avg_monthly: float
    alert_buffer_days: int
    target_buffer_days: int
    transactions: list[TransactionOccurrence]
    cc_payments: dict[str, CreditCardPayment]
    covered_cc_ids: set[str] = field(default_factory=set)
    is_alert: bool = False


def _get_end_date(monitor_days: str) -> date:
    """Parse end date from monitor_days setting.

    Empty string means end of current month.
    Otherwise, today + N days.
    """
    today = datetime.now().date()
    if monitor_days:
        try:
            days = int(monitor_days)
        except ValueError:
            raise ValueError(f"MONITOR_DAYS must be an integer, got: {monitor_days!r}") from None
        return today + timedelta(days=days)
    # End of current month
    last_day = calendar.monthrange(today.year, today.month)[1]
    return today.replace(day=last_day)


def run_check(
    client: YnabClient,
    account_ids: list[str],
    cache_dir: str,
    monitor_days: str = "",
    min_balance: int = 0,
    alert_buffer_days: int = 5,
    target_buffer_days: int = 10,
    cc_close_dates: str = "",
    cc_categories: str = "",
    dry_run: bool = False,
) -> MonitorResult:
    """Run one balance check cycle.

    Fetches accounts and scheduled transactions once and passes them through
    to avoid duplicate API calls.
    """
    end_date = _get_end_date(monitor_days)
    today = datetime.now().date()

    logger.info(f"YNAB Balance Monitor — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    logger.info(f"Projecting through {end_date}, min floor: ${min_balance:,.2f}")

    # Fetch shared data once
    accounts_data = client.get(f"/budgets/{client.budget_id}/accounts")
    all_accounts: list[dict[str, Any]] = accounts_data["accounts"]
    raw_scheduled = fetch_scheduled_transactions_delta(client, cache_dir)

    balance, accounts = fetch_account_balances(client, account_ids, all_accounts=all_accounts)
    transactions = expand_scheduled_transactions(raw_scheduled, account_ids, today, end_date)
    cc_payments, _ = get_cc_payment_amounts(client, cc_close_dates, cc_categories, all_accounts=all_accounts)

    # Update CC scheduled payment amounts
    if account_ids:
        logger.info("Checking CC payment amounts...")
        checking_id = account_ids[0]
        for cc_id, payment_info in cc_payments.items():
            if payment_info.amount > 0:
                update_cc_payment_amount(
                    client,
                    cc_id,
                    payment_info.name,
                    payment_info.amount,
                    checking_id,
                    raw_scheduled,
                    account_ids,
                    dry_run=dry_run,
                )

    # Calculate dynamic thresholds
    avg_daily, avg_monthly = calculate_monthly_expenses(client, cache_dir, dry_run=dry_run)
    alert_threshold, target_threshold = get_dynamic_thresholds(
        avg_daily,
        alert_buffer_days,
        target_buffer_days,
        min_balance,
    )
    logger.info(f"Alert threshold ({alert_buffer_days}d): ${alert_threshold:,.0f}")
    logger.info(f"Target threshold ({target_buffer_days}d): ${target_threshold:,.0f}")

    covered_cc_ids = get_covered_cc_ids(raw_scheduled, account_ids)
    min_bal, min_date = project_minimum_balance(
        balance,
        transactions,
        cc_payments,
        end_date,
        today,
        covered_cc_ids=covered_cc_ids,
    )

    is_alert = min_bal < alert_threshold
    if is_alert:
        shortfall = alert_threshold - min_bal
        logger.warning(f"ALERT: Projected balance drops ${shortfall:,.0f} below alert threshold!")
    else:
        logger.info(f"Balance stays above ${alert_threshold:,.0f} alert threshold.")

    return MonitorResult(
        balance=balance,
        accounts=accounts,
        min_balance=min_bal,
        min_date=min_date,
        end_date=end_date,
        alert_threshold=alert_threshold,
        target_threshold=target_threshold,
        avg_daily=avg_daily,
        avg_monthly=avg_monthly,
        alert_buffer_days=alert_buffer_days,
        target_buffer_days=target_buffer_days,
        transactions=transactions,
        cc_payments=cc_payments,
        covered_cc_ids=covered_cc_ids,
        is_alert=is_alert,
    )
