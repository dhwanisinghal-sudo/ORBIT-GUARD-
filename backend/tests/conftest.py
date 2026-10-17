"""Shared test setup. Runs before any test module imports the app."""
import os

# The app refuses to start without a real secret (config.load_secret), so give tests one.
os.environ.setdefault("ORBITGUARD_SECRET", "test-only-secret-" + "x" * 32)

import pytest

import alert_hub
import auth
import cache
import db
import watchlist


@pytest.fixture(autouse=True)
def isolated_state(tmp_path, monkeypatch):
    """Keep every test off the real databases and start each with clean rate limits."""
    monkeypatch.setattr(cache, "DB_PATH", tmp_path / "cache.db")
    monkeypatch.setattr(auth, "DB_PATH", tmp_path / "users.db")
    auth.reset_rate_limits()
    watchlist.reset_rate_limits()
    alert_hub.reset_rate_limits()

    if db.is_postgres():
        # Postgres is one shared database (not a fresh temp file per test), so empty it instead.
        conn = db.connect("users", None)
        conn.execute("TRUNCATE users, watchlist, tle_cache, tle_single_cache RESTART IDENTITY CASCADE")
        conn.commit()
        conn.close()
