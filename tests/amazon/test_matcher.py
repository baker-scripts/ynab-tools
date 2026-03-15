"""Tests for Amazon order amount matching."""

from __future__ import annotations

from decimal import Decimal


from ynab_tools.amazon.matcher import locate_by_amount
from ynab_tools.amazon.scraper import AmazonOrder


def _make_order(amount: str, **overrides) -> AmazonOrder:
    """Create an AmazonOrder with the given transaction_total."""
    from datetime import date

    defaults = {
        "completed_date": date(2026, 3, 1),
        "transaction_total": Decimal(amount),
        "order_total": Decimal(amount),
        "order_number": "111-0000000-0000000",
        "order_link": "https://www.amazon.com/gp/your-account/order-details?orderID=111-0000000-0000000",
        "items": [],
    }
    return AmazonOrder(**{**defaults, **overrides})


class TestLocateByAmount:
    def test_exact_match(self):
        orders = [_make_order("10.00"), _make_order("26.99"), _make_order("50.00")]
        # YNAB amount is negative (outflow), we pass the raw value
        idx, is_fuzzy = locate_by_amount(orders, Decimal("-26.99"))
        assert idx == 1
        assert is_fuzzy is False

    def test_exact_match_first_item(self):
        orders = [_make_order("10.00"), _make_order("20.00")]
        idx, is_fuzzy = locate_by_amount(orders, Decimal("-10.00"))
        assert idx == 0
        assert is_fuzzy is False

    def test_exact_match_last_item(self):
        orders = [_make_order("10.00"), _make_order("20.00"), _make_order("30.00")]
        idx, is_fuzzy = locate_by_amount(orders, Decimal("-30.00"))
        assert idx == 2
        assert is_fuzzy is False

    def test_no_match(self):
        orders = [_make_order("10.00"), _make_order("20.00")]
        idx, is_fuzzy = locate_by_amount(orders, Decimal("-99.99"))
        assert idx is None
        assert is_fuzzy is False

    def test_empty_list(self):
        idx, is_fuzzy = locate_by_amount([], Decimal("-10.00"))
        assert idx is None
        assert is_fuzzy is False

    def test_fuzzy_match_within_tolerance(self):
        orders = [_make_order("10.50")]
        idx, is_fuzzy = locate_by_amount(orders, Decimal("-10.00"), tolerance=1.00)
        assert idx == 0
        assert is_fuzzy is True

    def test_fuzzy_match_outside_tolerance(self):
        orders = [_make_order("10.50")]
        idx, is_fuzzy = locate_by_amount(orders, Decimal("-10.00"), tolerance=0.10)
        assert idx is None
        assert is_fuzzy is False

    def test_fuzzy_match_picks_closest(self):
        orders = [_make_order("11.00"), _make_order("10.20"), _make_order("9.00")]
        idx, is_fuzzy = locate_by_amount(orders, Decimal("-10.00"), tolerance=2.00)
        assert idx == 1  # 10.20 is closest to 10.00
        assert is_fuzzy is True

    def test_exact_preferred_over_fuzzy(self):
        orders = [_make_order("10.20"), _make_order("10.00"), _make_order("9.80")]
        idx, is_fuzzy = locate_by_amount(orders, Decimal("-10.00"), tolerance=1.00)
        assert idx == 1  # exact match found first
        assert is_fuzzy is False

    def test_zero_tolerance_no_fuzzy(self):
        orders = [_make_order("10.01")]
        idx, is_fuzzy = locate_by_amount(orders, Decimal("-10.00"), tolerance=0.0)
        assert idx is None
        assert is_fuzzy is False

    def test_fuzzy_at_exact_boundary(self):
        orders = [_make_order("11.00")]
        idx, is_fuzzy = locate_by_amount(orders, Decimal("-10.00"), tolerance=1.00)
        assert idx == 0
        assert is_fuzzy is True

    def test_fuzzy_just_outside_boundary(self):
        orders = [_make_order("11.01")]
        idx, _is_fuzzy = locate_by_amount(orders, Decimal("-10.00"), tolerance=1.00)
        assert idx is None

    def test_multiple_exact_returns_first(self):
        orders = [_make_order("10.00"), _make_order("10.00")]
        idx, is_fuzzy = locate_by_amount(orders, Decimal("-10.00"))
        assert idx == 0
        assert is_fuzzy is False

    def test_negative_amount_handling(self):
        """YNAB amounts are negative for outflows; matcher inverts them."""
        orders = [_make_order("25.00")]
        idx, _is_fuzzy = locate_by_amount(orders, Decimal("-25.00"))
        assert idx == 0

    def test_large_amount(self):
        orders = [_make_order("1234.56")]
        idx, _ = locate_by_amount(orders, Decimal("-1234.56"))
        assert idx == 0

    def test_cents_precision(self):
        orders = [_make_order("0.01")]
        idx, _ = locate_by_amount(orders, Decimal("-0.01"))
        assert idx == 0
