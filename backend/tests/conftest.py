"""Shared test setup. Runs before any test module imports the app."""
import os

# The app refuses to start without a real secret (config.load_secret), so give tests one.
os.environ.setdefault("ORBITGUARD_SECRET", "test-only-secret-" + "x" * 32)

import pytest

import auth
import cache
import watchlist


@pytest.fixture(autouse=True)
def isolated_state(tmp_path, monkeypatch):
    """Keep every test off the real databases and start each with clean rate limits."""
    monkeypatch.setattr(cache, "DB_PATH", tmp_path / "cache.db")
    monkeypatch.setattr(auth, "DB_PATH", tmp_path / "users.db")
    auth.reset_rate_limits()
    watchlist.reset_rate_limits()
