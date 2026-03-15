"""Tests for milliunit conversion helpers."""

from __future__ import annotations

import pytest

from ynab_tools.core.money import dollars_to_milliunits, fmt_dollars, milliunits_to_dollars


class TestMilliunitsToDollars:
    def test_positive(self):
        assert milliunits_to_dollars(1500000) == 1500.0

    def test_negative(self):
        assert milliunits_to_dollars(-250000) == -250.0

    def test_zero(self):
        assert milliunits_to_dollars(0) == 0.0

    def test_fractional(self):
        assert milliunits_to_dollars(1234) == 1.234

    def test_one_dollar(self):
        assert milliunits_to_dollars(1000) == 1.0


class TestDollarsToMilliunits:
    def test_positive(self):
        assert dollars_to_milliunits(1500.0) == 1500000

    def test_negative(self):
        assert dollars_to_milliunits(-250.0) == -250000

    def test_zero(self):
        assert dollars_to_milliunits(0) == 0

    def test_rounds_to_int(self):
        # 1.2345 * 1000 = 1234.5 in IEEE 754 → rounds to 1234 (banker's rounding)
        assert dollars_to_milliunits(1.2345) == 1234
        assert dollars_to_milliunits(1.2346) == 1235

    def test_roundtrip(self):
        original = 42567
        assert dollars_to_milliunits(milliunits_to_dollars(original)) == original


class TestFmtDollars:
    def test_positive(self):
        assert fmt_dollars(1500.50) == "$1,500.50"

    def test_negative(self):
        assert fmt_dollars(-250.0) == "-$250.00"

    def test_zero(self):
        assert fmt_dollars(0) == "$0.00"

    def test_large(self):
        assert fmt_dollars(1234567.89) == "$1,234,567.89"

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (0.1, "$0.10"),
            (0.01, "$0.01"),
            (999.99, "$999.99"),
        ],
    )
    def test_various(self, value, expected):
        assert fmt_dollars(value) == expected
