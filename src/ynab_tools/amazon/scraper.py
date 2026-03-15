"""Amazon session management and order/transaction retrieval.

The amazonorders and cache_decorator packages are optional dependencies
(installed via ``pip install ynab-tools[amazon]``).  Imports are deferred
to method bodies so that modules which only need the ``AmazonOrder`` model
(matcher, sync, tests) can import it without those heavy deps.
"""

from __future__ import annotations

import os
import warnings
from datetime import date
from decimal import Decimal
from typing import Any

from loguru import logger
from pydantic import AnyUrl, BaseModel, Field

from ynab_tools.config.settings import get_settings
from ynab_tools.exceptions import AmazonAuthError


class AmazonOrder(BaseModel):
    """Amazon transaction matched to its order details."""

    completed_date: date
    transaction_total: Decimal = Field(description="Positive value (charge amount)")
    order_total: Decimal
    order_number: str
    order_link: AnyUrl
    items: list[Any] = Field(default_factory=list)

    model_config = {"arbitrary_types_allowed": True}

    @classmethod
    def from_transaction_and_orders(
        cls,
        orders_dict: dict[str, Any],
        transaction: Any,
    ) -> AmazonOrder:
        """Create from an amazon-orders Transaction matched to its Order."""
        order = orders_dict.get(transaction.order_number)  # type: ignore[attr-defined]
        if order is None:
            msg = f"Order {transaction.order_number} not found"  # type: ignore[attr-defined]
            raise ValueError(msg)

        # Invert transaction_total: amazon-orders stores as negative (charge)
        raw_total = transaction.grand_total  # type: ignore[attr-defined]
        return cls(
            completed_date=transaction.completed_date,  # type: ignore[attr-defined]
            transaction_total=-Decimal(str(raw_total)),
            order_total=Decimal(str(order.grand_total)),  # type: ignore[attr-defined]
            order_number=order.order_number,  # type: ignore[attr-defined]
            order_link=order.order_details_link,  # type: ignore[attr-defined]
            items=order.items,  # type: ignore[attr-defined]
        )


def _normalized_years(years: list[str] | None) -> list[str]:
    """Normalize year strings to 4-digit format."""
    if years is None:
        return [str(date.today().year)]

    result: list[str] = []
    for year in years:
        if len(year) == 2:
            result.append("20" + year)
        elif len(year) == 4:
            result.append(year)
        else:
            msg = f"Year must be 2 or 4 digits, got: {year!r}"
            raise ValueError(msg)
    return result


class AmazonTransactionRetriever:
    """Retrieves Amazon transactions linked to their orders.

    Uses cache_decorator for 2h pickle caching of Amazon API results.
    """

    def __init__(
        self,
        *,
        username: str | None = None,
        password: str | None = None,
        otp_secret_key: str | None = None,
        debug: bool = False,
        order_years: list[str] | None = None,
        transaction_days: int = 31,
        force_refresh: bool = False,
    ) -> None:
        s = get_settings()
        self._username = username or s.amazon_user
        self._password = password or s.amazon_password.get_secret_value()
        self._otp_secret_key = otp_secret_key
        if self._otp_secret_key is None and s.amazon_otp_secret_key:
            self._otp_secret_key = s.amazon_otp_secret_key.get_secret_value()
        self._debug = debug or s.amazon_debug
        self._full_details = s.amazon_full_details
        self._order_years = _normalized_years(order_years)
        self._transaction_days = transaction_days
        self._force_refresh = force_refresh
        self._memo: dict[str, Any] = {}

    def get_transactions(self) -> list[AmazonOrder]:
        """Get Amazon transactions linked to their orders."""
        # Lazy import: cache_decorator is an optional dep (ynab-tools[amazon])
        warnings.filterwarnings("ignore", message="invalid escape sequence", module="cache_decorator")
        from cache_decorator import Cache

        # Build cached wrapper on first call
        if not hasattr(self, "_cached_fn"):

            @Cache(
                validity_duration="2h",
                enable_cache_arg_name="use_cache",
                cache_path=os.environ.get("AMAZON_CACHE_DIR", "/tmp/ynab-tools/amazon") + "/transactions_{_hash}.pkl",
            )
            def _get(order_years: list[str], transaction_days: int, *, use_cache: bool = True) -> list[AmazonOrder]:
                return self._build_orders()

            self._cached_fn = _get

        return self._cached_fn(
            order_years=self._order_years,
            transaction_days=self._transaction_days,
            use_cache=not self._force_refresh,
        )

    def _build_orders(self) -> list[AmazonOrder]:
        """Fetch orders + transactions from Amazon and merge them."""
        orders_dict = {
            order.order_number: order  # type: ignore[attr-defined]
            for order in self._fetch_orders()
        }
        transactions = self._fetch_transactions()

        result: list[AmazonOrder] = []
        for txn in transactions:
            try:
                result.append(AmazonOrder.from_transaction_and_orders(orders_dict, txn))
            except ValueError:
                logger.debug(
                    f"Transaction {txn.order_number} not found in retrieved orders"  # type: ignore[attr-defined]
                )
        return result

    def _fetch_orders(self) -> list[Any]:
        from amazonorders.orders import AmazonOrders

        if "orders" in self._memo:
            return self._memo["orders"]

        amazon_orders = AmazonOrders(self._session())
        all_orders: list[Any] = []
        for year in self._order_years:
            all_orders.extend(
                amazon_orders.get_order_history(
                    year=year,  # type: ignore[arg-type]
                    full_details=self._full_details,
                )
            )
        all_orders.sort(key=lambda o: o.order_placed_date)  # type: ignore[attr-defined]
        self._memo["orders"] = all_orders
        return all_orders

    def _fetch_transactions(self) -> list[Any]:
        from amazonorders.transactions import AmazonTransactions

        if "transactions" in self._memo:
            return self._memo["transactions"]

        txns = AmazonTransactions(amazon_session=self._session()).get_transactions(days=self._transaction_days)
        txns.sort(key=lambda t: t.completed_date)  # type: ignore[attr-defined]
        self._memo["transactions"] = txns
        return txns

    def _session(self) -> Any:
        from amazonorders.session import AmazonSession

        if "session" in self._memo:
            return self._memo["session"]

        session = AmazonSession(
            username=self._username,
            password=self._password,
            debug=self._debug,
            otp_secret_key=self._otp_secret_key,
        )
        session.login()

        if not session.is_authenticated:  # type: ignore[attr-defined]
            raise AmazonAuthError("Amazon authentication failed")

        self._memo["session"] = session
        return session
