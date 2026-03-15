"""Milliunit conversion helpers for YNAB amounts.

YNAB stores all monetary amounts in milliunits (1 dollar = 1000 milliunits).
"""

from __future__ import annotations


def milliunits_to_dollars(milliunits: int) -> float:
    """Convert YNAB milliunits to dollars."""
    return milliunits / 1000.0


def dollars_to_milliunits(dollars: float) -> int:
    """Convert dollars to YNAB milliunits."""
    return int(dollars * 1000)


def fmt_dollars(amount: float) -> str:
    """Format a dollar amount with sign for negative values."""
    if amount < 0:
        return f"-${abs(amount):,.0f}"
    return f"${amount:,.0f}"
