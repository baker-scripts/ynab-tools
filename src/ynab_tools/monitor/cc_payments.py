"""Credit card close date calculation, statement balance, and auto-update."""

from __future__ import annotations

import calendar
from datetime import date, datetime, timedelta
from typing import Any

from loguru import logger

from ynab_tools.core.client import YnabClient
from ynab_tools.core.models import CreditCardPayment
from ynab_tools.core.money import dollars_to_milliunits, milliunits_to_dollars
from ynab_tools.monitor.scheduler import _add_months


def parse_cc_close_dates(close_dates_str: str) -> dict[str, int]:
    """Parse CC close dates from comma-separated 'CardName=day' format.

    Example: "Chase Freedom=15,Amex Gold=25"
    Returns: {"Chase Freedom": 15, "Amex Gold": 25}
    """
    result: dict[str, int] = {}
    if not close_dates_str.strip():
        return result
    for pair in close_dates_str.split(","):
        pair = pair.strip()
        if "=" not in pair:
            continue
        name, day_str = pair.rsplit("=", 1)
        try:
            result[name.strip()] = int(day_str.strip())
        except ValueError:
            logger.warning(f"Invalid close date: {pair}")
    return result


def _get_last_close_date(close_day: int, today: date | None = None) -> date:
    """Return the most recent statement close date for a given close day-of-month."""
    if today is None:
        today = datetime.now().date()

    try:
        this_month_close = today.replace(day=close_day)
    except ValueError:
        this_month_close = today.replace(day=calendar.monthrange(today.year, today.month)[1])

    if this_month_close <= today:
        return this_month_close

    last_month = _add_months(today, -1)
    last_day = calendar.monthrange(last_month.year, last_month.month)[1]
    return last_month.replace(day=min(close_day, last_day))


def _compute_statement_balance(
    client: YnabClient,
    account_id: str,
    cleared_balance_milliunits: int,
    close_day: int,
    today: date | None = None,
) -> tuple[float, date]:
    """Compute the statement balance as of the last close date.

    statement_balance = cleared_balance - (sum of post-close cleared transactions)

    CC balances are negative in YNAB (debt). The result is negated so that
    a $500 debt returns 500.0 as the payment amount.

    Returns:
        Tuple of (payment_dollars, last_close_date).
    """
    last_close = _get_last_close_date(close_day, today)
    day_after_close = last_close + timedelta(days=1)
    since_str = day_after_close.strftime("%Y-%m-%d")

    data = client.get(f"/budgets/{client.budget_id}/accounts/{account_id}/transactions?since_date={since_str}")

    post_close_sum = 0
    for txn in data.get("transactions", []):
        if txn.get("deleted"):
            continue
        if txn.get("cleared", "") in ("cleared", "reconciled"):
            post_close_sum += txn["amount"]

    statement_balance_milliunits = cleared_balance_milliunits - post_close_sum
    payment_dollars = max(0.0, -milliunits_to_dollars(statement_balance_milliunits))
    return payment_dollars, last_close


def _find_cc_accounts(
    all_accounts: list[dict[str, Any]],
) -> tuple[dict[str, str], dict[str, dict[str, Any]]]:
    """Extract active CC accounts from the full account list.

    Returns:
        Tuple of (name -> id mapping, id -> {name, cleared_balance_milliunits} mapping).
    """
    cc_accounts: dict[str, str] = {}
    cc_cleared: dict[str, dict[str, Any]] = {}
    for acct in all_accounts:
        if acct["type"] == "creditCard" and not acct.get("deleted", False) and not acct.get("closed", False):
            cc_accounts[acct["name"]] = acct["id"]
            cc_cleared[acct["id"]] = {
                "name": acct["name"],
                "cleared_balance_milliunits": acct["cleared_balance"],
            }
    return cc_accounts, cc_cleared


def _payments_from_close_dates(
    client: YnabClient,
    close_dates: dict[str, int],
    cc_accounts: dict[str, str],
    cc_cleared: dict[str, dict[str, Any]],
) -> dict[str, CreditCardPayment]:
    """Compute statement-based payments for cards with configured close dates."""
    payments: dict[str, CreditCardPayment] = {}
    for card_name, close_day in close_dates.items():
        account_id = cc_accounts.get(card_name)
        if not account_id:
            logger.warning(f"CC close date configured for '{card_name}' but no matching account found")
            continue
        info = cc_cleared[account_id]
        amount, last_close = _compute_statement_balance(
            client, account_id, info["cleared_balance_milliunits"], close_day
        )
        if amount > 0:
            payments[account_id] = CreditCardPayment(
                name=card_name,
                amount=amount,
                source=f"statement ({last_close})",
            )
    return payments


