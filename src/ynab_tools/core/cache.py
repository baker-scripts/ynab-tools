"""JSON disk cache with fcntl file locking."""

from __future__ import annotations

import fcntl
import json
import os
import time
from pathlib import Path
from typing import Any

from loguru import logger


def cache_path(cache_dir: str, name: str) -> str:
    """Return a cache file path, ensuring the directory exists."""
    os.makedirs(cache_dir, exist_ok=True)
    return os.path.join(cache_dir, name)


def read_cache(filepath: str, ttl_seconds: int) -> dict[str, Any] | None:
    """Read JSON from a cache file if it exists and is within TTL.

    Returns None if the cache is missing, expired, or corrupt.
    Uses file locking for shared cache safety.
    """
    try:
        with open(filepath) as f:
            fcntl.flock(f, fcntl.LOCK_SH)
            try:
                data = json.load(f)
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)
        cached_at = data.get("cached_at", 0)
        if time.time() - cached_at > ttl_seconds:
            return None
        return data
    except FileNotFoundError:
        return None
    except (json.JSONDecodeError, KeyError):
        logger.warning(f"Corrupt cache file: {filepath}")
        return None


def write_cache(filepath: str, data: dict[str, Any]) -> None:
    """Write JSON data to a cache file with file locking."""
    stamped = {**data, "cached_at": time.time()}
    Path(filepath).parent.mkdir(parents=True, exist_ok=True)
    with open(filepath, "w") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            json.dump(stamped, f)
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)
