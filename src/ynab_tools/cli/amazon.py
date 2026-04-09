"""CLI subcommand: ynab-tools amazon."""

from __future__ import annotations

from typing import Annotated

from loguru import logger
from typer import Option


def amazon(
    dry_run: Annotated[
        bool,
        Option("--dry-run", help="Show what would be updated without making changes"),
    ] = False,
    force: Annotated[
        bool,
        Option("--force", help="Process all matching transactions, even those with existing memos"),
    ] = False,
    days: Annotated[
        int,
        Option("-d", "--days", help="Number of days to look back for transactions", min=1, max=365),
    ] = 31,
    force_refresh: Annotated[
        bool,
        Option("--force-refresh", help="Bypass Amazon cache and re-fetch orders"),
    ] = False,
) -> None:
    """[bold cyan]Match YNAB transactions to Amazon orders and annotate memos.[/]"""
    from ynab_tools.amazon.runner import run_sync
    from ynab_tools.cli._client import make_client
    from ynab_tools.config.settings import get_settings

    s = get_settings()
    client = make_client(s)

    result = run_sync(
        client,
        dry_run=dry_run,
        force=force,
        transaction_days=days,
        force_refresh_amazon=force_refresh,
    )

    logger.info(f"Amazon sync complete: {result.matched} matched, {result.updated} updated, {result.skipped} skipped")
    if result.errors:
        for err in result.errors:
            logger.error(err)

    _send_notification(result, s, dry_run=dry_run)


def _send_notification(result: object, s: object, *, dry_run: bool) -> None:
    """Send Amazon sync notification via Notifiarr."""
    from ynab_tools.amazon.runner import SyncResult

    r: SyncResult = result  # type: ignore[assignment]

    notifiarr_key = getattr(s, "notifiarr_api_key", None)
    channel_id = getattr(s, "notifiarr_channel_id", "")
    if not (notifiarr_key and notifiarr_key.get_secret_value() and channel_id):
        return

    from ynab_tools.notify.notifiarr import build_amazon_sync_payload, send_notifiarr

    payload = build_amazon_sync_payload(
        matched=r.matched,
        updated=r.updated,
        skipped=r.skipped,
        errors=r.errors,
        ynab_count=r.ynab_count,
        amazon_count=r.amazon_count,
        channel_id=int(channel_id),
    )

    if dry_run:
        logger.info("[DRY-RUN] Would send Notifiarr Amazon sync notification")
    else:
        send_notifiarr(payload, notifiarr_key.get_secret_value())
