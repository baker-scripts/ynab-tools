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

    _send_notifications(result, s, dry_run=dry_run)


def _send_notifications(result: object, s: object, *, dry_run: bool) -> None:
    """Send Amazon sync notifications via all configured channels."""
    from ynab_tools.amazon.runner import SyncResult

    r: SyncResult = result  # type: ignore[assignment]
    sync_kwargs = {
        "matched": r.matched,
        "updated": r.updated,
        "skipped": r.skipped,
        "errors": r.errors,
        "ynab_count": r.ynab_count,
        "amazon_count": r.amazon_count,
    }

    notifiarr_key = getattr(s, "notifiarr_api_key", None)
    channel_id = getattr(s, "notifiarr_channel_id", "")
    if notifiarr_key and notifiarr_key.get_secret_value() and channel_id:
        from ynab_tools.notify.notifiarr import build_amazon_sync_payload, send_notifiarr

        payload = build_amazon_sync_payload(**sync_kwargs, channel_id=int(channel_id))
        if dry_run:
            logger.info("[DRY-RUN] Would send Notifiarr Amazon sync notification")
        else:
            send_notifiarr(payload, notifiarr_key.get_secret_value())

    apprise_urls = getattr(s, "apprise_urls", None)
    if apprise_urls and apprise_urls.get_secret_value():
        from ynab_tools.notify.apprise import send_amazon_sync

        if dry_run:
            logger.info("[DRY-RUN] Would send Apprise Amazon sync notification")
        else:
            send_amazon_sync(**sync_kwargs, apprise_urls=apprise_urls.get_secret_value())
