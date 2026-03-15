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
