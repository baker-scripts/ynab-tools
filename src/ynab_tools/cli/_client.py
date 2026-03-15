"""Shared client factory for CLI subcommands."""

from __future__ import annotations

from ynab_tools.config.settings import Settings
from ynab_tools.core.client import YnabClient
from ynab_tools.exceptions import ConfigError


def make_client(settings: Settings) -> YnabClient:
    """Create a YnabClient from settings, raising ConfigError if misconfigured."""
    token = settings.ynab_api_token.get_secret_value()
    if not token:
        raise ConfigError("YNAB_API_TOKEN is required")

    return YnabClient(
        api_token=token,
        budget_id=settings.ynab_budget_id,
    )
