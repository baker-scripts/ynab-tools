"""Tests for recurrence expansion — all 13 YNAB frequency types."""

from __future__ import annotations

from datetime import date


from ynab_tools.monitor.scheduler import _add_months, _expand_occurrences, expand_scheduled_transactions


class TestAddMonths:
    def test_simple(self):
        assert _add_months(date(2026, 1, 15), 1) == date(2026, 2, 15)

    def test_year_boundary(self):
        assert _add_months(date(2025, 12, 1), 1) == date(2026, 1, 1)

    def test_clamp_day(self):
        # Jan 31 + 1 month → Feb 28 (non-leap)
        assert _add_months(date(2025, 1, 31), 1) == date(2025, 2, 28)

    def test_leap_year(self):
        assert _add_months(date(2024, 1, 29), 1) == date(2024, 2, 29)

    def test_negative(self):
        assert _add_months(date(2026, 3, 15), -1) == date(2026, 2, 15)

    def test_multiple_months(self):
        assert _add_months(date(2026, 1, 1), 6) == date(2026, 7, 1)


class TestExpandOccurrences:
    def test_never_in_range(self):
        result = _expand_occurrences(date(2026, 3, 15), "never", date(2026, 3, 1), date(2026, 3, 31))
        assert result == [date(2026, 3, 15)]

    def test_never_out_of_range(self):
        result = _expand_occurrences(date(2026, 4, 15), "never", date(2026, 3, 1), date(2026, 3, 31))
        assert result == []

    def test_daily(self):
        result = _expand_occurrences(date(2026, 3, 1), "daily", date(2026, 3, 1), date(2026, 3, 3))
        assert result == [date(2026, 3, 1), date(2026, 3, 2), date(2026, 3, 3)]

    def test_weekly(self):
        result = _expand_occurrences(date(2026, 3, 1), "weekly", date(2026, 3, 1), date(2026, 3, 31))
        assert result == [date(2026, 3, 1), date(2026, 3, 8), date(2026, 3, 15), date(2026, 3, 22), date(2026, 3, 29)]

    def test_every_other_week(self):
        result = _expand_occurrences(date(2026, 3, 1), "everyOtherWeek", date(2026, 3, 1), date(2026, 3, 31))
        assert result == [date(2026, 3, 1), date(2026, 3, 15), date(2026, 3, 29)]

    def test_every_4_weeks(self):
        result = _expand_occurrences(date(2026, 3, 1), "every4Weeks", date(2026, 3, 1), date(2026, 4, 30))
        assert result == [date(2026, 3, 1), date(2026, 3, 29), date(2026, 4, 26)]

    def test_monthly(self):
        result = _expand_occurrences(date(2026, 1, 15), "monthly", date(2026, 1, 1), date(2026, 4, 30))
        assert result == [date(2026, 1, 15), date(2026, 2, 15), date(2026, 3, 15), date(2026, 4, 15)]

    def test_every_other_month(self):
        result = _expand_occurrences(date(2026, 1, 15), "everyOtherMonth", date(2026, 1, 1), date(2026, 6, 30))
        assert result == [date(2026, 1, 15), date(2026, 3, 15), date(2026, 5, 15)]

    def test_every_3_months(self):
        result = _expand_occurrences(date(2026, 1, 1), "every3Months", date(2026, 1, 1), date(2026, 12, 31))
        assert result == [date(2026, 1, 1), date(2026, 4, 1), date(2026, 7, 1), date(2026, 10, 1)]

    def test_every_4_months(self):
        result = _expand_occurrences(date(2026, 1, 1), "every4Months", date(2026, 1, 1), date(2026, 12, 31))
        assert result == [date(2026, 1, 1), date(2026, 5, 1), date(2026, 9, 1)]

    def test_twice_a_month(self):
        result = _expand_occurrences(date(2026, 3, 1), "twiceAMonth", date(2026, 3, 1), date(2026, 3, 31))
        assert date(2026, 3, 1) in result
        assert date(2026, 3, 16) in result
        assert len(result) == 2

    def test_twice_a_year(self):
        result = _expand_occurrences(date(2026, 1, 1), "twiceAYear", date(2026, 1, 1), date(2026, 12, 31))
        assert result == [date(2026, 1, 1), date(2026, 7, 1)]

    def test_yearly(self):
        result = _expand_occurrences(date(2026, 6, 15), "yearly", date(2026, 1, 1), date(2027, 12, 31))
        assert result == [date(2026, 6, 15), date(2027, 6, 15)]

    def test_every_other_year(self):
        result = _expand_occurrences(date(2026, 1, 1), "everyOtherYear", date(2026, 1, 1), date(2030, 12, 31))
        assert result == [date(2026, 1, 1), date(2028, 1, 1), date(2030, 1, 1)]

    def test_unknown_frequency_treated_as_one_time(self):
        result = _expand_occurrences(date(2026, 3, 15), "unknownFreq", date(2026, 3, 1), date(2026, 3, 31))
        assert result == [date(2026, 3, 15)]


class TestExpandScheduledTransactions:
    def _make_txn(self, **overrides):
        base = {
            "id": "st1",
            "account_id": "checking",
            "amount": -50000,
            "payee_name": "Rent",
            "date_next": "2026-03-15",
            "frequency": "monthly",
            "transfer_account_id": None,
            "deleted": False,
        }
        return {**base, **overrides}

    def test_on_checking(self):
        txn = self._make_txn()
        result = expand_scheduled_transactions([txn], ["checking"], date(2026, 3, 1), date(2026, 3, 31))
        assert len(result) == 1
        assert result[0].amount == -50.0
        assert result[0].payee == "Rent"

    def test_transfer_to_checking(self):
        txn = self._make_txn(
            account_id="cc-account",
            transfer_account_id="checking",
            amount=50000,  # positive from CC perspective
        )
        result = expand_scheduled_transactions([txn], ["checking"], date(2026, 3, 1), date(2026, 3, 31))
        assert len(result) == 1
        assert result[0].amount == -50.0  # flipped sign

    def test_unrelated_account_excluded(self):
        txn = self._make_txn(account_id="savings")
        result = expand_scheduled_transactions([txn], ["checking"], date(2026, 3, 1), date(2026, 3, 31))
        assert len(result) == 0

    def test_deleted_excluded(self):
        txn = self._make_txn(deleted=True)
        result = expand_scheduled_transactions([txn], ["checking"], date(2026, 3, 1), date(2026, 3, 31))
        assert len(result) == 0

    def test_sorted_by_date(self):
        txns = [
            self._make_txn(id="st1", date_next="2026-03-20", payee_name="B"),
            self._make_txn(id="st2", date_next="2026-03-10", payee_name="A"),
        ]
        result = expand_scheduled_transactions(txns, ["checking"], date(2026, 3, 1), date(2026, 3, 31))
        assert result[0].payee == "A"
        assert result[1].payee == "B"
