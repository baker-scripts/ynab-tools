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
    from ynab_tools.notify.types import build_notification_context

    ctx = build_notification_context(result, s)  # type: ignore[arg-type]

    # Alert notification (Notifiarr + Apprise)
    if result.is_alert:  # type: ignore[attr-defined]
        _send_alert(ctx, s, dry_run=dry_run)

    # Regular update notification
    _send_update(ctx, s, dry_run=dry_run)


def _send_alert(ctx: object, s: object, *, dry_run: bool) -> None:
    """Send alert notifications via Notifiarr and Apprise."""
    notifiarr_key = getattr(s, "notifiarr_api_key", None)
    if notifiarr_key and notifiarr_key.get_secret_value():
        from ynab_tools.notify.notifiarr import build_alert_payload, send_notifiarr

        payload = build_alert_payload(ctx)  # type: ignore[arg-type]
        send_notifiarr(
            notifiarr_key.get_secret_value(),
            payload,
            channel_id=getattr(s, "notifiarr_channel_id", ""),
            dry_run=dry_run,
        )

    apprise_urls = getattr(s, "apprise_urls", None)
    if apprise_urls and apprise_urls.get_secret_value():
        from ynab_tools.notify.apprise import build_alert_message, send_apprise

        title, body = build_alert_message(ctx)  # type: ignore[arg-type]
        send_apprise(apprise_urls.get_secret_value(), title=title, body=body, dry_run=dry_run)


def _send_update(ctx: object, s: object, *, dry_run: bool) -> None:
    """Send regular update notifications via Notifiarr and Apprise."""
    update_urls = getattr(s, "update_apprise_urls", None)
    if update_urls and update_urls.get_secret_value():
        from ynab_tools.notify.apprise import build_update_message, send_apprise

        title, body = build_update_message(ctx)  # type: ignore[arg-type]
        send_apprise(update_urls.get_secret_value(), title=title, body=body, dry_run=dry_run)

    notifiarr_key = getattr(s, "notifiarr_api_key", None)
    update_channel = getattr(s, "notifiarr_update_channel_id", "")
    if notifiarr_key and notifiarr_key.get_secret_value() and update_channel:
        from ynab_tools.notify.notifiarr import build_update_payload, send_notifiarr

        payload = build_update_payload(ctx)  # type: ignore[arg-type]
        send_notifiarr(
            notifiarr_key.get_secret_value(),
            payload,
            channel_id=update_channel,
            dry_run=dry_run,
        )

    logger.info("Monitor check complete")
