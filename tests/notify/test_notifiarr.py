"""Tests for Notifiarr payload building and sending."""

from __future__ import annotations

from datetime import date

import httpx
import respx

from ynab_tools.notify.notifiarr import (
    NOTIFIARR_BASE_URL,
    build_alert_payload,
    build_update_payload,
    send_notifiarr,
)
from ynab_tools.notify.types import NotificationContext


def _make_ctx(**overrides):
    defaults = {
        "current_balance": 5000.0,
        "accounts": [],
        "min_balance": 300.0,
        "min_date": date(2026, 3, 15),
        "end_date": date(2026, 3, 31),
        "alert_threshold": 500.0,
        "target_threshold": 1000.0,
        "alert_buffer_days": 5,
        "target_buffer_days": 10,
        "avg_daily_expenses": 100.0,
        "buffer_days_remaining": 3.0,
        "shortfall": 200.0,
        "transfer_to_target": 700.0,
        "upcoming_outflows": [],
        "scheduled_inflows": [],
        "cc_payments": {},
    }
    return NotificationContext(**{**defaults, **overrides})


class TestSendNotifiarr:
    @respx.mock
    def test_success(self):
        respx.post(NOTIFIARR_BASE_URL).mock(return_value=httpx.Response(200, json={"result": "success"}))
        assert send_notifiarr({"test": True}, "fake-key") is True

    @respx.mock
    def test_unexpected_response(self):
        respx.post(NOTIFIARR_BASE_URL).mock(
            return_value=httpx.Response(200, json={"result": "error", "details": "bad"})
        )
        assert send_notifiarr({"test": True}, "fake-key") is False

    @respx.mock
    def test_http_error(self):
        respx.post(NOTIFIARR_BASE_URL).mock(return_value=httpx.Response(500, text="Internal Server Error"))
        assert send_notifiarr({"test": True}, "fake-key") is False

    def test_dry_run(self):
        assert send_notifiarr({"test": True}, "fake-key", dry_run=True) is True


class TestBuildAlertPayload:
    def test_structure(self):
        ctx = _make_ctx()
        payload = build_alert_payload(ctx, channel_id=12345)
        assert payload["notification"]["event"] == "ynab-alert"
        assert payload["discord"]["ids"]["channel"] == 12345
        assert "Transfer" in payload["discord"]["text"]["title"]

    def test_negative_balance_red(self):
        ctx = _make_ctx(min_balance=-100.0)
        payload = build_alert_payload(ctx, channel_id=12345)
        assert payload["discord"]["color"] == "E74C3C"

    def test_positive_balance_orange(self):
        ctx = _make_ctx(min_balance=100.0)
        payload = build_alert_payload(ctx, channel_id=12345)
        assert payload["discord"]["color"] == "FF8C00"


class TestBuildUpdatePayload:
    def test_on_track(self):
        ctx = _make_ctx(min_balance=2000.0)
        payload = build_update_payload(ctx, channel_id=12345)
        assert payload["discord"]["color"] == "2ECC71"
        assert "On Track" in payload["discord"]["text"]["title"]

    def test_below_alert(self):
        ctx = _make_ctx(min_balance=100.0)
        payload = build_update_payload(ctx, channel_id=12345)
        assert payload["discord"]["color"] == "E74C3C"
        assert "BELOW ALERT" in payload["discord"]["text"]["title"]

    def test_below_target(self):
        ctx = _make_ctx(min_balance=600.0)
        payload = build_update_payload(ctx, channel_id=12345)
        assert payload["discord"]["color"] == "F39C12"
        assert "Below Target" in payload["discord"]["text"]["title"]


class TestBuildAmazonSyncPayload:
    def _build(self, **overrides):
        from ynab_tools.notify.notifiarr import build_amazon_sync_payload

        defaults = {
            "matched": 3,
            "updated": 3,
            "skipped": 2,
            "errors": (),
            "ynab_count": 5,
            "amazon_count": 10,
            "channel_id": 12345,
        }
        return build_amazon_sync_payload(**{**defaults, **overrides})

    def test_structure(self):
        payload = self._build()
        assert payload["notification"]["event"] == "ynab-amazon-sync"
        assert payload["discord"]["ids"]["channel"] == 12345

    def test_updated_green(self):
        payload = self._build(updated=3)
        assert payload["discord"]["color"] == "2ECC71"
        assert "Updated" in payload["discord"]["text"]["title"]

    def test_no_changes_blue(self):
        payload = self._build(matched=0, updated=0, skipped=5)
        assert payload["discord"]["color"] == "3498DB"
        assert "No Changes" in payload["discord"]["text"]["title"]

    def test_errors_red(self):
        payload = self._build(errors=("Update failed for txn-1: timeout",))
        assert payload["discord"]["color"] == "E74C3C"
        assert "Errors" in payload["discord"]["text"]["title"]

    def test_errors_in_fields(self):
        payload = self._build(errors=("err1", "err2"))
        error_fields = [f for f in payload["discord"]["text"]["fields"] if f["title"] == "Errors"]
        assert len(error_fields) == 1
        assert "err1" in error_fields[0]["text"]

    def test_description_includes_counts(self):
        payload = self._build(matched=3, ynab_count=5, amazon_count=10)
        desc = payload["discord"]["text"]["description"]
        assert "3" in desc
        assert "5" in desc
        assert "10" in desc
