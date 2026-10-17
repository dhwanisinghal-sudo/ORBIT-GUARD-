"""
OrbitGuard - SQLite TLE cache
------------------------------
Caches fetched TLEs on disk so repeated requests don't re-hit CelesTrak
(which rate-limits clients that ask for the same data too often).

Two layers, both with the same TTL:
  * group cache   - a whole CelesTrak group ("stations", "active", ...)
  * single cache  - one object by NORAD ID (used by /objects/{id}, /trajectory,
                    /what-if and /watchlist?live=true)

If CelesTrak is unreachable and an expired copy exists (younger than
MAX_STALE_SERVE_SECONDS), the expired copy is served instead of failing, and the
metadata says so (source == "stale_cache"). "Not found" and bad-data errors are
never masked this way.

Every read can also return metadata describing where the data came from:
    {"source": "cache" | "upstream" | "stale_cache",
     "fetched_at_utc": "...", "age_seconds": 12.3}
"""

import json
import logging
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import requests

import config

log = logging.getLogger("orbitguard.cache")

DB_PATH = config.DATA_DIR / "orbitguard_cache.db"
CACHE_TTL_SECONDS = 60 * 30            # CelesTrak refreshes element sets roughly every 2 h
MAX_STALE_SERVE_SECONDS = 60 * 60 * 24  # never serve an expired copy older than a day
FETCH_WORKERS = 4                       # parallel single-object fetches (be polite to CelesTrak)


def _get_conn():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")   # concurrent requests: readers don't block the writer
    conn.execute("""
        CREATE TABLE IF NOT EXISTS tle_cache (
            group_name TEXT PRIMARY KEY,
            tles_json TEXT NOT NULL,
            fetched_at REAL NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS tle_single_cache (
            norad_id INTEGER PRIMARY KEY,
            tle_json TEXT NOT NULL,
            fetched_at REAL NOT NULL
        )
    """)
    return conn


def _meta(source: str, fetched_at: float) -> dict:
    return {
        "source": source,
        "fetched_at_utc": datetime.fromtimestamp(fetched_at, timezone.utc).isoformat(),
        "age_seconds": round(max(0.0, time.time() - fetched_at), 1),
    }


# ----------------------------------------------------------------------------
# group cache
# ----------------------------------------------------------------------------
def get_tles(group: str, fetch_fn, limit: int | None = None, force_refresh: bool = False,
             return_meta: bool = False):
    """
    Return TLEs for a group, using the SQLite cache when it's still fresh.

    The cache always stores the FULL group; `limit` is applied only when
    returning results. (Caching a limited fetch would make a later, larger
    request silently return the truncated list.)

    group: CelesTrak group name, used as the cache key
    fetch_fn: called as fetch_fn(group=..., limit=None) on a cache miss
    limit: cap on how many TLEs are returned to the caller
    force_refresh: bypass the cache and hit CelesTrak regardless of age
    return_meta: return (tles, meta) instead of just tles
    """
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT tles_json, fetched_at FROM tle_cache WHERE group_name = ?", (group,)
        ).fetchone()
        now = time.time()

        if row and not force_refresh and now - row[1] < CACHE_TTL_SECONDS:
            tles, fetched_at, source = json.loads(row[0]), row[1], "cache"
        else:
            try:
                tles = fetch_fn(group=group, limit=None)   # whole group, never a truncated one
            except requests.RequestException as exc:
                if row and now - row[1] < MAX_STALE_SERVE_SECONDS:
                    log.warning("CelesTrak unreachable for group %s (%s); serving cached copy", group, exc)
                    tles, fetched_at, source = json.loads(row[0]), row[1], "stale_cache"
                else:
                    raise
            else:
                fetched_at, source = time.time(), "upstream"
                conn.execute(
                    "INSERT OR REPLACE INTO tle_cache (group_name, tles_json, fetched_at) VALUES (?, ?, ?)",
                    (group, json.dumps(tles), fetched_at),
                )
                conn.commit()

        out = tles[:limit] if limit else tles
        return (out, _meta(source, fetched_at)) if return_meta else out
    finally:
        conn.close()


