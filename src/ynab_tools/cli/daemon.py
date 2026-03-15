"""CLI subcommand: ynab-tools daemon."""

from __future__ import annotations

from typing import Annotated

from typer import Option


def daemon(
    monitor_schedule: Annotated[
        str,
        Option("--monitor-schedule", help="Monitor schedule: 'HH:MM' for daily, 'Nh' for interval"),
    ] = "",
    amazon_interval: Annotated[
        float,
        Option("--amazon-interval", help="Hours between Amazon sync runs (min: 12)"),
    ] = 0,
    amazon_windows: Annotated[
        str,
        Option("--amazon-windows", help="Time windows for Amazon sync, e.g. '6-8,18-20'"),
    ] = "",
    monitor_only: Annotated[
        bool,
        Option("--monitor-only", help="Only run the balance monitor"),
    ] = False,
    amazon_only: Annotated[
        bool,
        Option("--amazon-only", help="Only run the Amazon sync"),
    ] = False,
) -> None:
    """[bold cyan]Run as a unified daemon with scheduled execution.[/]"""
    from ynab_tools.daemon.scheduler import run_daemon

    run_daemon(
        monitor_schedule=monitor_schedule,
        amazon_interval=amazon_interval,
        amazon_windows=amazon_windows,
        monitor_only=monitor_only,
        amazon_only=amazon_only,
    )
