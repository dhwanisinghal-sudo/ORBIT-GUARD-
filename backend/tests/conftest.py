"""Shared fixtures: keep every test off the real cache database."""
import pytest

import cache


@pytest.fixture(autouse=True)
def isolated_cache_db(tmp_path, monkeypatch):
    monkeypatch.setattr(cache, "DB_PATH", tmp_path / "cache.db")
