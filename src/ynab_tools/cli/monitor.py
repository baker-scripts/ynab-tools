"""CLI subcommand: ynab-tools monitor."""

from __future__ import annotations

from typing import Annotated

from loguru import logger
from typer import Option


def monitor(
    dry_run: Annotated[
        bool,
        Option("--dry-run", help="Run without sending notifications or updating CC payments"),
    ] = False,
) -> None:
    """[bold cyan]Run balance projection and alert check.[/]"""
    from ynab_tools.cli._client import make_client
    from ynab_tools.config.settings import get_settings
    from ynab_tools.monitor.runner import run_check

    s = get_settings()
    client = make_client(s)

    result = run_check(
        client,
        account_ids=s.account_ids,
        cache_dir=s.cache_dir,
        monitor_days=s.monitor_days,
        min_balance=s.min_balance,
        alert_buffer_days=s.ynab_alert_buffer_days,
        target_buffer_days=s.ynab_target_buffer_days,
        cc_close_dates=s.ynab_cc_close_dates,
        cc_categories=s.ynab_cc_categories,
        dry_run=dry_run,
    )

    _send_notifications(result, s, dry_run=dry_run)


def _send_notifications(result: object, s: object, *, dry_run: bool) -> None:
    """Send alert/update notifications based on monitor result."""
    from ynab_tools.monitor.runner import MonitorResult
    from ynab_tools.notify.types import build_notification_context

    r: MonitorResult = result  # type: ignore[assignment]
    ctx = build_notification_context(
        current_balance=r.balance,
        accounts=[{"name": a.name, "balance": a.balance} for a in r.accounts],
        min_balance=r.min_balance,
        min_date=r.min_date,
        end_date=r.end_date,
        alert_threshold=r.alert_threshold,
        target_threshold=r.target_threshold,
        alert_buffer_days=r.alert_buffer_days,
        target_buffer_days=r.target_buffer_days,
        avg_daily_expenses=r.avg_daily,
        transactions=r.transactions,
        cc_payments=r.cc_payments,
        covered_cc_ids=r.covered_cc_ids,
    )

    if r.is_alert:
        _send_alert(ctx, s, dry_run=dry_run)

    _send_update(ctx, s, dry_run=dry_run)


def _send_alert(ctx: object, s: object, *, dry_run: bool) -> None:
    """Send alert notifications via Notifiarr and Apprise."""
    from ynab_tools.notify.types import NotificationContext

    n_ctx: NotificationContext = ctx  # type: ignore[assignment]

    notifiarr_key = getattr(s, "notifiarr_api_key", None)
    channel_id = getattr(s, "notifiarr_channel_id", "")
    if notifiarr_key and notifiarr_key.get_secret_value() and channel_id:
        from ynab_tools.notify.notifiarr import build_alert_payload, send_notifiarr

        payload = build_alert_payload(n_ctx, int(channel_id))
        if dry_run:
            logger.info("[DRY-RUN] Would send Notifiarr alert")
        else:
            send_notifiarr(payload, notifiarr_key.get_secret_value())

    apprise_urls = getattr(s, "apprise_urls", None)
    if apprise_urls and apprise_urls.get_secret_value():
        from ynab_tools.notify.apprise import send_alert

        if dry_run:
            logger.info("[DRY-RUN] Would send Apprise alert")
        else:
            send_alert(n_ctx, apprise_urls.get_secret_value())


def _send_update(ctx: object, s: object, *, dry_run: bool) -> None:
    """Send regular update notifications via Notifiarr and Apprise."""
    from ynab_tools.notify.types import NotificationContext

    n_ctx: NotificationContext = ctx  # type: ignore[assignment]

    update_urls = getattr(s, "update_apprise_urls", None)
    if update_urls and update_urls.get_secret_value():
        from ynab_tools.notify.apprise import send_update

        if dry_run:
            logger.info("[DRY-RUN] Would send Apprise update")
        else:
            send_update(n_ctx, update_urls.get_secret_value())

    notifiarr_key = getattr(s, "notifiarr_api_key", None)
    update_channel = getattr(s, "notifiarr_update_channel_id", "")
    if notifiarr_key and notifiarr_key.get_secret_value() and update_channel:
        from ynab_tools.notify.notifiarr import build_update_payload, send_notifiarr

        payload = build_update_payload(n_ctx, int(update_channel))
        if dry_run:
            logger.info("[DRY-RUN] Would send Notifiarr update")
        else:
            send_notifiarr(payload, notifiarr_key.get_secret_value())

    logger.info("Monitor check complete")
