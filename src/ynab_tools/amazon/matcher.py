"""Amount-based matching of YNAB transactions to Amazon orders."""

from __future__ import annotations

from decimal import Decimal

from loguru import logger

from ynab_tools.amazon.scraper import AmazonOrder


def locate_by_amount(
    amazon_orders: list[AmazonOrder],
    amount: Decimal,
    tolerance: float = 0.0,
) -> tuple[int | None, bool]:
    """Find an Amazon order matching the given amount.

    Tries exact match first, then falls back to closest match within tolerance.

    Args:
        amazon_orders: List of Amazon orders to search.
        amount: Positive dollar amount to match (e.g. 26.99).
        tolerance: Maximum dollar difference for fuzzy matching (0 = exact only).

    Returns:
        Tuple of (index or None, True if fuzzy match).
    """
    target = -amount  # transaction_total is positive (charge), amount is negative in YNAB

    # Exact match first
    for idx, order in enumerate(amazon_orders):
        if order.transaction_total == target:
            return idx, False

    # Fuzzy match within tolerance
    if tolerance > 0:
        tolerance_decimal = Decimal(str(tolerance))
        best_idx: int | None = None
        best_diff = tolerance_decimal + 1

        for idx, order in enumerate(amazon_orders):
            diff = abs(order.transaction_total - target)
            if diff <= tolerance_decimal and diff < best_diff:
                best_diff = diff
                best_idx = idx

        if best_idx is not None:
            return best_idx, True

        # Log near-misses for debugging
        for order in amazon_orders:
            diff = abs(order.transaction_total - target)
            if diff <= tolerance_decimal * 2:
                logger.info(
                    f"Near-miss: Amazon ${order.transaction_total:.2f} "
                    f"vs YNAB ${-amount:.2f} (diff: ${diff:.2f}, tolerance: ${tolerance:.2f})"
                )

    return None, False
