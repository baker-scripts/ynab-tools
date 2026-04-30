"""YNAB transaction fetching and updating for Amazon sync.

Replaces the ynab SDK with direct httpx calls via YnabClient.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from loguru import logger

from ynab_tools.config.settings import get_settings
from ynab_tools.core.client import YnabClient
from ynab_tools.core.models import Payee, Transaction
from ynab_tools.exceptions import ConfigError

YNAB_MEMO_LIMIT = 500


def fetch_payees(client: YnabClient) -> list[Payee]:
    """Fetch all payees from YNAB."""
    data = client.get(f"/budgets/{client.budget_id}/payees")
    return [Payee.model_validate(p) for p in data["payees"]]


def find_payee_by_name(payees: list[Payee], name: str) -> Payee | None:
    """Find a payee by exact name."""
    return next((p for p in payees if p.name == name), None)


def fetch_transactions_by_payee(client: YnabClient, payee_id: str) -> list[Transaction]:
    """Fetch all transactions for a specific payee."""
    data = client.get(f"/budgets/{client.budget_id}/payees/{payee_id}/transactions")
    return [Transaction.model_validate(t) for t in data["transactions"]]


def get_ynab_transactions(
    client: YnabClient,
    *,
    force: bool = False,
    days: int = 31,
) -> tuple[list[Transaction], Payee]:
    """Fetch YNAB transactions that need Amazon memo annotation.

    Returns filtered transactions and the target payee for updates.

    Raises:
        ConfigError: If required payees don't exist in YNAB.
    """
    s = get_settings()
    payees = fetch_payees(client)

    target_payee = find_payee_by_name(payees, s.ynab_payee_name_processing_completed)
    if target_payee is None:
        raise ConfigError(f"Payee '{s.ynab_payee_name_processing_completed}' not found in YNAB")

    min_date = date.today() - timedelta(days=days)

    if s.match_empty_memo or force:
        raw_txns = fetch_transactions_by_payee(client, target_payee.id)
        if force:
            txns = [t for t in raw_txns if t.date >= str(min_date)]
        else:
            allowed = set(s.approved_statuses_list)
            txns = [
                t
                for t in raw_txns
                if not t.memo and t.date >= str(min_date) and ("approved" if t.approved else "unapproved") in allowed
            ]
    else:
        needs_memo_payee = find_payee_by_name(payees, s.ynab_payee_name_to_be_processed)
        if needs_memo_payee is None:
            raise ConfigError(
                f"Payee '{s.ynab_payee_name_to_be_processed}' not found in YNAB. "
                f"Either create the payee or set MATCH_EMPTY_MEMO=true (default) to use "
                f"'{s.ynab_payee_name_processing_completed}' payee instead"
            )
        raw_txns = fetch_transactions_by_payee(client, needs_memo_payee.id)
        txns = [t for t in raw_txns if not t.approved and t.date >= str(min_date)]

    return txns, target_payee


def update_ynab_transaction(
    client: YnabClient,
    transaction_id: str,
    *,
    memo: str,
    payee_id: str,
) -> None:
    """Update a YNAB transaction's memo and payee."""
    # Enforce memo limit
    if len(memo) > YNAB_MEMO_LIMIT:
        logger.warning(f"Memo exceeds {YNAB_MEMO_LIMIT} chars ({len(memo)}), truncating")
        memo = _truncate_update_memo(memo)

    client.put(
        f"/budgets/{client.budget_id}/transactions/{transaction_id}",
        {"transaction": {"memo": memo, "payee_id": payee_id}},
    )
    logger.info(f"Updated transaction {transaction_id}")


def amount_to_decimal(milliunits: int) -> Decimal:
    """Convert YNAB milliunits to Decimal dollars."""
    return Decimal(milliunits) / Decimal("1000")


def build_memo(
    items: list[object],
    order_number: str,
    transaction_total: Decimal,
    order_total: Decimal,
    *,
    use_markdown: bool = False,
) -> str:
    """Build a memo string from Amazon order data."""
    s = get_settings()
    use_md = use_markdown or s.ynab_use_markdown

    def _format_item(item: object) -> str:
        title = getattr(item, "title", str(item))
        price = getattr(item, "price", None)
        price_str = f" (${price:.2f})" if price else ""
        return f"{title}{price_str}"

    items_str = ", ".join(_format_item(item) for item in items)
    order_url = f"https://www.amazon.com/gp/your-account/order-details?orderID={order_number}"

    link = f"[Order #{order_number}]({order_url})" if use_md else order_url

    memo = f"{items_str}\n{link}"

    if transaction_total != order_total:
        warning = f"-This transaction doesn't represent the entire order. The order total is ${order_total:.2f}-"
        memo = f"{warning}\n{memo}"

    return memo


def _truncate_update_memo(memo: str) -> str:
    """Truncate a memo for YNAB update, preserving URL and warnings."""
    lines = memo.split("\n")

    # Only treat last line as URL if it looks like one
    url_line = lines[-1] if lines and "amazon.com" in lines[-1] else ""
    content_lines = lines[:-1] if url_line else lines

    header = ""
    if content_lines and "-This transaction doesn" in content_lines[0]:
        header = content_lines[0] + "\n\n"
        content_lines = content_lines[1:]

    url_suffix = f"\n{url_line}" if url_line else ""
    remaining = YNAB_MEMO_LIMIT - len(header) - len(url_suffix) - 4
    middle = "\n".join(content_lines)
    if len(middle) > remaining:
        middle = middle[: max(remaining, 0)] + "..."

    result = f"{header}{middle}{url_suffix}"
    # Final safety: hard-truncate if still over limit
    if len(result) > YNAB_MEMO_LIMIT:
        result = result[:YNAB_MEMO_LIMIT]
    return result
