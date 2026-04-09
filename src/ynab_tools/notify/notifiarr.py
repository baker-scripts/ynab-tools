"""Notifiarr passthrough API — Discord embeds for balance alerts and updates."""

from __future__ import annotations

import json

import httpx
from loguru import logger

from ynab_tools import APP_NAME, USER_AGENT, __version__
from ynab_tools.core.client import sanitize_error
from ynab_tools.notify.types import NotificationContext

NOTIFIARR_BASE_URL = "https://notifiarr.com/api/v1/notification/passthrough"


def _fmt_whole_dollars(amount: float) -> str:
    """Format dollars without decimals for notification display."""
    if amount < 0:
        return f"-${abs(amount):,.0f}"
    return f"${amount:,.0f}"


def send_notifiarr(
    payload: dict,
    api_key: str,
    *,
    dry_run: bool = False,
    timeout: int = 30,
) -> bool:
    """POST a JSON payload to the Notifiarr passthrough API.

    Returns True on success, False on failure.
    """
    if dry_run:
        logger.info("[DRY-RUN] Notifiarr payload:\n{}", json.dumps(payload, indent=2, default=str))
        return True

    try:
        resp = httpx.post(
            NOTIFIARR_BASE_URL,
            json=payload,
            headers={
                "Accept": "text/plain",
                "User-Agent": USER_AGENT,
                "x-api-key": api_key,
            },
            timeout=timeout,
        )
        resp.raise_for_status()
        result = resp.json()
        if result.get("result") == "success":
            logger.info("Notifiarr passthrough sent successfully")
            return True
        logger.warning("Notifiarr unexpected response: {}", resp.text[:200])
        return False
    except httpx.HTTPStatusError as e:
        body = e.response.text
        logger.error("Notifiarr API error ({}): {}", e.response.status_code, sanitize_error(body))
        return False
    except (httpx.TimeoutException, httpx.ConnectError) as e:
        logger.error("Notifiarr network error: {}", e)
        return False


def _inflow_lines(ctx: NotificationContext) -> list[str]:
    """Build inflow display lines from context."""
    lines = []
    for inflow in ctx.scheduled_inflows:
        if inflow.count > 1:
            lines.append(f"{inflow.payee}: {_fmt_whole_dollars(inflow.amount)} ({inflow.count}x)")
        else:
            lines.append(f"{inflow.payee}: {_fmt_whole_dollars(inflow.amount)}")
    return lines


def _cc_lines(ctx: NotificationContext) -> list[str]:
    """Build CC payment display lines from context."""
    lines = []
    for payment in ctx.cc_payments.values():
        tag = " *(scheduled)*" if payment.scheduled else " *(unscheduled)*"
        lines.append(f"{payment.name}: {_fmt_whole_dollars(payment.amount)}{tag}")
    return lines


def build_alert_payload(ctx: NotificationContext, channel_id: int) -> dict:
    """Build a Notifiarr passthrough payload for a balance alert."""
    min_bal = ctx.min_balance
    shortfall = ctx.shortfall
    transfer = ctx.transfer_to_target

    color = "E74C3C" if min_bal < 0 else "FF8C00"
    min_date_str = ctx.min_date.strftime("%b %d")
    daily_text = f"${ctx.avg_daily_expenses:,.0f}/day"

    description = (
        f"After all scheduled bills and CC payments, checking will bottom out at "
        f"**{_fmt_whole_dollars(min_bal)}** on **{min_date_str}** — "
        f"that's {_fmt_whole_dollars(shortfall)} less than the {ctx.alert_buffer_days}-day "
        f"spending cushion ({_fmt_whole_dollars(ctx.alert_threshold)})."
    )

    fields = [
        {"title": "Balance Now", "text": _fmt_whole_dollars(ctx.current_balance), "inline": True},
        {"title": "Lowest Point", "text": f"{_fmt_whole_dollars(min_bal)} on {min_date_str}", "inline": True},
        {"title": "Below Alert By", "text": _fmt_whole_dollars(shortfall), "inline": True},
        {
            "title": f"Alert Cushion ({ctx.alert_buffer_days}d spend)",
            "text": f"{_fmt_whole_dollars(ctx.alert_threshold)} ({daily_text} x {ctx.alert_buffer_days}d)",
            "inline": True,
        },
        {
            "title": f"Target Cushion ({ctx.target_buffer_days}d spend)",
            "text": f"{_fmt_whole_dollars(ctx.target_threshold)} ({daily_text} x {ctx.target_buffer_days}d)",
            "inline": True,
        },
        {"title": "Transfer Needed", "text": _fmt_whole_dollars(transfer), "inline": True},
    ]

    inflows = _inflow_lines(ctx)
    if inflows:
        fields.append({"title": "Scheduled Income & Transfers In", "text": "\n".join(inflows), "inline": False})

    if ctx.upcoming_outflows:
        outflow_lines = [
            f"{t.date.strftime('%b %d')}: {t.payee}  {_fmt_whole_dollars(t.amount)}" for t in ctx.upcoming_outflows
        ]
        fields.append({"title": "Upcoming Bills", "text": "\n".join(outflow_lines), "inline": False})

    cc = _cc_lines(ctx)
    if cc:
        fields.append({"title": "CC Payments", "text": "\n".join(cc), "inline": False})

    action = (
        f"Transfer **{_fmt_whole_dollars(transfer)}** from HYSA -> checking before "
        f"{min_date_str} to maintain {ctx.target_buffer_days}-day cushion."
    )
    fields.append({"title": "Action", "text": action, "inline": False})

    return {
        "notification": {"update": True, "name": APP_NAME, "event": "ynab-alert"},
        "discord": {
            "color": color,
            "text": {
                "title": f"Transfer {_fmt_whole_dollars(transfer)} to Checking",
                "description": description,
                "fields": fields,
                "footer": f"{APP_NAME} v{__version__} \u2022 Through {ctx.end_date.strftime('%b %d, %Y')}",
            },
            "ids": {"channel": channel_id},
        },
    }


