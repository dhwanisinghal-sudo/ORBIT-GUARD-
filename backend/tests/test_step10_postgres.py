"""
Step 10: optional Postgres storage (ORBITGUARD_DATABASE_URL).

The first group runs everywhere (config validation, SQL translation, SQLite behaviour).
The second group needs a real Postgres and is skipped unless ORBITGUARD_DATABASE_URL is set:

    ORBITGUARD_DATABASE_URL=postgresql://postgres@127.0.0.1:5432/orbitguard python -m pytest tests -q

The whole existing suite also runs against Postgres that way (conftest empties the tables per test).
"""
import sqlite3
import sys
import threading
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

import auth
import cache
import config
import db
import main
import migrate_sqlite_to_postgres as migrate

needs_postgres = pytest.mark.skipif(not db.is_postgres(), reason="set ORBITGUARD_DATABASE_URL to run")


# ======================= everywhere: config =======================
def test_database_url_unset_means_sqlite():
    assert config.database_url({}) is None
    assert config.database_url({"ORBITGUARD_DATABASE_URL": "   "}) is None


@pytest.mark.parametrize("url", ["postgresql://u:p@localhost:5432/orbit", "postgres://u@db/orbit"])
def test_database_url_accepts_postgres(url):
    assert config.database_url({"ORBITGUARD_DATABASE_URL": url}) == url


@pytest.mark.parametrize("url", ["sqlite:///x.db", "mysql://u@h/d", "localhost:5432/orbit", "orbit.db"])
def test_database_url_rejects_other_databases(url):
    with pytest.raises(RuntimeError, match="Postgres URL"):
        config.database_url({"ORBITGUARD_DATABASE_URL": url})


def test_pool_size_default_and_validation():
    assert config.db_pool_size({}) == 10
    assert config.db_pool_size({"ORBITGUARD_DB_POOL_SIZE": "25"}) == 25
    for bad in ("0", "101", "ten", "2.5"):
        with pytest.raises(RuntimeError, match="ORBITGUARD_DB_POOL_SIZE"):
            config.db_pool_size({"ORBITGUARD_DB_POOL_SIZE": bad})


# ======================= everywhere: db helpers =======================
def test_placeholders_are_translated_for_postgres():
    assert db._PgConn._q("SELECT * FROM t WHERE a = ? AND b = ?") == "SELECT * FROM t WHERE a = %s AND b = %s"


def test_unknown_database_kind_is_rejected():
    with pytest.raises(ValueError):
        db.connect("nope", None)


def test_integrity_error_covers_sqlite():
    assert issubclass(sqlite3.IntegrityError, db.IntegrityError)


@pytest.mark.skipif(db.is_postgres(), reason="SQLite behaviour")
def test_sqlite_connection_creates_tables_and_supports_dict_rows(tmp_path):
    conn = db.connect("users", tmp_path / "u.db", dict_rows=True)
    conn.execute("INSERT INTO users (name, email, password_hash, created_at) VALUES ('a', 'a@x.io', 'h', 'now')")
    conn.commit()
    row = conn.execute("SELECT id, name FROM users").fetchone()
    assert row["name"] == "a" and dict(row)["id"] == 1
    conn.close()
    cconn = db.connect("cache", tmp_path / "c.db")
    assert cconn.execute("SELECT COUNT(*) FROM tle_cache").fetchone()[0] == 0
    cconn.close()


@pytest.mark.skipif(db.is_postgres(), reason="SQLite behaviour")
def test_sqlite_foreign_key_violation_is_recognised(tmp_path):
    conn = db.connect("users", tmp_path / "u.db")
    with pytest.raises(db.IntegrityError) as e:
        conn.execute("INSERT INTO watchlist (user_id, norad_id, name, added_at) VALUES (999, 1, 'x', 'now')")
    assert db.is_foreign_key_violation(e.value)
    conn.execute("INSERT INTO users (name, email, password_hash, created_at) VALUES ('a', 'a@x.io', 'h', 'now')")
    with pytest.raises(db.IntegrityError) as e2:
        conn.execute("INSERT INTO users (name, email, password_hash, created_at) VALUES ('b', 'a@x.io', 'h', 'now')")
    assert not db.is_foreign_key_violation(e2.value)        # a duplicate email is not a foreign-key problem
    conn.close()


def test_migration_refuses_without_postgres_target(tmp_path):
    if db.is_postgres():
        pytest.skip("target is configured")
    with pytest.raises(SystemExit, match="ORBITGUARD_DATABASE_URL"):
        migrate.migrate(tmp_path / "nothing.db")


