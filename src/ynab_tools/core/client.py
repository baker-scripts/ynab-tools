"""YNAB API client with retry, rate limiting, and error sanitization."""

from __future__ import annotations

import re
import time
from typing import Any

import httpx
from loguru import logger

from ynab_tools.exceptions import FatalError, TransientError, YnabAPIError

YNAB_BASE = "https://api.ynab.com/v1"
_RETRY_MAX = 3
_RETRY_BACKOFFS = [30, 60, 120]


def sanitize_error(body: str, max_length: int = 500) -> str:
    """Remove sensitive data from API error responses before logging."""
    text = body[:max_length]
    text = re.sub(r"(Bearer\s+)\S+", r"\1[REDACTED]", text, flags=re.IGNORECASE)
    text = re.sub(
        r'(["\']?(?:access_token|token|key|secret|password|authorization)["\']?\s*[:=]\s*)["\']?\S+',
        r"\1[REDACTED]",
        text,
        flags=re.IGNORECASE,
    )
    return text


class YnabClient:
    """Sync YNAB API client with retry and rate-limit handling.

    Args:
        api_token: YNAB personal access token.
        budget_id: YNAB budget ID or "last-used".
        user_agent: User-Agent header value.
        timeout: Request timeout in seconds.
    """

    def __init__(
        self,
        api_token: str,
        budget_id: str = "last-used",
        user_agent: str = "ynab-tools",
        timeout: int = 30,
    ) -> None:
        self.budget_id = budget_id
        self._client = httpx.Client(
            base_url=YNAB_BASE,
            headers={
                "Authorization": f"Bearer {api_token}",
                "User-Agent": user_agent,
            },
            timeout=timeout,
        )

    def close(self) -> None:
        """Close the underlying HTTP client."""
        self._client.close()

    def __enter__(self) -> YnabClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def _request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        """Make an authenticated request with retry and backoff.

        Retries on 5xx, network errors, and timeouts with exponential backoff.
        Honors Retry-After header on 429. Fails immediately on 401/403.
        """
        last_exc: Exception | None = None

        for attempt in range(_RETRY_MAX):
            try:
                if payload is not None:
                    response = self._client.request(method, path, json=payload)
                else:
                    response = self._client.request(method, path)

                # Auth errors — fail immediately
                if response.status_code in (401, 403):
                    body = response.text
                    raise FatalError(f"YNAB API auth error ({response.status_code}): {sanitize_error(body)}")

                # Rate limit — honor Retry-After
                if response.status_code == 429:
                    try:
                        retry_after = max(1, min(int(response.headers.get("Retry-After", 0)), 300))
                    except (ValueError, TypeError):
                        retry_after = _RETRY_BACKOFFS[attempt]
                    logger.warning(
                        f"YNAB API rate limited, waiting {retry_after}s (attempt {attempt + 1}/{_RETRY_MAX})"
                    )
                    time.sleep(retry_after)
                    last_exc = YnabAPIError(f"Rate limited ({response.status_code})", status_code=response.status_code)
                    continue

                # Server errors — retry with backoff
                if response.status_code >= 500:
                    body = response.text
                    wait = _RETRY_BACKOFFS[attempt]
                    logger.warning(
                        f"YNAB API error ({response.status_code}), retrying in {wait}s "
                        f"(attempt {attempt + 1}/{_RETRY_MAX})"
                    )
                    time.sleep(wait)
                    last_exc = YnabAPIError(
                        f"Server error ({response.status_code}): {sanitize_error(body)}",
                        status_code=response.status_code,
                    )
                    continue

                # Other client errors — fail immediately
                if response.status_code >= 400:
                    body = response.text
                    raise YnabAPIError(
                        f"YNAB API error ({response.status_code}): {sanitize_error(body)}",
                        status_code=response.status_code,
                    )

                return response.json()["data"]

            except (httpx.ConnectError, httpx.TimeoutException, OSError) as e:
                wait = _RETRY_BACKOFFS[attempt]
                logger.warning(f"Network error: {e}, retrying in {wait}s (attempt {attempt + 1}/{_RETRY_MAX})")
                time.sleep(wait)
                last_exc = e

        raise TransientError(f"YNAB API request failed after {_RETRY_MAX} attempts: {last_exc}") from last_exc

    def get(self, path: str) -> dict[str, Any]:
        """GET request to YNAB API."""
        return self._request("GET", path)

    def put(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        """PUT request to YNAB API."""
        return self._request("PUT", path, payload)

    def post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        """POST request to YNAB API."""
        return self._request("POST", path, payload)