def build_amazon_sync_payload(
    matched: int,
    updated: int,
    skipped: int,
    errors: tuple[str, ...],
    ynab_count: int,
    amazon_count: int,
    channel_id: int,
) -> dict:
    """Build a Notifiarr passthrough payload for an Amazon sync result."""
    has_errors = len(errors) > 0

    if has_errors:
        color, status = "E74C3C", "Errors"
    elif updated > 0:
        color, status = "2ECC71", "Updated"
    else:
        color, status = "3498DB", "No Changes"

    description = (
        f"Matched **{matched}** of **{ynab_count}** YNAB transactions against **{amazon_count}** Amazon orders."
    )

    fields = [
        {"title": "Matched", "text": str(matched), "inline": True},
        {"title": "Updated", "text": str(updated), "inline": True},
        {"title": "Skipped", "text": str(skipped), "inline": True},
    ]

    if errors:
        error_text = "\n".join(errors[:5])
        if len(errors) > 5:
            error_text += f"\n...and {len(errors) - 5} more"
        fields.append({"title": "Errors", "text": error_text, "inline": False})

    return {
        "notification": {"update": True, "name": APP_NAME, "event": "ynab-amazon-sync"},
        "discord": {
            "color": color,
            "text": {
                "title": f"Amazon Sync \u2014 {status}",
                "description": description,
                "fields": fields,
                "footer": f"{APP_NAME} v{__version__}",
            },
            "ids": {"channel": channel_id},
        },
    }


def build_update_payload(ctx: NotificationContext, channel_id: int) -> dict:
    """Build a Notifiarr passthrough payload for a routine balance update."""
    min_bal = ctx.min_balance

    if min_bal < ctx.alert_threshold:
        color, status = "E74C3C", "BELOW ALERT"
    elif min_bal < ctx.target_threshold:
        color, status = "F39C12", "Below Target"
    else:
        color, status = "2ECC71", "On Track"

    buf_days = ctx.buffer_days_remaining
    buf_text = f"~{buf_days:.0f} days of spending" if buf_days < 999 else "999+ days"
    min_date_str = ctx.min_date.strftime("%b %d")
    daily_text = f"${ctx.avg_daily_expenses:,.0f}/day"

    description = (
        f"After all scheduled bills and CC payments clear, checking bottoms out at "
        f"**{_fmt_whole_dollars(min_bal)}** on **{min_date_str}** — "
        f"that covers {buf_text}."
    )

    fields = [
        {"title": "Balance Now", "text": _fmt_whole_dollars(ctx.current_balance), "inline": True},
        {"title": "Lowest Point", "text": f"{_fmt_whole_dollars(min_bal)} on {min_date_str}", "inline": True},
        {"title": "Covers", "text": buf_text, "inline": True},
        {
            "title": f"Alert Cushion ({ctx.alert_buffer_days}d)",
            "text": f"{_fmt_whole_dollars(ctx.alert_threshold)} ({daily_text} x {ctx.alert_buffer_days}d)",
            "inline": True,
        },
        {
            "title": f"Target Cushion ({ctx.target_buffer_days}d)",
            "text": f"{_fmt_whole_dollars(ctx.target_threshold)} ({daily_text} x {ctx.target_buffer_days}d)",
            "inline": True,
        },
        {"title": "Avg Daily Spend", "text": f"{daily_text} (13-mo avg)", "inline": True},
    ]

    inflows = _inflow_lines(ctx)
    if inflows:
        fields.append({"title": "Scheduled Income & Transfers In", "text": "\n".join(inflows), "inline": False})

    cc = _cc_lines(ctx)
    if cc:
        fields.append({"title": "CC Payments", "text": "\n".join(cc), "inline": False})

    return {
        "notification": {"update": True, "name": APP_NAME, "event": "ynab-update"},
        "discord": {
            "color": color,
            "text": {
                "title": f"Checking \u2014 {status}",
                "description": description,
                "fields": fields,
                "footer": f"{APP_NAME} v{__version__} \u2022 Through {ctx.end_date.strftime('%b %d, %Y')}",
            },
            "ids": {"channel": channel_id},
        },
    }