# ======================= Postgres only =======================
def _register(client, email="a@example.com", name="Ada"):
    return client.post("/auth/register", json={"name": name, "email": email, "password": "correct-horse-1"})


@needs_postgres
def test_register_login_me_and_duplicate_email():
    client = TestClient(main.app)
    r = _register(client)
    assert r.status_code == 201
    user_id = r.json()["user"]["id"]
    assert isinstance(user_id, int)
    assert _register(client).status_code == 409                      # unique violation -> 409
    login = client.post("/auth/login", json={"email": "a@example.com", "password": "correct-horse-1"})
    assert login.status_code == 200
    me = client.get("/auth/me", headers={"Authorization": f"Bearer {login.json()['access_token']}"})
    assert me.json()["email"] == "a@example.com" and me.json()["id"] == user_id


@needs_postgres
def test_watchlist_add_duplicate_list_remove():
    client = TestClient(main.app)
    h = {"Authorization": f"Bearer {_register(client).json()['access_token']}"}
    assert client.post("/watchlist", json={"norad_id": 25544, "name": "ISS"}, headers=h).status_code == 201
    assert client.post("/watchlist", json={"norad_id": 25544}, headers=h).status_code == 409
    items = client.get("/watchlist", headers=h).json()
    assert items["count"] == 1 and items["items"][0]["norad_id"] == 25544
    assert client.delete("/watchlist/25544", headers=h).status_code == 200
    assert client.delete("/watchlist/25544", headers=h).status_code == 404


@needs_postgres
def test_deleted_user_cannot_add_to_watchlist():
    client = TestClient(main.app)
    body = _register(client).json()
    h = {"Authorization": f"Bearer {body['access_token']}"}
    # The JWT is still valid, but its user row is gone.
    conn = auth._get_conn()
    conn.execute("DELETE FROM users WHERE id = ?", (body["user"]["id"],))
    conn.commit()
    conn.close()
    assert client.post("/watchlist", json={"norad_id": 1}, headers=h).status_code == 401


@needs_postgres
def test_foreign_key_violation_is_recognised():
    conn = auth._get_conn()
    with pytest.raises(db.IntegrityError) as e:
        conn.execute("INSERT INTO watchlist (user_id, norad_id, name, added_at) VALUES (999, 1, 'x', 'now')")
    assert db.is_foreign_key_violation(e.value)
    conn.close()


@needs_postgres
def test_pool_connection_is_clean_after_a_failed_statement():
    """A failed insert aborts the Postgres transaction; the connection must come back usable."""
    for _ in range(30):                                              # more checkouts than pool connections get reused
        conn = auth._get_conn()
        with pytest.raises(db.IntegrityError):
            conn.execute("INSERT INTO watchlist (user_id, norad_id, name, added_at) VALUES (999, 1, 'x', 'now')")
        conn.close()
        ok = auth._get_conn()
        assert ok.execute("SELECT 1 AS one").fetchone()["one"] == 1
        ok.close()


@needs_postgres
def test_uncommitted_work_is_rolled_back_on_close():
    conn = auth._get_conn()
    conn.execute("INSERT INTO users (name, email, password_hash, created_at) VALUES ('x', 'x@x.io', 'h', 'now')")
    conn.close()                                                     # no commit
    check = auth._get_conn()
    assert check.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"] == 0
    check.close()


@needs_postgres
def test_group_cache_upsert_overwrites(monkeypatch):
    calls = []

    def fetch(group, limit=None):
        calls.append(group)
        return [{"name": f"v{len(calls)}", "line1": "1", "line2": "2"}]

    first = cache.get_tles("stations", fetch)
    again = cache.get_tles("stations", fetch)                        # cache hit
    forced = cache.get_tles("stations", fetch, force_refresh=True)   # upsert over the existing row
    assert first[0]["name"] == "v1" and again[0]["name"] == "v1" and forced[0]["name"] == "v2"
    assert cache.get_tles("stations", fetch)[0]["name"] == "v2"
    conn = cache._get_conn()
    assert conn.execute("SELECT COUNT(*) FROM tle_cache").fetchone()[0] == 1
    conn.close()
    assert cache.cache_status("stations")["is_fresh"] is True


