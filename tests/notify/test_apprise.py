"""Tests for Apprise notification message building."""

from __future__ import annotations

from datetime import date

from ynab_tools.core.models import CreditCardPayment, TransactionOccurrence
from ynab_tools.notify.apprise import _build_alert_message, _build_update_message
from ynab_tools.notify.types import InflowSummary, NotificationContext


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


class TestBuildAlertMessage:
    def test_title_includes_transfer(self):
        ctx = _make_ctx()
        title, _body = _build_alert_message(ctx)
        assert "$700" in title
        assert "ynab-tools" in title

    def test_body_includes_balances(self):
        ctx = _make_ctx()
        _title, body = _build_alert_message(ctx)
        assert "$5,000" in body
        assert "$300" in body
        assert "$200" in body  # shortfall

    def test_body_includes_inflows(self):
        inflows = [InflowSummary(payee="Paycheck", amount=2000.0, count=2)]
        ctx = _make_ctx(scheduled_inflows=inflows)
        _title, body = _build_alert_message(ctx)
        assert "Paycheck" in body
        assert "(2x)" in body

    def test_body_includes_outflows(self):
        txns = [
            TransactionOccurrence(
                date=date(2026, 3, 15),
                amount=-500.0,
                payee="Rent",
                transfer_account_id=None,
                frequency="monthly",
                label="Rent",
            )
        ]
        ctx = _make_ctx(upcoming_outflows=txns)
        _title, body = _build_alert_message(ctx)
        assert "Rent" in body
        assert "Mar 15" in body

    def test_body_includes_cc_payments(self):
        cc = {"cc1": CreditCardPayment(name="Chase", amount=500.0, source="statement", scheduled=True)}
        ctx = _make_ctx(cc_payments=cc)
        _title, body = _build_alert_message(ctx)
        assert "Chase" in body
        assert "(scheduled)" in body


class TestBuildUpdateMessage:
    def test_on_track(self):
        ctx = _make_ctx(min_balance=2000.0)
        title, _body = _build_update_message(ctx)
        assert "On Track" in title

    def test_below_alert(self):
        ctx = _make_ctx(min_balance=100.0)
        title, _body = _build_update_message(ctx)
        assert "BELOW ALERT" in title

    def test_below_target(self):
        ctx = _make_ctx(min_balance=600.0)
        title, _body = _build_update_message(ctx)
        assert "Below Target" in title

    def test_body_includes_date_range(self):
        ctx = _make_ctx(min_balance=2000.0)
        _title, body = _build_update_message(ctx)
        assert "Mar 31, 2026" in body

    def test_body_includes_cc_unscheduled(self):
        cc = {"cc1": CreditCardPayment(name="Amex", amount=300.0, source="category_balance", scheduled=False)}
        ctx = _make_ctx(cc_payments=cc)
        _title, body = _build_update_message(ctx)
        assert "Amex" in body
        assert "(unscheduled)" in body
