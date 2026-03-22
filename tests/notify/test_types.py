"""Tests for notification context building."""

from __future__ import annotations

from datetime import date

from ynab_tools.core.models import CreditCardPayment, TransactionOccurrence
from ynab_tools.notify.types import build_notification_context


def _make_txn(**overrides):
    defaults = {
        "date": date(2026, 3, 15),
        "amount": -500.0,
        "payee": "Rent",
        "transfer_account_id": None,
        "frequency": "monthly",
        "label": "Rent (monthly)",
    }
    return TransactionOccurrence(**{**defaults, **overrides})


class TestBuildNotificationContext:
    def test_shortfall_calculated(self):
        ctx = build_notification_context(
            current_balance=5000.0,
            accounts=[],
            min_balance=300.0,
            min_date=date(2026, 3, 15),
            end_date=date(2026, 3, 31),
            alert_threshold=500.0,
            target_threshold=1000.0,
            alert_buffer_days=5,
            target_buffer_days=10,
            avg_daily_expenses=100.0,
            transactions=[],
            cc_payments={},
            today=date(2026, 3, 1),
        )
        assert ctx.shortfall == 200.0
        assert ctx.transfer_to_target == 700.0

    def test_no_shortfall_when_above(self):
        ctx = build_notification_context(
            current_balance=5000.0,
            accounts=[],
            min_balance=2000.0,
            min_date=date(2026, 3, 15),
            end_date=date(2026, 3, 31),
            alert_threshold=500.0,
            target_threshold=1000.0,
            alert_buffer_days=5,
            target_buffer_days=10,
            avg_daily_expenses=100.0,
            transactions=[],
            cc_payments={},
            today=date(2026, 3, 1),
        )
        assert ctx.shortfall == 0.0
        assert ctx.transfer_to_target == 0.0

    def test_buffer_days(self):
        ctx = build_notification_context(
            current_balance=5000.0,
            accounts=[],
            min_balance=1000.0,
            min_date=date(2026, 3, 15),
            end_date=date(2026, 3, 31),
            alert_threshold=500.0,
            target_threshold=1000.0,
            alert_buffer_days=5,
            target_buffer_days=10,
            avg_daily_expenses=100.0,
            transactions=[],
            cc_payments={},
            today=date(2026, 3, 1),
        )
        assert ctx.buffer_days_remaining == 10.0

    def test_zero_expenses_buffer(self):
        ctx = build_notification_context(
            current_balance=5000.0,
            accounts=[],
            min_balance=1000.0,
            min_date=date(2026, 3, 15),
            end_date=date(2026, 3, 31),
            alert_threshold=0.0,
            target_threshold=0.0,
            alert_buffer_days=5,
            target_buffer_days=10,
            avg_daily_expenses=0.0,
            transactions=[],
            cc_payments={},
            today=date(2026, 3, 1),
        )
        assert ctx.buffer_days_remaining == 0.0

    def test_upcoming_outflows_top5(self):
        txns = [_make_txn(date=date(2026, 3, d), amount=-d * 100, payee=f"Bill{d}") for d in range(1, 8)]
        ctx = build_notification_context(
            current_balance=5000.0,
            accounts=[],
            min_balance=1000.0,
            min_date=date(2026, 3, 15),
            end_date=date(2026, 3, 31),
            alert_threshold=500.0,
            target_threshold=1000.0,
            alert_buffer_days=5,
            target_buffer_days=10,
            avg_daily_expenses=100.0,
            transactions=txns,
            cc_payments={},
            today=date(2026, 3, 1),
        )
        assert len(ctx.upcoming_outflows) == 5
        # Sorted by amount (most negative first)
        assert ctx.upcoming_outflows[0].amount <= ctx.upcoming_outflows[1].amount

    def test_inflows_aggregated(self):
        txns = [
            _make_txn(date=date(2026, 3, 5), amount=2000.0, payee="Paycheck"),
            _make_txn(date=date(2026, 3, 20), amount=2000.0, payee="Paycheck"),
            _make_txn(date=date(2026, 3, 10), amount=500.0, payee="Side Gig"),
        ]
        ctx = build_notification_context(
            current_balance=5000.0,
            accounts=[],
            min_balance=1000.0,
            min_date=date(2026, 3, 15),
            end_date=date(2026, 3, 31),
            alert_threshold=500.0,
            target_threshold=1000.0,
            alert_buffer_days=5,
            target_buffer_days=10,
            avg_daily_expenses=100.0,
            transactions=txns,
            cc_payments={},
            today=date(2026, 3, 1),
        )
        paycheck = next(i for i in ctx.scheduled_inflows if i.payee == "Paycheck")
        assert paycheck.amount == 4000.0
        assert paycheck.count == 2
        side = next(i for i in ctx.scheduled_inflows if i.payee == "Side Gig")
        assert side.amount == 500.0
        assert side.count == 1

    def test_cc_transfer_excluded_from_upcoming_outflows(self):
        """CC payment transfers already shown in CC Payments should not also appear in Upcoming Bills."""
        cc_id = "chase-cc-id"
        txns = [
            _make_txn(date=date(2026, 3, 3), amount=-500.0, payee="Transfer : Chase", transfer_account_id=cc_id),
            _make_txn(date=date(2026, 3, 5), amount=-200.0, payee="Electric Bill", transfer_account_id=None),
        ]
        cc = {cc_id: CreditCardPayment(name="Chase", amount=500.0, source="statement")}
        ctx = build_notification_context(
            current_balance=5000.0,
            accounts=[],
            min_balance=1000.0,
            min_date=date(2026, 3, 15),
            end_date=date(2026, 3, 31),
            alert_threshold=500.0,
            target_threshold=1000.0,
            alert_buffer_days=5,
            target_buffer_days=10,
            avg_daily_expenses=100.0,
            transactions=txns,
            cc_payments=cc,
            covered_cc_ids={cc_id},
            today=date(2026, 3, 1),
        )
        assert len(ctx.upcoming_outflows) == 1
        assert ctx.upcoming_outflows[0].payee == "Electric Bill"
        assert ctx.cc_payments[cc_id].scheduled is True

    def test_uncovered_cc_transfer_still_in_upcoming(self):
        """Transfers to CCs without scheduled payments should still appear in upcoming."""
        cc_id = "amex-cc-id"
        txns = [
            _make_txn(date=date(2026, 3, 3), amount=-300.0, payee="Transfer : Amex", transfer_account_id=cc_id),
        ]
        ctx = build_notification_context(
            current_balance=5000.0,
            accounts=[],
            min_balance=1000.0,
            min_date=date(2026, 3, 15),
            end_date=date(2026, 3, 31),
            alert_threshold=500.0,
            target_threshold=1000.0,
            alert_buffer_days=5,
            target_buffer_days=10,
            avg_daily_expenses=100.0,
            transactions=txns,
            cc_payments={},
            covered_cc_ids=set(),
            today=date(2026, 3, 1),
        )
        assert len(ctx.upcoming_outflows) == 1
        assert ctx.upcoming_outflows[0].payee == "Transfer : Amex"

    def test_cc_payments_tagged(self):
        cc = {
            "cc1": CreditCardPayment(name="Chase", amount=500.0, source="statement"),
            "cc2": CreditCardPayment(name="Amex", amount=300.0, source="category_balance"),
        }
        ctx = build_notification_context(
            current_balance=5000.0,
            accounts=[],
            min_balance=1000.0,
            min_date=date(2026, 3, 15),
            end_date=date(2026, 3, 31),
            alert_threshold=500.0,
            target_threshold=1000.0,
            alert_buffer_days=5,
            target_buffer_days=10,
            avg_daily_expenses=100.0,
            transactions=[],
            cc_payments=cc,
            covered_cc_ids={"cc1"},
            today=date(2026, 3, 1),
        )
        assert ctx.cc_payments["cc1"].scheduled is True
        assert ctx.cc_payments["cc2"].scheduled is False
