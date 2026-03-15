"""Tests for JSON disk cache with file locking."""

from __future__ import annotations

import json
import os
import time

from ynab_tools.core.cache import cache_path, read_cache, write_cache


class TestCachePath:
    def test_creates_directory(self, tmp_cache_dir):
        path = cache_path(tmp_cache_dir, "test.json")
        assert os.path.isdir(tmp_cache_dir)
        assert path == os.path.join(tmp_cache_dir, "test.json")

    def test_nested_directory(self, tmp_path):
        nested = str(tmp_path / "a" / "b" / "c")
        path = cache_path(nested, "deep.json")
        assert os.path.isdir(nested)
        assert path.endswith("deep.json")


class TestWriteAndReadCache:
    def test_roundtrip(self, tmp_cache_dir):
        path = cache_path(tmp_cache_dir, "data.json")
        data = {"key": "value", "count": 42}
        write_cache(path, data)

        result = read_cache(path, ttl_seconds=3600)
        assert result is not None
        assert result["key"] == "value"
        assert result["count"] == 42
        assert "cached_at" in result

    def test_ttl_expired(self, tmp_cache_dir):
        path = cache_path(tmp_cache_dir, "expired.json")
        data = {"key": "old"}
        write_cache(path, data)

        # Manually backdate cached_at
        with open(path) as f:
            cached = json.load(f)
        cached["cached_at"] = time.time() - 7200  # 2 hours ago
        with open(path, "w") as f:
            json.dump(cached, f)

        result = read_cache(path, ttl_seconds=3600)
        assert result is None

    def test_ttl_still_valid(self, tmp_cache_dir):
        path = cache_path(tmp_cache_dir, "valid.json")
        write_cache(path, {"key": "fresh"})

        result = read_cache(path, ttl_seconds=3600)
        assert result is not None
        assert result["key"] == "fresh"

    def test_missing_file(self, tmp_cache_dir):
        path = os.path.join(tmp_cache_dir, "nonexistent.json")
        result = read_cache(path, ttl_seconds=3600)
        assert result is None

    def test_corrupt_json(self, tmp_cache_dir):
        os.makedirs(tmp_cache_dir, exist_ok=True)
        path = os.path.join(tmp_cache_dir, "corrupt.json")
        with open(path, "w") as f:
            f.write("{invalid json content")

        result = read_cache(path, ttl_seconds=3600)
        assert result is None

    def test_overwrite(self, tmp_cache_dir):
        path = cache_path(tmp_cache_dir, "overwrite.json")
        write_cache(path, {"version": 1})
        write_cache(path, {"version": 2})

        result = read_cache(path, ttl_seconds=3600)
        assert result is not None
        assert result["version"] == 2

    def test_preserves_nested_data(self, tmp_cache_dir):
        path = cache_path(tmp_cache_dir, "nested.json")
        data = {
            "transactions": [{"id": "a", "amount": 100}, {"id": "b", "amount": 200}],
            "server_knowledge": 42,
        }
        write_cache(path, data)

        result = read_cache(path, ttl_seconds=3600)
        assert result is not None
        assert len(result["transactions"]) == 2
        assert result["server_knowledge"] == 42