def _payments_from_categories(
    client: YnabClient,
    cc_accounts: dict[str, str],
    existing_payments: dict[str, CreditCardPayment],
    cc_categories_str: str,
) -> dict[str, CreditCardPayment]:
    """Fall back to category balances for CCs without close dates."""
    cc_filter: set[str] = set()
    if cc_categories_str:
        cc_filter = {c.strip() for c in cc_categories_str.split(",")}

    payments = dict(existing_payments)
    categories_data = client.get(f"/budgets/{client.budget_id}/categories")
    for group in categories_data["category_groups"]:
        if group["name"] != "Credit Card Payments":
            continue
        for cat in group["categories"]:
            if cat.get("deleted", False) or cat.get("hidden", False):
                continue
            if cc_filter and cat["id"] not in cc_filter and cat["name"] not in cc_filter:
                continue
            account_id = cc_accounts.get(cat["name"])
            if account_id and account_id not in payments:
                available = milliunits_to_dollars(cat["balance"])
                if available > 0:
                    payments[account_id] = CreditCardPayment(
                        name=cat["name"],
                        amount=available,
                        source="category_balance",
                    )
    return payments


def get_cc_payment_amounts(
    client: YnabClient,
    close_dates_str: str,
    cc_categories_str: str,
    all_accounts: list[dict[str, Any]] | None = None,
) -> tuple[dict[str, CreditCardPayment], float]:
    """Get credit card payment amounts.

    For cards with configured close dates: computes statement balance.
    For cards without: falls back to category balance.

    Returns:
        Tuple of (dict of account_id -> CreditCardPayment, total_payment_dollars).
    """
    if all_accounts is None:
        accounts_data = client.get(f"/budgets/{client.budget_id}/accounts")
        all_accounts = accounts_data["accounts"]

    cc_accounts, cc_cleared = _find_cc_accounts(all_accounts)
    close_dates = parse_cc_close_dates(close_dates_str)
    cc_payments = _payments_from_close_dates(client, close_dates, cc_accounts, cc_cleared)

    # If all CCs have close dates, skip category fallback
    uncovered = {name for name in cc_accounts if cc_accounts[name] not in cc_payments}
    if uncovered:
        cc_payments = _payments_from_categories(client, cc_accounts, cc_payments, cc_categories_str)

    total = sum(p.amount for p in cc_payments.values())
    logger.info(f"Credit card payments to account for: ${total:,.2f}")
    return cc_payments, total


def get_covered_cc_ids(
    raw_scheduled: list[dict[str, Any]],
    account_ids: list[str],
) -> set[str]:
    """Find CC account IDs that have scheduled transfers from checking.

    These CCs have their payments covered by scheduled transactions and
    should not be double-counted in the projection.
    """
    account_set = set(account_ids)
    covered: set[str] = set()

    for txn in raw_scheduled:
        if txn.get("deleted", False):
            continue
        acct_id = txn["account_id"]
        xfer_id = txn.get("transfer_account_id")
        if not xfer_id:
            continue
        # Transfer from checking to CC
        if acct_id in account_set and xfer_id not in account_set:
            covered.add(xfer_id)
        # Transfer recorded on CC side to checking
        if xfer_id in account_set and acct_id not in account_set:
            covered.add(acct_id)

    return covered


def update_cc_payment_amount(
    client: YnabClient,
    cc_account_id: str,
    cc_name: str,
    payment_amount: float,
    checking_account_id: str,
    raw_scheduled: list[dict[str, Any]],
    account_ids: list[str],
    dry_run: bool = False,
) -> None:
    """Update the scheduled payment amount for a CC if it differs.

    Finds existing scheduled transfer from checking to this CC.
    If found and amount differs: PUT update.
    """
    existing = None
    reverse = False
    for txn in raw_scheduled:
        if txn.get("deleted"):
            continue
        if txn["account_id"] == checking_account_id and txn.get("transfer_account_id") == cc_account_id:
            existing = txn
            break
        if txn["account_id"] == cc_account_id and txn.get("transfer_account_id") == checking_account_id:
            existing = txn
            reverse = True
            break

    amount_milliunits = dollars_to_milliunits(payment_amount * (1 if reverse else -1))

    if existing:
        current_amount = existing["amount"]
        if current_amount != amount_milliunits:
            old_dollars = abs(milliunits_to_dollars(current_amount))
            if dry_run:
                logger.info(f"[DRY-RUN] Would update {cc_name}: ${old_dollars:,.2f} -> ${payment_amount:,.2f}")
                return

            logger.info(f"Updating {cc_name}: ${old_dollars:,.2f} -> ${payment_amount:,.2f}")
            today = datetime.now().date()
            week_ago = today - timedelta(days=7)
            existing_date_str = existing.get("date_next") or existing.get("date_first", "")
            existing_date = date.fromisoformat(existing_date_str) if existing_date_str else None
            valid_date = existing_date if existing_date and existing_date >= week_ago else today

            client.put(
                f"/budgets/{client.budget_id}/scheduled_transactions/{existing['id']}",
                {
                    "scheduled_transaction": {
                        "account_id": existing["account_id"],
                        "date": valid_date.strftime("%Y-%m-%d"),
                        "amount": amount_milliunits,
                    }
                },
            )
        else:
            logger.info(f"{cc_name}: already correct at ${payment_amount:,.2f}")
    else:
        logger.warning(f"No scheduled payment found for {cc_name}, skipping")
