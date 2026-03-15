"""CLI subcommand: ynab-tools monitor."""

from __future__ import annotations

from typing import Annotated

from typer import Option


def monitor(
    dry_run: Annotated[
        bool,
        Option("--dry-run", help="Run without sending notifications or updating CC payments"),
    ] = False,
) -> None:
    """[bold cyan]Run balance projection and alert check.[/]"""
    from ynab_tools.config.settings import get_settings
    from ynab_tools.monitor.runner import run_check

    settings = get_settings()
    run_check(dry_run=dry_run, settings=settings)
