"""
OrbitGuard - database access (SQLite by default, Postgres when DATABASE_URL is set)
-----------------------------------------------------------------------------------
auth.py, watchlist.py, alert_hub.py and cache.py all go through connect() so the
choice of database lives in one place.

    * ORBITGUARD_DATABASE_URL unset  -> SQLite files in ORBITGUARD_DATA_DIR (as before).
      Two files: users + watchlist in one, the TLE cache in the other.
    * ORBITGUARD_DATABASE_URL=postgresql://...  -> one Postgres database holds all four
      tables, through a small connection pool (ORBITGUARD_DB_POOL_SIZE connections).

Callers write plain SQL with "?" placeholders and upserts as INSERT ... ON CONFLICT
(valid in both databases); the Postgres wrapper turns "?" into "%s". Row access:
connect(..., dict_rows=True) gives rows that support row["col"] and dict(row);
dict_rows=False gives plain tuples (row[0]).

Postgres only changes where data is stored. Rate-limit counters and the alert job's
snapshots are still in process memory, so keep ONE worker (see README).
"""

import atexit
import logging
import sqlite3
import threading

import config

log = logging.getLogger("orbitguard.db")

# ----------------------------------------------------------------------------
# schema (one statement list per database kind and dialect)
# ----------------------------------------------------------------------------
_SQLITE_SCHEMA = {
    "users": [
        """CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL
        )""",
        """CREATE TABLE IF NOT EXISTS watchlist (
            user_id INTEGER NOT NULL,
            norad_id INTEGER NOT NULL,
            name TEXT,
            added_at TEXT NOT NULL,
            PRIMARY KEY (user_id, norad_id),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )""",
    ],
    "cache": [
        """CREATE TABLE IF NOT EXISTS tle_cache (
            group_name TEXT PRIMARY KEY,
            tles_json TEXT NOT NULL,
            fetched_at REAL NOT NULL
        )""",
        """CREATE TABLE IF NOT EXISTS tle_single_cache (
            norad_id INTEGER PRIMARY KEY,
            tle_json TEXT NOT NULL,
            fetched_at REAL NOT NULL
        )""",
    ],
}

_POSTGRES_SCHEMA = [
    """CREATE TABLE IF NOT EXISTS users (
        id BIGSERIAL PRIMARY KEY,
        name TEXT NOT NULL,
        email TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL,
        created_at TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS watchlist (
        user_id BIGINT NOT NULL,
        norad_id BIGINT NOT NULL,
        name TEXT,
        added_at TEXT NOT NULL,
        PRIMARY KEY (user_id, norad_id),
        FOREIGN KEY (user_id) REFERENCES users(id)
    )""",
    """CREATE TABLE IF NOT EXISTS tle_cache (
        group_name TEXT PRIMARY KEY,
        tles_json TEXT NOT NULL,
        fetched_at DOUBLE PRECISION NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS tle_single_cache (
        norad_id BIGINT PRIMARY KEY,
        tle_json TEXT NOT NULL,
        fetched_at DOUBLE PRECISION NOT NULL
    )""",
]
POSTGRES_TABLES = ("users", "watchlist", "tle_cache", "tle_single_cache")
_SCHEMA_LOCK_KEY = 7_245_001            # arbitrary id for the Postgres advisory lock

# ----------------------------------------------------------------------------
# errors
# ----------------------------------------------------------------------------
try:
    import psycopg
    from psycopg import errors as _pg_errors
    IntegrityError = (sqlite3.IntegrityError, psycopg.errors.IntegrityError)
except ImportError:                                  # SQLite-only install
    psycopg = None
    _pg_errors = None
    IntegrityError = (sqlite3.IntegrityError,)


def is_foreign_key_violation(exc: BaseException) -> bool:
    """True when an IntegrityError was a foreign-key failure (not a duplicate key)."""
    if isinstance(exc, sqlite3.IntegrityError):
        return "FOREIGN KEY" in str(exc)
    return _pg_errors is not None and isinstance(exc, _pg_errors.ForeignKeyViolation)


def is_postgres() -> bool:
    return bool(config.DATABASE_URL)


# ----------------------------------------------------------------------------
# Postgres connection wrapper + pool
# ----------------------------------------------------------------------------
_pool = None
_pool_lock = threading.Lock()


def _get_pool():
    global _pool
    if _pool is None:
        with _pool_lock:
            if _pool is None:
                if psycopg is None:
                    raise RuntimeError("ORBITGUARD_DATABASE_URL is set but psycopg is not installed "
                                       "(pip install -r requirements.txt)")
                from psycopg_pool import ConnectionPool
                pool = ConnectionPool(config.DATABASE_URL, min_size=1,
                                      max_size=config.DB_POOL_SIZE, open=False,
                                      kwargs={"connect_timeout": 10})
                pool.open(wait=True, timeout=15)       # fail at first use with a clear error
                _init_postgres_schema(pool)
                _pool = pool
                atexit.register(close_pool)        # scripts and tests exit without a shutdown hook
    return _pool


def close_pool() -> None:
    """Close the Postgres pool (app shutdown, tests, reconfiguration)."""
    global _pool
    with _pool_lock:
        if _pool is not None:
            _pool.close()
            _pool = None


def _init_postgres_schema(pool) -> None:
    """Create the tables once per process; the advisory lock keeps two starting workers apart."""
    with pool.connection() as conn:
        conn.execute("SELECT pg_advisory_lock(%s)", (_SCHEMA_LOCK_KEY,))
        try:
            for stmt in _POSTGRES_SCHEMA:
                conn.execute(stmt)
            conn.commit()
        finally:
            conn.rollback()                  # a failed statement leaves the transaction aborted
            conn.execute("SELECT pg_advisory_unlock(%s)", (_SCHEMA_LOCK_KEY,))
            conn.commit()


class _PgConn:
    """Gives a pooled psycopg connection the small sqlite3-style API the app uses."""

    def __init__(self, pool, conn, dict_rows: bool):
        from psycopg.rows import dict_row, tuple_row
        self._pool, self._conn = pool, conn
        conn.row_factory = dict_row if dict_rows else tuple_row

    @staticmethod
    def _q(sql: str) -> str:
        return sql.replace("?", "%s")

    def execute(self, sql, params=()):
        return self._conn.execute(self._q(sql), params)

    def executemany(self, sql, seq):
        cur = self._conn.cursor()
        cur.executemany(self._q(sql), seq)
        return cur

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        """Give the connection back to the pool (anything uncommitted is rolled back)."""
        try:
            self._conn.rollback()
        finally:
            self._pool.putconn(self._conn)


# ----------------------------------------------------------------------------
# public entry point
# ----------------------------------------------------------------------------
def connect(kind: str, sqlite_path, dict_rows: bool = False):
    """
    Open a connection for `kind` ("users" or "cache"); the tables exist when it returns.
    Always close() it. sqlite_path is only used when ORBITGUARD_DATABASE_URL is not set.
    """
    if kind not in _SQLITE_SCHEMA:
        raise ValueError(f"unknown database kind {kind!r}")

    if is_postgres():
        pool = _get_pool()
        return _PgConn(pool, pool.getconn(timeout=30), dict_rows)

    conn = sqlite3.connect(sqlite_path, timeout=10)
    if dict_rows:
        conn.row_factory = sqlite3.Row
    if kind == "users":
        conn.execute("PRAGMA foreign_keys=ON")     # off by default in SQLite; the watchlist FK needs it
    conn.execute("PRAGMA journal_mode=WAL")        # readers don't block the writer
    for stmt in _SQLITE_SCHEMA[kind]:
        conn.execute(stmt)
    return conn
