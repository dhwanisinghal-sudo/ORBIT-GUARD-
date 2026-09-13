"""
OrbitGuard - SQLite cache (Week 6)
-------------------------------------
Caches fetched TLEs on disk so repeated requests don't re-hit CelesTrak.
TLEs are only refreshed after CACHE_TTL_SECONDS has passed for that group.

Usage from main.py:
    import cache
    tles = cache.get_tles(group="stations", fetch_fn=engine.fetch_many)
"""

import sqlite3
import time
import json
from pathlib import Path

DB_PATH = Path(__file__).parent / "orbitguard_cache.db"
CACHE_TTL_SECONDS = 60 * 30  # 30 minutes - TLEs don't change that fast


def _get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS tle_cache (
            group_name TEXT PRIMARY KEY,
            tles_json TEXT NOT NULL,
            fetched_at REAL NOT NULL
        )
    """)
    return conn


def get_tles(group: str, fetch_fn, limit: int | None = None, force_refresh: bool = False):
    """
    Return TLEs for a group, using the SQLite cache when it's still fresh.

    group: CelesTrak group name, used as the cache key
    fetch_fn: the function to call on a cache miss (e.g. engine.fetch_many)
    limit: passed through to fetch_fn on a cache miss
    force_refresh: bypass the cache and hit CelesTrak regardless of age
    """
    conn = _get_conn()
    try:
        if not force_refresh:
            row = conn.execute(
                "SELECT tles_json, fetched_at FROM tle_cache WHERE group_name = ?",
                (group,),
            ).fetchone()
            if row:
                tles_json, fetched_at = row
                age = time.time() - fetched_at
                if age < CACHE_TTL_SECONDS:
                    return json.loads(tles_json)

        # cache miss or stale - fetch fresh data
        tles = fetch_fn(group=group, limit=limit)
        conn.execute(
            "INSERT OR REPLACE INTO tle_cache (group_name, tles_json, fetched_at) VALUES (?, ?, ?)",
            (group, json.dumps(tles), time.time()),
        )
        conn.commit()
        return tles
    finally:
        conn.close()


def cache_status(group: str) -> dict | None:
    """Return cache metadata for a group, or None if nothing cached yet."""
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT fetched_at FROM tle_cache WHERE group_name = ?", (group,)
        ).fetchone()
        if not row:
            return None
        fetched_at = row[0]
        age = time.time() - fetched_at
        return {
            "group": group,
            "fetched_at": fetched_at,
            "age_seconds": round(age, 1),
            "is_fresh": age < CACHE_TTL_SECONDS,
        }
    finally:
        conn.close()
