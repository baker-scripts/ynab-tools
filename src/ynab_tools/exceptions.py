"""Unified exception hierarchy for ynab-tools."""

from __future__ import annotations


class YnabToolsError(Exception):
    """Base exception for all ynab-tools errors."""


class YnabAPIError(YnabToolsError):
    """Raised when the YNAB API request fails after all retries."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class TransientError(YnabToolsError):
    """Retryable error (network timeout, 5xx, rate limit exhausted)."""


class FatalError(YnabToolsError):
    """Non-retryable error requiring human intervention (auth, bad config)."""


class ConfigError(YnabToolsError):
    """Invalid or missing configuration."""


class AmazonAuthError(YnabToolsError):
    """Amazon authentication failed."""


class SyncError(YnabToolsError):
    """Error during Amazon→YNAB sync."""

    def __init__(self, message: str, *, sync_result: object | None = None) -> None:
        super().__init__(message)
        self.sync_result = sync_result


class TransientSyncError(SyncError, TransientError):
    """Retryable sync error."""


class FatalSyncError(SyncError, FatalError):
    """Non-retryable sync error."""
