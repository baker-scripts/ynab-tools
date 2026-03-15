"""Amazon→YNAB sync orchestrator."""

from __future__ import annotations

from dataclasses import dataclass

from loguru import logger

from ynab_tools.amazon.matcher import locate_by_amount
from ynab_tools.amazon.scraper import AmazonOrder, AmazonTransactionRetriever
from ynab_tools.amazon.sync import (
    amount_to_decimal,
    build_memo,
    get_ynab_transactions,
    update_ynab_transaction,
)
from ynab_tools.config.settings import Settings, get_settings
from ynab_tools.core.client import YnabClient
from ynab_tools.core.models import Payee, Transaction
from ynab_tools.exceptions import (
    AmazonAuthError,
    FatalError,
    FatalSyncError,
    TransientError,
    TransientSyncError,
)


@dataclass(frozen=True)
class SyncResult:
    """Summary of a sync run."""

    ynab_count: int = 0
    amazon_count: int = 0
    matched: int = 0
    skipped: int = 0
    updated: int = 0
    errors: tuple[str, ...] = ()


def run_sync(
    client: YnabClient,
    *,
    force_refresh_amazon: bool = False,
    dry_run: bool = False,
    force: bool = False,
    transaction_days: int = 31,
) -> SyncResult:
    """Match YNAB transactions to Amazon orders and update memos.

    Args:
        client: Authenticated YNAB API client.
        force_refresh_amazon: Bypass Amazon cache.
        dry_run: Log matches without updating YNAB.
        force: Include transactions that already have memos.
        transaction_days: Days to look back for transactions.

    Returns:
        SyncResult with counts of matched/updated/skipped transactions.
    """
    s = get_settings()

    ynab_txns, target_payee = _fetch_ynab(client, force=force, days=transaction_days)
    amazon_orders = _fetch_amazon(transaction_days, force_refresh_amazon)

    logger.info(f"Matching {len(ynab_txns)} YNAB transactions against {len(amazon_orders)} Amazon orders")

    matched = 0
    skipped = 0
    updated = 0
    errors: list[str] = []

    for txn in ynab_txns:
        result = _process_transaction(client, txn, amazon_orders, target_payee, s, dry_run=dry_run)
        matched += result[0]
        skipped += result[1]
        updated += result[2]
        errors.extend(result[3])

    return SyncResult(
        ynab_count=len(ynab_txns),
        amazon_count=len(amazon_orders) + matched,
        matched=matched,
        skipped=skipped,
        updated=updated,
        errors=tuple(errors),
    )


def _fetch_ynab(client: YnabClient, *, force: bool, days: int) -> tuple[list[Transaction], Payee]:
    """Fetch YNAB transactions, wrapping errors as sync errors."""
    try:
        return get_ynab_transactions(client, force=force, days=days)
    except FatalError as e:
        raise FatalSyncError(str(e)) from e
    except TransientError as e:
        raise TransientSyncError(str(e)) from e


def _fetch_amazon(transaction_days: int, force_refresh: bool) -> list[AmazonOrder]:
    """Fetch Amazon transactions, wrapping errors as sync errors."""
    try:
        retriever = AmazonTransactionRetriever(
            transaction_days=transaction_days,
            force_refresh=force_refresh,
        )
        return retriever.get_transactions()
    except AmazonAuthError as e:
        raise FatalSyncError(f"Amazon auth failed: {e}") from e
    except (ConnectionError, TimeoutError) as e:
        raise TransientSyncError(f"Amazon network error: {e}") from e


def _process_transaction(
    client: YnabClient,
    txn: Transaction,
    amazon_orders: list[AmazonOrder],
    target_payee: Payee,
    settings: Settings,
    *,
    dry_run: bool,
) -> tuple[int, int, int, list[str]]:
    """Process a single YNAB transaction: match, build memo, update.

    Returns (matched, skipped, updated, errors) counts.
    """
    ynab_amount = amount_to_decimal(txn.amount)

    idx, is_fuzzy = locate_by_amount(
        amazon_orders,
        ynab_amount,
        tolerance=settings.amount_match_tolerance,
    )

    if idx is None:
        logger.debug(f"No Amazon match for YNAB ${-ynab_amount:.2f} on {txn.date}")
        return 0, 1, 0, []

    amazon_order = amazon_orders[idx]

    if is_fuzzy:
        diff = abs(amazon_order.transaction_total - (-ynab_amount))
        logger.warning(
            f"Fuzzy match: YNAB ${-ynab_amount:.2f} ≈ Amazon ${amazon_order.transaction_total:.2f} (diff: ${diff:.2f})"
        )

    if str(amazon_order.completed_date) != txn.date:
        logger.warning(
            f"Date mismatch: YNAB {txn.date} vs Amazon {amazon_order.completed_date} "
            f"(tolerance: {settings.date_mismatch_tolerance_days} days)"
        )

    memo = _build_and_process_memo(amazon_order)

    # Remove matched order to prevent double-matching
    amazon_orders.pop(idx)

    if dry_run:
        logger.info(
            f"DRY RUN: Would update {txn.id} with memo ({len(memo)} chars) for order #{amazon_order.order_number}"
        )
        return 1, 1, 0, []

    try:
        update_ynab_transaction(client, txn.id, memo=memo, payee_id=target_payee.id)
        return 1, 0, 1, []
    except FatalError as e:
        raise FatalSyncError(f"Update failed: {e}") from e
    except TransientError as e:
        logger.error(f"Failed to update {txn.id}: {e}")
        return 1, 1, 0, [f"Update failed for {txn.id}: {e}"]


def _build_and_process_memo(amazon_order: AmazonOrder) -> str:
    """Build memo from Amazon order and optionally process with AI."""
    memo = build_memo(
        items=amazon_order.items,
        order_number=amazon_order.order_number,
        transaction_total=amazon_order.transaction_total,
        order_total=amazon_order.order_total,
    )

    try:
        from ynab_tools.amazon.memo import process_memo

        memo = process_memo(memo)
    except Exception:
        logger.debug("AI memo processing unavailable, using raw memo")

    return memo
