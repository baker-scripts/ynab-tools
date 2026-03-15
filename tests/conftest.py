"""Shared test fixtures."""

from __future__ import annotations

import pytest


@pytest.fixture
def tmp_cache_dir(tmp_path):
    """Provide a temporary directory for cache files."""
    return str(tmp_path / "cache")
