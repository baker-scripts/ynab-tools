"""Tests for monthly expense calculation."""

from __future__ import annotations

from unittest.mock import MagicMock

from ynab_tools.core.cache import cache_path, write_cache
from ynab_tools.monitor.expenses import calculate_monthly_expenses


class TestCalculateMonthlyExpenses:
    def test_uses_cache(self, tmp_cache_dir):
        """Cached data is returned without API calls."""
        filepath = cache_path(tmp_cache_dir, "monthly_expenses_test-budget.json")
        write_cache(
            filepath,
            {
                "monthly_totals": [
                    ["2026-01-01", 3000.0],
                    ["2025-12-01", 2500.0],
                ],
            },
        )

        client = MagicMock()
        client.budget_id = "test-budget"

        avg_daily, avg_monthly = calculate_monthly_expenses(client, tmp_cache_dir)
        assert avg_monthly == 2750.0
        assert avg_daily > 0
        client.get.assert_not_called()

    def test_dry_run_skips_cache(self, tmp_cache_dir):
        """dry_run=True bypasses cache and fetches fresh data."""
        filepath = cache_path(tmp_cache_dir, "monthly_expenses_test-budget.json")
        write_cache(
            filepath,
            {
                "monthly_totals": [["2026-01-01", 9999.0]],
            },
        )

        client = MagicMock()
        client.budget_id = "test-budget"
        client.get.return_value = {
            "month": {
                "categories": [
                    {
                        "activity": -1000000,  # -$1000 in milliunits
                        "deleted": False,
                        "hidden": False,
                        "category_group_name": "Bills",
                    },
                ],
            },
        }

        _avg_daily, avg_monthly = calculate_monthly_expenses(client, tmp_cache_dir, dry_run=True)
        assert avg_monthly == 1000.0
        assert client.get.call_count == 13  # 13 months