# ----------------------------------------------------------------------------
# single-object cache
# ----------------------------------------------------------------------------
def get_tles_by_ids(norad_ids, fetch_fn, force_refresh: bool = False):
    """
    Fetch TLEs for several NORAD IDs with as few CelesTrak requests as possible.

    Returns (tles, errors, metas), each a dict keyed by NORAD ID:
      tles   - id -> {"name", "line1", "line2"}
      errors - id -> the exception that prevented getting this one (others still succeed)
      metas  - id -> cache metadata (see module docstring)

    Cached entries cost nothing; misses are fetched in parallel (FETCH_WORKERS at a
    time) and written back in one transaction.
    """
    ids = list(dict.fromkeys(int(i) for i in norad_ids))
    tles, errors, metas = {}, {}, {}
    if not ids:
        return tles, errors, metas

    conn = _get_conn()
    try:
        rows = {}
        for nid in ids:
            row = conn.execute(
                "SELECT tle_json, fetched_at FROM tle_single_cache WHERE norad_id = ?", (nid,)
            ).fetchone()
            if row:
                rows[nid] = row
    finally:
        conn.close()

    now = time.time()
    missing = []
    for nid in ids:
        row = rows.get(nid)
        if row and not force_refresh and now - row[1] < CACHE_TTL_SECONDS:
            tles[nid], metas[nid] = json.loads(row[0]), _meta("cache", row[1])
        else:
            missing.append(nid)

    if not missing:
        return tles, errors, metas

    def _fetch(nid):
        try:
            return nid, fetch_fn(nid), None
        except Exception as exc:  # reported per object, never raised from a worker
            return nid, None, exc

    if len(missing) == 1:
        fetched = [_fetch(missing[0])]
    else:
        with ThreadPoolExecutor(max_workers=min(FETCH_WORKERS, len(missing))) as pool:
            fetched = list(pool.map(_fetch, missing))

    to_store = []
    for nid, tle, exc in fetched:
        if exc is None:
            ts = time.time()
            tles[nid], metas[nid] = tle, _meta("upstream", ts)
            to_store.append((nid, json.dumps(tle), ts))
        elif (isinstance(exc, requests.RequestException)
              and nid in rows and now - rows[nid][1] < MAX_STALE_SERVE_SECONDS):
            log.warning("CelesTrak unreachable for %s (%s); serving cached copy", nid, exc)
            tles[nid], metas[nid] = json.loads(rows[nid][0]), _meta("stale_cache", rows[nid][1])
        else:
            errors[nid] = exc

    if to_store:
        conn = _get_conn()
        try:
            conn.executemany(
                "INSERT OR REPLACE INTO tle_single_cache (norad_id, tle_json, fetched_at) VALUES (?, ?, ?)",
                to_store,
            )
            conn.commit()
        finally:
            conn.close()
    return tles, errors, metas


def get_tle(norad_id: int, fetch_fn, force_refresh: bool = False, return_meta: bool = False):
    """One object's TLE through the single-object cache. Raises whatever fetch_fn raised."""
    tles, errors, metas = get_tles_by_ids([norad_id], fetch_fn, force_refresh=force_refresh)
    nid = int(norad_id)
    if nid in errors:
        raise errors[nid]
    return (tles[nid], metas[nid]) if return_meta else tles[nid]


# ----------------------------------------------------------------------------
# status
# ----------------------------------------------------------------------------
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


def single_cache_status(norad_id: int) -> dict | None:
    """Cache metadata for one object, or None if it isn't cached."""
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT fetched_at FROM tle_single_cache WHERE norad_id = ?", (int(norad_id),)
        ).fetchone()
        if not row:
            return None
        age = time.time() - row[0]
        return {"norad_id": int(norad_id), "fetched_at": row[0],
                "age_seconds": round(age, 1), "is_fresh": age < CACHE_TTL_SECONDS}
    finally:
        conn.close()
