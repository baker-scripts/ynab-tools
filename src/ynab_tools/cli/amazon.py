"""CLI subcommand: ynab-tools amazon."""

from __future__ import annotations

from typing import Annotated

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
        Option("-d", "--days", help="Number of days to look back for transactions", min=1, max=31),
    ] = 31,
) -> None:
    """[bold cyan]Match YNAB transactions to Amazon orders and annotate memos.[/]"""
    from ynab_tools.amazon.runner import run_sync

    run_sync(dry_run=dry_run, force=force, days=days)
