"""Tests for YNAB transaction sync operations."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from ynab_tools.amazon.sync import (
    YNAB_MEMO_LIMIT,
    amount_to_decimal,
    build_memo,
    fetch_payees,
    find_payee_by_name,
    get_ynab_transactions,
    update_ynab_transaction,
)
from ynab_tools.core.models import Payee
from ynab_tools.exceptions import ConfigError


class TestAmountToDecimal:
    def test_positive(self):
        assert amount_to_decimal(26990) == Decimal("26.990")

    def test_negative(self):
        assert amount_to_decimal(-10000) == Decimal("-10.000")

    def test_zero(self):
        assert amount_to_decimal(0) == Decimal("0")

    def test_fractional(self):
        assert amount_to_decimal(1) == Decimal("0.001")


class TestFindPayeeByName:
    def test_found(self):
        payees = [
            Payee(id="1", name="Amazon"),
            Payee(id="2", name="Walmart"),
        ]
        result = find_payee_by_name(payees, "Amazon")
        assert result is not None
        assert result.id == "1"

    def test_not_found(self):
        payees = [Payee(id="1", name="Amazon")]
        assert find_payee_by_name(payees, "Target") is None

    def test_empty_list(self):
        assert find_payee_by_name([], "Amazon") is None


class TestFetchPayees:
    def test_parses_response(self):
        client = MagicMock()
        client.budget_id = "test-budget"
        client.get.return_value = {
            "payees": [
                {"id": "p1", "name": "Amazon", "deleted": False},
                {"id": "p2", "name": "Walmart", "deleted": False},
            ]
        }
        payees = fetch_payees(client)
        assert len(payees) == 2
        assert payees[0].name == "Amazon"
        client.get.assert_called_once_with("/budgets/test-budget/payees")


class TestBuildMemo:
    def test_simple_memo(self):
        memo = build_memo(
            items=[],
            order_number="111-0000000-0000000",
            transaction_total=Decimal("25.00"),
            order_total=Decimal("25.00"),
        )
        assert "111-0000000-0000000" in memo
        assert "amazon.com" in memo

    def test_partial_order_warning(self):
        memo = build_memo(
            items=[],
            order_number="111-0000000-0000000",
            transaction_total=Decimal("10.00"),
            order_total=Decimal("50.00"),
        )
        assert "doesn't represent the entire order" in memo
        assert "$50.00" in memo

    def test_no_partial_warning_when_equal(self):
        memo = build_memo(
            items=[],
            order_number="111-0000000-0000000",
            transaction_total=Decimal("25.00"),
            order_total=Decimal("25.00"),
        )
        assert "doesn't represent" not in memo

    def test_markdown_link(self):
        memo = build_memo(
            items=[],
            order_number="111-0000000-0000000",
            transaction_total=Decimal("25.00"),
            order_total=Decimal("25.00"),
            use_markdown=True,
        )
        assert "[Order #111-0000000-0000000](" in memo

    def test_plain_link(self):
        with patch("ynab_tools.amazon.sync.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(ynab_use_markdown=False)
            memo = build_memo(
                items=[],
                order_number="111-0000000-0000000",
                transaction_total=Decimal("25.00"),
                order_total=Decimal("25.00"),
            )
        assert "[Order #" not in memo
        assert "amazon.com" in memo

    def test_items_in_memo(self):
        class FakeItem:
            title = "Widget"
            price = 12.99

        memo = build_memo(
            items=[FakeItem()],
            order_number="111-0000000-0000000",
            transaction_total=Decimal("12.99"),
            order_total=Decimal("12.99"),
        )
        assert "Widget" in memo
        assert "$12.99" in memo


class TestUpdateYnabTransaction:
    def test_updates_via_client(self):
        client = MagicMock()
        client.budget_id = "test-budget"
        update_ynab_transaction(client, "txn-123", memo="Test memo", payee_id="p1")
        client.put.assert_called_once()
        call_args = client.put.call_args
        assert "txn-123" in call_args[0][0]
        assert call_args[0][1]["transaction"]["memo"] == "Test memo"
        assert call_args[0][1]["transaction"]["payee_id"] == "p1"

    def test_truncates_long_memo(self):
        client = MagicMock()
        client.budget_id = "test-budget"
        long_memo = "x" * (YNAB_MEMO_LIMIT + 100)
        update_ynab_transaction(client, "txn-123", memo=long_memo, payee_id="p1")
        call_args = client.put.call_args
        actual_memo = call_args[0][1]["transaction"]["memo"]
        assert len(actual_memo) <= YNAB_MEMO_LIMIT + 10  # some slack for truncation logic


class TestGetYnabTransactions:
    @patch("ynab_tools.amazon.sync.get_settings")
    @patch("ynab_tools.amazon.sync.fetch_transactions_by_payee")
    @patch("ynab_tools.amazon.sync.fetch_payees")
    def test_finds_target_payee(self, mock_payees, mock_txns, mock_settings):
        mock_settings.return_value = MagicMock(
            ynab_payee_name_processing_completed="Amazon",
            ynab_payee_name_to_be_processed="Amazon - Needs Memo",
            match_empty_memo=False,
        )
        mock_payees.return_value = [
            Payee(id="p1", name="Amazon"),
            Payee(id="p2", name="Amazon - Needs Memo"),
        ]
        mock_txns.return_value = []

        client = MagicMock()
        client.budget_id = "test-budget"
        _txns, payee = get_ynab_transactions(client)
        assert payee.name == "Amazon"

    @patch("ynab_tools.amazon.sync.get_settings")
    @patch("ynab_tools.amazon.sync.fetch_payees")
    def test_raises_on_missing_payee(self, mock_payees, mock_settings):
        mock_settings.return_value = MagicMock(
            ynab_payee_name_processing_completed="Amazon",
            match_empty_memo=False,
        )
        mock_payees.return_value = []

        client = MagicMock()
        with pytest.raises(ConfigError, match="Amazon"):
            get_ynab_transactions(client)
