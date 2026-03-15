"""Tests for YNAB API client — retry, rate limit, error handling."""

from __future__ import annotations

import httpx
import pytest
import respx

from ynab_tools.core.client import YNAB_BASE, YnabClient, sanitize_error
from ynab_tools.exceptions import FatalError, TransientError, YnabAPIError


@pytest.fixture
def client():
    c = YnabClient(api_token="test-token", budget_id="test-budget", timeout=5)
    yield c
    c.close()


class TestSanitizeError:
    def test_redacts_bearer_token(self):
        text = "Authorization: Bearer sk-secret-token-123"
        result = sanitize_error(text)
        assert "sk-secret-token-123" not in result
        assert "[REDACTED]" in result

    def test_redacts_key_value(self):
        text = 'token: "my-secret-value"'
        result = sanitize_error(text)
        assert "my-secret-value" not in result

    def test_truncates_long_body(self):
        text = "x" * 1000
        result = sanitize_error(text, max_length=100)
        assert len(result) <= 100

    def test_preserves_safe_text(self):
        text = "Something went wrong with the budget"
        assert sanitize_error(text) == text


class TestClientGet:
    @respx.mock
    def test_successful_get(self, client):
        respx.get(f"{YNAB_BASE}/budgets/test-budget/accounts").mock(
            return_value=httpx.Response(
                200,
                json={"data": {"accounts": [{"id": "acc1", "name": "Checking"}]}},
            )
        )
        result = client.get("/budgets/test-budget/accounts")
        assert result["accounts"][0]["id"] == "acc1"

    @respx.mock
    def test_auth_error_401(self, client):
        respx.get(f"{YNAB_BASE}/budgets/test-budget/accounts").mock(
            return_value=httpx.Response(401, text="Unauthorized")
        )
        with pytest.raises(FatalError, match="auth error"):
            client.get("/budgets/test-budget/accounts")

    @respx.mock
    def test_auth_error_403(self, client):
        respx.get(f"{YNAB_BASE}/budgets/test-budget/accounts").mock(return_value=httpx.Response(403, text="Forbidden"))
        with pytest.raises(FatalError, match="auth error"):
            client.get("/budgets/test-budget/accounts")

    @respx.mock
    def test_client_error_400(self, client):
        respx.get(f"{YNAB_BASE}/budgets/test-budget/bad").mock(return_value=httpx.Response(400, text="Bad Request"))
        with pytest.raises(YnabAPIError) as exc_info:
            client.get("/budgets/test-budget/bad")
        assert exc_info.value.status_code == 400

    @respx.mock
    def test_server_error_retries_and_fails(self, client, monkeypatch):
        # Patch sleep to avoid waiting
        monkeypatch.setattr("ynab_tools.core.client.time.sleep", lambda _: None)

        respx.get(f"{YNAB_BASE}/budgets/test-budget/accounts").mock(
            return_value=httpx.Response(500, text="Internal Server Error")
        )
        with pytest.raises(TransientError, match="failed after 3 attempts"):
            client.get("/budgets/test-budget/accounts")

    @respx.mock
    def test_server_error_retries_then_succeeds(self, client, monkeypatch):
        monkeypatch.setattr("ynab_tools.core.client.time.sleep", lambda _: None)

        route = respx.get(f"{YNAB_BASE}/budgets/test-budget/accounts")
        route.side_effect = [
            httpx.Response(500, text="Error"),
            httpx.Response(200, json={"data": {"accounts": []}}),
        ]
        result = client.get("/budgets/test-budget/accounts")
        assert result["accounts"] == []

    @respx.mock
    def test_rate_limit_429_retries(self, client, monkeypatch):
        monkeypatch.setattr("ynab_tools.core.client.time.sleep", lambda _: None)

        route = respx.get(f"{YNAB_BASE}/budgets/test-budget/accounts")
        route.side_effect = [
            httpx.Response(429, headers={"Retry-After": "1"}),
            httpx.Response(200, json={"data": {"ok": True}}),
        ]
        result = client.get("/budgets/test-budget/accounts")
        assert result["ok"] is True


class TestClientPut:
    @respx.mock
    def test_successful_put(self, client):
        respx.put(f"{YNAB_BASE}/budgets/test-budget/transactions/txn1").mock(
            return_value=httpx.Response(
                200,
                json={"data": {"transaction": {"id": "txn1", "memo": "updated"}}},
            )
        )
        result = client.put(
            "/budgets/test-budget/transactions/txn1",
            {"transaction": {"memo": "updated"}},
        )
        assert result["transaction"]["memo"] == "updated"


class TestClientPost:
    @respx.mock
    def test_successful_post(self, client):
        respx.post(f"{YNAB_BASE}/budgets/test-budget/transactions").mock(
            return_value=httpx.Response(
                201,
                json={"data": {"transaction": {"id": "new1"}}},
            )
        )
        result = client.post(
            "/budgets/test-budget/transactions",
            {"transaction": {"amount": -50000}},
        )
        assert result["transaction"]["id"] == "new1"


class TestClientContextManager:
    def test_context_manager(self):
        with YnabClient(api_token="test", budget_id="budget") as client:
            assert client.budget_id == "budget"
