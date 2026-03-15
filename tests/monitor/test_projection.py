"""Tests for day-by-day balance projection."""

from __future__ import annotations

from datetime import date

from ynab_tools.core.models import CreditCardPayment, TransactionOccurrence
from ynab_tools.monitor.projection import project_minimum_balance


class TestProjectMinimumBalance:
    def test_no_transactions(self):
        min_bal, min_date = project_minimum_balance(
            current_balance=5000.0,
            scheduled_transactions=[],
            cc_payments={},
            end_date=date(2026, 3, 31),
            today=date(2026, 3, 1),
        )
        assert min_bal == 5000.0
        assert min_date == date(2026, 3, 1)

    def test_single_outflow(self):
        txns = [
            TransactionOccurrence(
                date=date(2026, 3, 15),
                amount=-1000.0,
                payee="Rent",
                transfer_account_id=None,
                frequency="monthly",
                label="Rent (monthly)",
            )
        ]
        min_bal, min_date = project_minimum_balance(
            current_balance=5000.0,
            scheduled_transactions=txns,
            cc_payments={},
            end_date=date(2026, 3, 31),
            today=date(2026, 3, 1),
        )
        assert min_bal == 4000.0
        assert min_date == date(2026, 3, 15)

    def test_inflow_recovers(self):
        txns = [
            TransactionOccurrence(
                date=date(2026, 3, 10),
                amount=-3000.0,
                payee="Rent",
                transfer_account_id=None,
                frequency="monthly",
                label="Rent",
            ),
            TransactionOccurrence(
                date=date(2026, 3, 15),
                amount=4000.0,
                payee="Paycheck",
                transfer_account_id=None,
                frequency="monthly",
                label="Paycheck",
            ),
        ]
        min_bal, min_date = project_minimum_balance(
            current_balance=5000.0,
            scheduled_transactions=txns,
            cc_payments={},
            end_date=date(2026, 3, 31),
            today=date(2026, 3, 1),
        )
        assert min_bal == 2000.0
        assert min_date == date(2026, 3, 10)

    def test_unscheduled_cc_applied_day_1(self):
        cc = {
            "cc1": CreditCardPayment(name="Chase", amount=500.0, source="statement"),
        }
        min_bal, _ = project_minimum_balance(
            current_balance=5000.0,
            scheduled_transactions=[],
            cc_payments=cc,
            end_date=date(2026, 3, 31),
            today=date(2026, 3, 1),
            covered_cc_ids=set(),
        )
        assert min_bal == 4500.0

    def test_covered_cc_not_deducted(self):
        cc = {
            "cc1": CreditCardPayment(name="Chase", amount=500.0, source="statement"),
        }
        min_bal, _ = project_minimum_balance(
            current_balance=5000.0,
            scheduled_transactions=[],
            cc_payments=cc,
            end_date=date(2026, 3, 31),
            today=date(2026, 3, 1),
            covered_cc_ids={"cc1"},
        )
        assert min_bal == 5000.0

    def test_multiple_transactions_same_day(self):
        txns = [
            TransactionOccurrence(
                date=date(2026, 3, 15),
                amount=-1000.0,
                payee="Rent",
                transfer_account_id=None,
                frequency="monthly",
                label="Rent",
            ),
            TransactionOccurrence(
                date=date(2026, 3, 15),
                amount=-500.0,
                payee="Insurance",
                transfer_account_id=None,
                frequency="monthly",
                label="Insurance",
            ),
        ]
        min_bal, _ = project_minimum_balance(
            current_balance=5000.0,
            scheduled_transactions=txns,
            cc_payments={},
            end_date=date(2026, 3, 31),
            today=date(2026, 3, 1),
        )
        assert min_bal == 3500.0
