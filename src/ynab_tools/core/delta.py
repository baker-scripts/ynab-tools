"""Delta sync for YNAB scheduled transactions using server_knowledge."""

from __future__ import annotations

from typing import Any

from loguru import logger

from ynab_tools.core.cache import cache_path, read_cache, write_cache
from ynab_tools.core.client import YnabClient
from ynab_tools.exceptions import YnabAPIError


def fetch_scheduled_transactions_delta(
    client: YnabClient,
    cache_dir: str,
) -> list[dict[str, Any]]:
    """Fetch scheduled transactions using delta sync (last_knowledge_of_server).

    On first call: full fetch, caches response + server_knowledge.
    On subsequent calls: sends ?last_knowledge_of_server=N, merges delta.
    Returns the full list of scheduled transaction dicts.
    """
    filepath = cache_path(cache_dir, f"delta_scheduled_{client.budget_id}.json")
    cached = read_cache(filepath, 86400 * 7)  # 7-day max TTL for delta base

    if cached and "server_knowledge" in cached and "transactions" in cached:
        sk = cached["server_knowledge"]
        if not isinstance(sk, int):
            logger.warning("Corrupt delta cache: server_knowledge is not an integer, doing full fetch")
            return _full_fetch(client, filepath)
        try:
            data = client.get(f"/budgets/{client.budget_id}/scheduled_transactions?last_knowledge_of_server={sk}")
        except YnabAPIError:
            # Delta failed — do a full fetch
            logger.warning("Delta sync failed, falling back to full fetch")
            return _full_fetch(client, filepath)

        # Merge delta into cached transactions
        txn_map = {t["id"]: t for t in cached["transactions"]}
        for txn in data.get("scheduled_transactions", []):
            if txn.get("deleted"):
                txn_map.pop(txn["id"], None)
            else:
                txn_map[txn["id"]] = txn

        merged = list(txn_map.values())
        new_sk = data.get("server_knowledge", sk)
        write_cache(filepath, {"server_knowledge": new_sk, "transactions": merged})
        logger.info(f"Scheduled transactions: delta sync (knowledge {sk} → {new_sk})")
        return merged

    # First run / cache miss — full fetch
    return _full_fetch(client, filepath)


def _full_fetch(client: YnabClient, filepath: str) -> list[dict[str, Any]]:
    """Perform a full fetch of scheduled transactions and cache them."""
    data = client.get(f"/budgets/{client.budget_id}/scheduled_transactions")
    write_cache(
        filepath,
        {
            "server_knowledge": data.get("server_knowledge", 0),
            "transactions": data["scheduled_transactions"],
        },
    )
    logger.info("Scheduled transactions: full fetch (no delta cache)")
    return data["scheduled_transactions"]
