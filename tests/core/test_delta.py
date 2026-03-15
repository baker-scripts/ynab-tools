"""Tests for delta sync with server_knowledge."""

from __future__ import annotations

import json
import os
import time

import httpx
import pytest
import respx

from ynab_tools.core.cache import cache_path, write_cache
from ynab_tools.core.client import YNAB_BASE, YnabClient
from ynab_tools.core.delta import fetch_scheduled_transactions_delta


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr("ynab_tools.core.client.time.sleep", lambda _: None)
    c = YnabClient(api_token="test-token", budget_id="test-budget", timeout=5)
    yield c
    c.close()


class TestFullFetch:
    @respx.mock
    def test_first_run_full_fetch(self, client, tmp_cache_dir):
        """First call with no cache does a full fetch."""
        respx.get(f"{YNAB_BASE}/budgets/test-budget/scheduled_transactions").mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": {
                        "server_knowledge": 100,
                        "scheduled_transactions": [
                            {"id": "st1", "amount": -50000, "payee_name": "Rent"},
                            {"id": "st2", "amount": -10000, "payee_name": "Netflix"},
                        ],
                    }
                },
            )
        )

        result = fetch_scheduled_transactions_delta(client, tmp_cache_dir)
        assert len(result) == 2
        assert result[0]["id"] == "st1"

        # Verify cache was written
        filepath = cache_path(tmp_cache_dir, "delta_scheduled_test-budget.json")
        assert os.path.exists(filepath)


class TestDeltaSync:
    @respx.mock
    def test_delta_merge_new_transaction(self, client, tmp_cache_dir):
        """Delta adds a new transaction."""
        # Seed cache with existing data
        filepath = cache_path(tmp_cache_dir, "delta_scheduled_test-budget.json")
        write_cache(
            filepath,
            {
                "server_knowledge": 100,
                "transactions": [{"id": "st1", "amount": -50000, "payee_name": "Rent"}],
            },
        )

        respx.get(
            f"{YNAB_BASE}/budgets/test-budget/scheduled_transactions",
            params={"last_knowledge_of_server": "100"},
        ).mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": {
                        "server_knowledge": 150,
                        "scheduled_transactions": [
                            {"id": "st2", "amount": -10000, "payee_name": "Netflix"},
                        ],
                    }
                },
            )
        )

        result = fetch_scheduled_transactions_delta(client, tmp_cache_dir)
        assert len(result) == 2
        ids = {t["id"] for t in result}
        assert ids == {"st1", "st2"}

    @respx.mock
    def test_delta_updates_existing(self, client, tmp_cache_dir):
        """Delta updates an existing transaction."""
        filepath = cache_path(tmp_cache_dir, "delta_scheduled_test-budget.json")
        write_cache(
            filepath,
            {
                "server_knowledge": 100,
                "transactions": [{"id": "st1", "amount": -50000, "payee_name": "Rent"}],
            },
        )

        respx.get(
            f"{YNAB_BASE}/budgets/test-budget/scheduled_transactions",
            params={"last_knowledge_of_server": "100"},
        ).mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": {
                        "server_knowledge": 150,
                        "scheduled_transactions": [
                            {"id": "st1", "amount": -55000, "payee_name": "Rent (increased)"},
                        ],
                    }
                },
            )
        )

        result = fetch_scheduled_transactions_delta(client, tmp_cache_dir)
        assert len(result) == 1
        assert result[0]["amount"] == -55000
        assert result[0]["payee_name"] == "Rent (increased)"

    @respx.mock
    def test_delta_deletes_transaction(self, client, tmp_cache_dir):
        """Delta removes a deleted transaction."""
        filepath = cache_path(tmp_cache_dir, "delta_scheduled_test-budget.json")
        write_cache(
            filepath,
            {
                "server_knowledge": 100,
                "transactions": [
                    {"id": "st1", "amount": -50000, "payee_name": "Rent"},
                    {"id": "st2", "amount": -10000, "payee_name": "Netflix"},
                ],
            },
        )

        respx.get(
            f"{YNAB_BASE}/budgets/test-budget/scheduled_transactions",
            params={"last_knowledge_of_server": "100"},
        ).mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": {
                        "server_knowledge": 150,
                        "scheduled_transactions": [
                            {"id": "st2", "deleted": True},
                        ],
                    }
                },
            )
        )

        result = fetch_scheduled_transactions_delta(client, tmp_cache_dir)
        assert len(result) == 1
        assert result[0]["id"] == "st1"

    @respx.mock
    def test_delta_fallback_on_api_error(self, client, tmp_cache_dir):
        """Falls back to full fetch when delta API call fails."""
        filepath = cache_path(tmp_cache_dir, "delta_scheduled_test-budget.json")
        write_cache(
            filepath,
            {
                "server_knowledge": 100,
                "transactions": [{"id": "st1", "amount": -50000}],
            },
        )

        # Delta call fails with 400
        respx.get(
            f"{YNAB_BASE}/budgets/test-budget/scheduled_transactions",
            params={"last_knowledge_of_server": "100"},
        ).mock(return_value=httpx.Response(400, text="Bad delta request"))

        # Full fetch succeeds
        respx.get(f"{YNAB_BASE}/budgets/test-budget/scheduled_transactions").mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": {
                        "server_knowledge": 200,
                        "scheduled_transactions": [
                            {"id": "st1", "amount": -50000},
                            {"id": "st3", "amount": -20000},
                        ],
                    }
                },
            )
        )

        result = fetch_scheduled_transactions_delta(client, tmp_cache_dir)
        assert len(result) == 2


class TestExpiredCache:
    @respx.mock
    def test_expired_cache_does_full_fetch(self, client, tmp_cache_dir):
        """Expired cache triggers full fetch."""
        filepath = cache_path(tmp_cache_dir, "delta_scheduled_test-budget.json")
        # Write cache, then backdate it
        write_cache(
            filepath,
            {
                "server_knowledge": 100,
                "transactions": [{"id": "old"}],
            },
        )
        with open(filepath) as f:
            data = json.load(f)
        data["cached_at"] = time.time() - 86400 * 8  # 8 days ago (past 7-day TTL)
        with open(filepath, "w") as f:
            json.dump(data, f)

        respx.get(f"{YNAB_BASE}/budgets/test-budget/scheduled_transactions").mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": {
                        "server_knowledge": 300,
                        "scheduled_transactions": [{"id": "fresh"}],
                    }
                },
            )
        )

        result = fetch_scheduled_transactions_delta(client, tmp_cache_dir)
        assert len(result) == 1
        assert result[0]["id"] == "fresh"
