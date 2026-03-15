"""Unified Pydantic v2 settings with lazy loading.

Settings are loaded once on first access via get_settings(). Feature-specific
validation only runs when that feature is invoked, not at import time.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Flat settings class for all ynab-tools configuration.

    All values come from environment variables (or .env file).
    """

    model_config = SettingsConfigDict(
        env_file=["/app/config/.env", ".env"],
        env_file_encoding="utf-8",
        env_prefix="",
        extra="ignore",
    )

    # === YNAB API ===
    ynab_api_token: SecretStr = SecretStr("")
    ynab_budget_id: str = "last-used"
    ynab_account_id: str = ""  # comma-separated

    # === Monitor Settings ===
    monitor_days: str = ""  # empty = end of current month
    min_balance: int = 0
    ynab_target_buffer_days: int = 10
    ynab_alert_buffer_days: int = 5
    cache_dir: str = "/tmp/ynab-tools"
    dry_run: bool = False

    # === CC Payment Tracking ===
    ynab_cc_close_dates: str = ""
    ynab_cc_categories: str = ""
    ynab_cc_create_payments: bool = False

    # === Notifications ===
    apprise_urls: SecretStr = SecretStr("")
    notifiarr_api_key: SecretStr = SecretStr("")
    notifiarr_channel_id: str = ""
    notifiarr_update_channel_id: str = ""
    update_apprise_urls: SecretStr = SecretStr("")

    # === Scheduling ===
    schedule: str = ""
    update_schedule: str = ""

    # === Amazon Settings ===
    amazon_user: str = ""
    amazon_password: SecretStr = SecretStr("")
    amazon_otp_secret_key: SecretStr | None = None
    amazon_debug: bool = False
    amazon_full_details: bool = True
    amazon_cache_dir: str = ""

    # === Amazon → YNAB Matching ===
    ynab_payee_name_to_be_processed: str = "Amazon - Needs Memo"
    ynab_payee_name_processing_completed: str = "Amazon"
    ynab_use_markdown: bool = False
    match_empty_memo: bool = False
    amount_match_tolerance: float = 2.00
    date_mismatch_tolerance_days: int = 0
    auto_accept_date_mismatch: bool = False
    non_interactive: bool = False
    ynab_approved_statuses: str = "approved,unapproved"

    # === AI Summarization ===
    use_ai_summarization: bool = False
    openai_api_key: SecretStr | None = None

    # === General ===
    tz: str = ""

    @property
    def account_ids(self) -> list[str]:
        """Parse comma-separated account IDs."""
        return [aid.strip() for aid in self.ynab_account_id.split(",") if aid.strip()]

    @property
    def approved_statuses_list(self) -> list[str]:
        """Parse comma-separated approved statuses."""
        return [s.strip() for s in self.ynab_approved_statuses.split(",") if s.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Get the singleton Settings instance (lazy-loaded)."""
    return Settings()  # type: ignore[call-arg]
