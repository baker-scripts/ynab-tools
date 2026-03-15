"""Account balance fetching for monitored YNAB accounts."""

from __future__ import annotations

from typing import Any

from loguru import logger

from ynab_tools.core.client import YnabClient
from ynab_tools.core.models import Account
from ynab_tools.core.money import milliunits_to_dollars


def fetch_account_balances(
    client: YnabClient,
    account_ids: list[str],
    all_accounts: list[dict[str, Any]] | None = None,
) -> tuple[float, list[Account]]:
    """Get current balances for all monitored accounts.

    Args:
        client: YNAB API client.
        account_ids: List of account IDs to monitor.
        all_accounts: Pre-fetched account dicts (avoids extra API call).

    Returns:
        Tuple of (total_balance_dollars, list of Account models).
    """
    if all_accounts is not None:
        acct_map = {a["id"]: a for a in all_accounts}
        accounts = []
        total = 0.0
        for aid in account_ids:
            raw = acct_map.get(aid)
            if not raw:
                logger.warning(f"Account {aid} not found in budget")
                continue
            acct = Account(
                id=raw["id"],
                name=raw["name"],
                type=raw["type"],
                balance=raw["balance"],
                cleared_balance=raw.get("cleared_balance", 0),
                closed=raw.get("closed", False),
                deleted=raw.get("deleted", False),
            )
            balance = milliunits_to_dollars(acct.balance)
            total += balance
            accounts.append(acct)
            logger.info(f"Account: {acct.name} — ${balance:,.2f}")
        if len(accounts) > 1:
            logger.info(f"Combined balance: ${total:,.2f}")
        return total, accounts

    accounts = []
    total = 0.0
    for aid in account_ids:
        data = client.get(f"/budgets/{client.budget_id}/accounts/{aid}")
        raw = data["account"]
        acct = Account(
            id=raw["id"],
            name=raw["name"],
            type=raw["type"],
            balance=raw["balance"],
            cleared_balance=raw.get("cleared_balance", 0),
            closed=raw.get("closed", False),
            deleted=raw.get("deleted", False),
        )
        balance = milliunits_to_dollars(acct.balance)
        total += balance
        accounts.append(acct)
        logger.info(f"Account: {acct.name} — ${balance:,.2f}")

    if len(accounts) > 1:
        logger.info(f"Combined balance: ${total:,.2f}")

    return total, accounts
