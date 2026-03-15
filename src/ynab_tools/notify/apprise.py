"""Apprise multi-service notification sender."""

from __future__ import annotations

import apprise
from loguru import logger

from ynab_tools import APP_NAME
from ynab_tools.notify.types import NotificationContext


def _build_notifier(urls_str: str) -> apprise.Apprise:
    """Build an Apprise notifier from a comma-separated URL string."""
    notifier = apprise.Apprise()
    for url in urls_str.split(","):
        url = url.strip()
        if url:
            notifier.add(url)
    return notifier


def _fmt(amount: float) -> str:
    """Format dollars without decimals for notification text."""
    if amount < 0:
        return f"-${abs(amount):,.0f}"
    return f"${amount:,.0f}"


def _build_alert_message(ctx: NotificationContext) -> tuple[str, str]:
    """Build title and body for an alert notification."""
    transfer = ctx.transfer_to_target
    min_bal = ctx.min_balance
    daily = ctx.avg_daily_expenses
    min_date_str = ctx.min_date.strftime("%b %d")

    title = f"{APP_NAME}: Transfer {_fmt(transfer)} to checking"

    lines = [
        f"After all scheduled bills and CC payments, checking bottoms out at "
        f"{_fmt(min_bal)} on {min_date_str} — "
        f"that's {_fmt(ctx.shortfall)} below the alert cushion.",
        "",
        f"Balance now: {_fmt(ctx.current_balance)}",
        f"Lowest point: {_fmt(min_bal)} on {min_date_str}",
        f"Avg daily spend: ${daily:,.0f}/day (13-mo avg)",
        f"Alert cushion: {_fmt(ctx.alert_threshold)} (${daily:,.0f}/day x {ctx.alert_buffer_days}d)",
        f"Target cushion: {_fmt(ctx.target_threshold)} (${daily:,.0f}/day x {ctx.target_buffer_days}d)",
    ]

    if ctx.scheduled_inflows:
        lines.append("")
        lines.append("Scheduled income & transfers in:")
        for inflow in ctx.scheduled_inflows:
            if inflow.count > 1:
                lines.append(f"  {inflow.payee}: {_fmt(inflow.amount)} ({inflow.count}x)")
            else:
                lines.append(f"  {inflow.payee}: {_fmt(inflow.amount)}")

    if ctx.upcoming_outflows:
        lines.append("")
        lines.append("Upcoming bills:")
        for t in ctx.upcoming_outflows:
            lines.append(f"  {t.date.strftime('%b %d')}: {t.payee}  {_fmt(t.amount)}")

    if ctx.cc_payments:
        lines.append("")
        lines.append("CC payments:")
        for payment in ctx.cc_payments.values():
            tag = " (scheduled)" if payment.scheduled else " (unscheduled)"
            lines.append(f"  {payment.name}: {_fmt(payment.amount)}{tag}")

    lines.append("")
    lines.append(
        f"Action: Transfer {_fmt(transfer)} from HYSA -> checking before "
        f"{min_date_str} to maintain {ctx.target_buffer_days}-day cushion."
    )

    return title, "\n".join(lines)


def _build_update_message(ctx: NotificationContext) -> tuple[str, str]:
    """Build title and body for a routine update notification."""
    min_bal = ctx.min_balance

    if min_bal < ctx.alert_threshold:
        status = "BELOW ALERT"
    elif min_bal < ctx.target_threshold:
        status = "Below Target"
    else:
        status = "On Track"

    title = f"{APP_NAME}: Checking \u2014 {status}"

    buf_days = ctx.buffer_days_remaining
    buf_text = f"~{buf_days:.0f} days" if buf_days < 999 else "999+ days"
    daily = ctx.avg_daily_expenses
    min_date_str = ctx.min_date.strftime("%b %d")

    lines = [
        f"After all scheduled bills and CC payments, checking bottoms out at "
        f"{_fmt(min_bal)} on {min_date_str} \u2014 that covers {buf_text} of spending.",
        "",
        f"Balance now: {_fmt(ctx.current_balance)}",
        f"Lowest point: {_fmt(min_bal)} on {min_date_str}",
        f"Avg daily spend: ${daily:,.0f}/day (13-mo avg)",
        f"Alert cushion: {_fmt(ctx.alert_threshold)} (${daily:,.0f}/day x {ctx.alert_buffer_days}d)",
        f"Target cushion: {_fmt(ctx.target_threshold)} (${daily:,.0f}/day x {ctx.target_buffer_days}d)",
    ]

    if ctx.scheduled_inflows:
        lines.append("")
        lines.append("Scheduled income & transfers in:")
        for inflow in ctx.scheduled_inflows:
            if inflow.count > 1:
                lines.append(f"  {inflow.payee}: {_fmt(inflow.amount)} ({inflow.count}x)")
            else:
                lines.append(f"  {inflow.payee}: {_fmt(inflow.amount)}")

    if ctx.cc_payments:
        lines.append("")
        lines.append("CC payments:")
        for payment in ctx.cc_payments.values():
            tag = " (scheduled)" if payment.scheduled else " (unscheduled)"
            lines.append(f"  {payment.name}: {_fmt(payment.amount)}{tag}")

    lines.append(f"Through {ctx.end_date.strftime('%b %d, %Y')}")

    return title, "\n".join(lines)


def send_alert(ctx: NotificationContext, apprise_urls: str) -> bool:
    """Send a below-threshold alert via Apprise.

    Returns True on success, False on failure.
    """
    title, body = _build_alert_message(ctx)
    notifier = _build_notifier(apprise_urls)
    notify_type = apprise.NotifyType.WARNING if ctx.min_balance < 0 else apprise.NotifyType.INFO

    result = notifier.notify(title=title, body=body, notify_type=notify_type)
    if result:
        logger.info("Alert notification sent via Apprise")
    else:
        logger.error("Failed to send alert via Apprise")
    return bool(result)


def send_update(ctx: NotificationContext, apprise_urls: str) -> bool:
    """Send a routine balance update via Apprise.

    Returns True on success, False on failure.
    """
    title, body = _build_update_message(ctx)
    notifier = _build_notifier(apprise_urls)
    notify_type = apprise.NotifyType.WARNING if ctx.min_balance < ctx.alert_threshold else apprise.NotifyType.SUCCESS

    result = notifier.notify(title=title, body=body, notify_type=notify_type)
    if result:
        logger.info("Update notification sent via Apprise")
    else:
        logger.error("Failed to send update via Apprise")
    return bool(result)