@needs_postgres
def test_single_cache_upsert_and_batch():
    def fetch(nid):
        return {"name": f"sat{nid}", "line1": "1", "line2": "2"}

    tles, errors, metas = cache.get_tles_by_ids([1, 2, 3], fetch)
    assert not errors and {m["source"] for m in metas.values()} == {"upstream"}
    tles, _, metas = cache.get_tles_by_ids([1, 2, 3], fetch)
    assert {m["source"] for m in metas.values()} == {"cache"}
    cache.get_tles_by_ids([2], fetch, force_refresh=True)            # upsert over an existing row
    assert cache.single_cache_status(2)["is_fresh"] is True


@needs_postgres
def test_concurrent_registrations_use_the_pool_safely():
    client = TestClient(main.app)
    results, lock = [], threading.Lock()

    def worker(i):
        r = client.post("/auth/register", json={"name": f"u{i}", "email": f"u{i}@example.com",
                                                 "password": "correct-horse-1"})
        with lock:
            results.append(r.status_code)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(24)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert results.count(201) + results.count(429) == 24 and results.count(201) >= 10
    conn = auth._get_conn()
    n = conn.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"]
    ids = [r["id"] for r in conn.execute("SELECT id FROM users").fetchall()]
    conn.close()
    assert n == results.count(201) and len(set(ids)) == n


# ----------------------- migration SQLite -> Postgres -----------------------
def _make_sqlite_source(path, orphan=False):
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE users (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, email TEXT NOT NULL UNIQUE,
                            password_hash TEXT NOT NULL, created_at TEXT NOT NULL);
        CREATE TABLE watchlist (user_id INTEGER NOT NULL, norad_id INTEGER NOT NULL, name TEXT, added_at TEXT NOT NULL,
                                PRIMARY KEY (user_id, norad_id));
        INSERT INTO users VALUES (3, 'Ada', 'ada@example.com', 'pbkdf2_sha256$1$aa$bb', '2026-01-01T00:00:00+00:00');
        INSERT INTO users VALUES (7, 'Bob', 'bob@example.com', 'pbkdf2_sha256$1$cc$dd', '2026-01-02T00:00:00+00:00');
        INSERT INTO watchlist VALUES (3, 25544, 'ISS', '2026-01-03T00:00:00+00:00');
        INSERT INTO watchlist VALUES (7, 20580, NULL, '2026-01-04T00:00:00+00:00');
    """)
    if orphan:
        conn.execute("INSERT INTO watchlist VALUES (99, 1, 'ghost', '2026-01-05T00:00:00+00:00')")
    conn.commit()
    conn.close()


@needs_postgres
def test_migration_copies_rows_keeps_ids_and_moves_the_sequence(tmp_path):
    src = tmp_path / "old_users.db"
    _make_sqlite_source(src, orphan=True)

    dry = migrate.migrate(src, dry_run=True)
    assert dry["users"] == 2 and dry["watchlist"] == 2 and dry["skipped_orphan_watchlist_rows"] == 1
    conn = auth._get_conn()
    assert conn.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"] == 0        # dry run changed nothing
    conn.close()

    out = migrate.migrate(src)
    assert out["users"] == 2 and out["watchlist"] == 2

    conn = auth._get_conn()
    users = {r["email"]: r for r in conn.execute("SELECT * FROM users").fetchall()}
    assert users["ada@example.com"]["id"] == 3 and users["bob@example.com"]["id"] == 7
    assert users["ada@example.com"]["password_hash"] == "pbkdf2_sha256$1$aa$bb"
    wl = conn.execute("SELECT user_id, norad_id, name FROM watchlist ORDER BY user_id").fetchall()
    assert [(r["user_id"], r["norad_id"], r["name"]) for r in wl] == [(3, 25544, "ISS"), (7, 20580, None)]
    conn.close()

    # A new signup must get an id after the copied ones, and an old user can still log in.
    client = TestClient(main.app)
    assert _register(client, email="new@example.com").json()["user"]["id"] == 8

    with pytest.raises(SystemExit, match="refusing"):                # never copies on top of existing rows
        migrate.migrate(src)


@needs_postgres
def test_migration_into_empty_source_leaves_sequence_starting_at_one(tmp_path):
    src = tmp_path / "empty.db"
    sqlite3.connect(src).close()
    assert migrate.migrate(src) == {"users": 0, "watchlist": 0, "skipped_orphan_watchlist_rows": 0, "dry_run": False}
    assert _register(TestClient(main.app)).json()["user"]["id"] == 1


@needs_postgres
def test_migration_missing_source_file(tmp_path):
    with pytest.raises(SystemExit, match="not found"):
        migrate.migrate(tmp_path / "missing.db")
