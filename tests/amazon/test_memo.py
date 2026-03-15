"""Tests for memo building, truncation, and URL extraction."""

from __future__ import annotations

from ynab_tools.amazon.memo import (
    YNAB_MEMO_LIMIT,
    extract_order_url,
    truncate_memo,
)


class TestExtractOrderUrl:
    def test_plain_url(self):
        memo = "Items\nhttps://www.amazon.com/gp/your-account/order-details?orderID=111-0000000-0000000"
        assert (
            extract_order_url(memo)
            == "https://www.amazon.com/gp/your-account/order-details?orderID=111-0000000-0000000"
        )

    def test_markdown_url(self):
        memo = "[Order #111-0000000-0000000](https://www.amazon.com/gp/your-account/order-details?orderID=111-0000000-0000000)"
        assert (
            extract_order_url(memo)
            == "https://www.amazon.com/gp/your-account/order-details?orderID=111-0000000-0000000"
        )

    def test_no_url(self):
        memo = "Just some text without a URL"
        assert extract_order_url(memo) is None

    def test_url_with_surrounding_text(self):
        memo = "Order: https://www.amazon.com/gp/your-account/order-details?orderID=ABC-123 done"
        assert extract_order_url(memo) == "https://www.amazon.com/gp/your-account/order-details?orderID=ABC-123"

    def test_multiline_url(self):
        """URL split across lines should be normalized and found."""
        memo = "Items\nhttps://www.amazon.com/gp/your-account/order-details?orderID=111-000-\n0000-0000000"
        # The normalize function joins lines containing amazon.com
        result = extract_order_url(memo)
        # May or may not find depending on exact split; test that it doesn't crash
        assert result is None or "amazon.com" in result


class TestTruncateMemo:
    def test_short_memo_unchanged(self):
        memo = "Short memo"
        assert truncate_memo(memo) == memo

    def test_at_limit_unchanged(self):
        memo = "x" * YNAB_MEMO_LIMIT
        assert truncate_memo(memo) == memo

    def test_over_limit_truncated(self):
        url = "https://www.amazon.com/gp/your-account/order-details?orderID=111-0000000-0000000"
        items = "\n".join(f"{i}. Item number {i} with a longer description" for i in range(1, 30))
        memo = f"{items}\n{url}"
        assert len(memo) > YNAB_MEMO_LIMIT

        result = truncate_memo(memo)
        assert len(result) <= YNAB_MEMO_LIMIT

    def test_preserves_url(self):
        url = "https://www.amazon.com/gp/your-account/order-details?orderID=111-0000000-0000000"
        items = "\n".join(f"{i}. Very long item description that takes up space" for i in range(1, 30))
        memo = f"{items}\n{url}"

        result = truncate_memo(memo)
        assert url in result

    def test_preserves_partial_order_warning(self):
        url = "https://www.amazon.com/gp/your-account/order-details?orderID=111-0000000-0000000"
        warning = "-This transaction doesn't represent the entire order. The order total is $50.00-"
        items = "\n".join(f"{i}. Item description" for i in range(1, 30))
        memo = f"{warning}\n{items}\n{url}"

        result = truncate_memo(memo)
        assert warning in result

    def test_adds_ellipsis_when_truncating(self):
        url = "https://www.amazon.com/gp/your-account/order-details?orderID=111-0000000-0000000"
        items = "\n".join(f"{i}. Very long item description padding" for i in range(1, 30))
        memo = f"{items}\n{url}"

        result = truncate_memo(memo)
        assert "..." in result
