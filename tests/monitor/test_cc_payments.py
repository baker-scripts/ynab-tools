"""Tests for CC close date calculation and payment logic."""

from __future__ import annotations

from datetime import date


from ynab_tools.monitor.cc_payments import (
    _get_last_close_date,
    get_covered_cc_ids,
    parse_cc_close_dates,
)


class TestParseCcCloseDates:
    def test_basic(self):
        result = parse_cc_close_dates("Chase Freedom:15,Amex Gold:25")
        assert result == {"Chase Freedom": 15, "Amex Gold": 25}

    def test_empty(self):
        assert parse_cc_close_dates("") == {}
        assert parse_cc_close_dates("  ") == {}

    def test_single(self):
        assert parse_cc_close_dates("Card:1") == {"Card": 1}

    def test_invalid_day(self):
        result = parse_cc_close_dates("Card:abc")
        assert result == {}

    def test_no_colon(self):
        result = parse_cc_close_dates("JustAName")
        assert result == {}

    def test_whitespace(self):
        result = parse_cc_close_dates("  Card A : 5 , Card B : 20 ")
        assert result == {"Card A": 5, "Card B": 20}


class TestGetLastCloseDate:
    def test_close_already_passed(self):
        result = _get_last_close_date(10, today=date(2026, 3, 15))
        assert result == date(2026, 3, 10)

    def test_close_today(self):
        result = _get_last_close_date(15, today=date(2026, 3, 15))
        assert result == date(2026, 3, 15)

    def test_close_not_yet(self):
        result = _get_last_close_date(20, today=date(2026, 3, 15))
        assert result == date(2026, 2, 20)

    def test_day_31_feb(self):
        # Close day 31 but Feb only has 28
        result = _get_last_close_date(31, today=date(2026, 3, 15))
        assert result == date(2026, 2, 28)


class TestGetCoveredCcIds:
    def test_transfer_from_checking_to_cc(self):
        scheduled = [
            {
                "account_id": "checking",
                "transfer_account_id": "cc1",
                "deleted": False,
            }
        ]
        result = get_covered_cc_ids(scheduled, ["checking"])
        assert result == {"cc1"}

    def test_transfer_on_cc_side(self):
        scheduled = [
            {
                "account_id": "cc1",
                "transfer_account_id": "checking",
                "deleted": False,
            }
        ]
        result = get_covered_cc_ids(scheduled, ["checking"])
        assert result == {"cc1"}

    def test_deleted_ignored(self):
        scheduled = [
            {
                "account_id": "checking",
                "transfer_account_id": "cc1",
                "deleted": True,
            }
        ]
        result = get_covered_cc_ids(scheduled, ["checking"])
        assert result == set()

    def test_no_transfer(self):
        scheduled = [
            {
                "account_id": "checking",
                "transfer_account_id": None,
                "deleted": False,
            }
        ]
        result = get_covered_cc_ids(scheduled, ["checking"])
        assert result == set()

    def test_unrelated_transfer(self):
        scheduled = [
            {
                "account_id": "savings",
                "transfer_account_id": "cc1",
                "deleted": False,
            }
        ]
        result = get_covered_cc_ids(scheduled, ["checking"])
        assert result == set()
