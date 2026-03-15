"""Monthly expense calculation with 24h disk cache."""

from __future__ import annotations

from datetime import date, datetime

from loguru import logger

from ynab_tools.core.cache import cache_path, read_cache, write_cache
from ynab_tools.core.client import YnabClient
from ynab_tools.core.money import milliunits_to_dollars
from ynab_tools.monitor.scheduler import _add_months

_SKIP_GROUPS = frozenset({"Credit Card Payments", "Internal Master Category"})
_CACHE_TTL = 86400  # 24 hours
_DAYS_PER_MONTH = 30.44


def calculate_monthly_expenses(
    client: YnabClient,
    cache_dir: str,
    dry_run: bool = False,
) -> tuple[float, float]:
    """Calculate average monthly expenses from trailing 13 months.

    Uses disk cache (24h TTL) to avoid 13 sequential API calls on every run.
    dry_run always fetches fresh data.

    Returns:
        Tuple of (avg_daily_expenses, avg_monthly_expenses).
    """
    filepath = cache_path(cache_dir, f"monthly_expenses_{client.budget_id}.json")

    if not dry_run:
        cached = read_cache(filepath, _CACHE_TTL)
        if cached and "monthly_totals" in cached:
            monthly_totals = [(date.fromisoformat(m), t) for m, t in cached["monthly_totals"]]
            avg_monthly = sum(t for _, t in monthly_totals) / len(monthly_totals)
            avg_daily = avg_monthly / _DAYS_PER_MONTH
            logger.info(f"Monthly expenses (cached): ${avg_monthly:,.2f}/mo (${avg_daily:,.2f}/day)")
            return avg_daily, avg_monthly

    today = datetime.now().date()
    first_of_month = date(today.year, today.month, 1)

    monthly_totals: list[tuple[date, float]] = []
    for i in range(1, 14):
        month_start = _add_months(first_of_month, -i)
        month_str = month_start.strftime("%Y-%m-01")
        data = client.get(f"/budgets/{client.budget_id}/months/{month_str}")
        month_detail = data["month"]

        total = 0.0
        for cat in month_detail["categories"]:
            if cat.get("deleted", False) or cat.get("hidden", False):
                continue
            if cat.get("category_group_name", "") in _SKIP_GROUPS:
                continue
            activity = milliunits_to_dollars(cat["activity"])
            if activity < 0:
                total += abs(activity)

        monthly_totals.append((month_start, total))

    write_cache(
        filepath,
        {"monthly_totals": [(m.isoformat(), t) for m, t in monthly_totals]},
    )

    avg_monthly = sum(t for _, t in monthly_totals) / len(monthly_totals)
    avg_daily = avg_monthly / _DAYS_PER_MONTH

    logger.info(f"Monthly expenses (fresh): ${avg_monthly:,.2f}/mo (${avg_daily:,.2f}/day)")
    return avg_daily, avg_monthly
