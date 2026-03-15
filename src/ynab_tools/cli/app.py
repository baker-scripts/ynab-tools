"""Typer CLI root application with subcommand registration."""

from __future__ import annotations

from typer import Typer

app = Typer(
    name="ynab-tools",
    help="YNAB balance monitoring and Amazon transaction annotation.",
    rich_markup_mode="rich",
    no_args_is_help=True,
)


def _register_subcommands() -> None:
    """Lazily import and register subcommands to avoid import-time side effects."""
    from ynab_tools.cli.amazon import amazon
    from ynab_tools.cli.daemon import daemon
    from ynab_tools.cli.monitor import monitor

    app.command(name="monitor")(monitor)
    app.command(name="amazon")(amazon)
    app.command(name="daemon")(daemon)


_register_subcommands()
