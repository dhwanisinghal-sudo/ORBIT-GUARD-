"""
OrbitGuard - copy existing users and watchlists from SQLite into Postgres
--------------------------------------------------------------------------
Run once when you switch an existing installation to Postgres:

    export ORBITGUARD_DATABASE_URL=postgresql://user:password@host:5432/orbitguard
    python migrate_sqlite_to_postgres.py                 # reads <ORBITGUARD_DATA_DIR>/orbitguard_users.db
    python migrate_sqlite_to_postgres.py --users-db /path/to/orbitguard_users.db
    python migrate_sqlite_to_postgres.py --dry-run       # only report what would be copied

* User ids are preserved, so existing login tokens (which carry the id) keep working.
* Only users and watchlist rows are copied. The TLE cache is not: it refills from CelesTrak by itself.
* It refuses to run when the Postgres users or watchlist table already has rows, so running it
  twice can never create duplicates.
* Watchlist rows that point to a user that does not exist are skipped and reported.
* All inserts happen in one transaction: either everything is copied or nothing is.
* The SQLite file is only read, never changed.
"""

import argparse
import sqlite3
import sys
from pathlib import Path

import config
import db


def _read_sqlite(path: Path) -> tuple[list[tuple], list[tuple]]:
    if not path.exists():
        raise SystemExit(f"SQLite users database not found: {path}")
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)      # read-only: the source is never modified
    try:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        users = (conn.execute("SELECT id, name, email, password_hash, created_at FROM users ORDER BY id").fetchall()
                 if "users" in tables else [])
        watch = (conn.execute("SELECT user_id, norad_id, name, added_at FROM watchlist").fetchall()
                 if "watchlist" in tables else [])
    finally:
        conn.close()
    return users, watch


def migrate(sqlite_path: Path, dry_run: bool = False) -> dict:
    """Copy users + watchlist from `sqlite_path` into Postgres. Returns a summary dict."""
    if not db.is_postgres():
        raise SystemExit("ORBITGUARD_DATABASE_URL is not set; there is no Postgres target to copy into.")

    users, watch = _read_sqlite(Path(sqlite_path))
    user_ids = {u[0] for u in users}
    kept_watch = [w for w in watch if w[0] in user_ids]
    summary = {"users": len(users), "watchlist": len(kept_watch),
               "skipped_orphan_watchlist_rows": len(watch) - len(kept_watch), "dry_run": dry_run}

    conn = db.connect("users", None, dict_rows=True)   # creates the tables in Postgres if they are missing
    try:
        have_users = conn.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"]
        have_watch = conn.execute("SELECT COUNT(*) AS n FROM watchlist").fetchone()["n"]
        if have_users or have_watch:
            raise SystemExit(f"Postgres already has {have_users} users and {have_watch} watchlist rows; "
                             "refusing to copy on top of them. Use an empty database.")
        if dry_run:
            return summary

        conn.executemany(
            "INSERT INTO users (id, name, email, password_hash, created_at) VALUES (?, ?, ?, ?, ?)", users)
        conn.executemany(
            "INSERT INTO watchlist (user_id, norad_id, name, added_at) VALUES (?, ?, ?, ?)", kept_watch)
        # The ids were inserted explicitly, so move the id counter past them or the next signup would clash.
        conn.execute("SELECT setval(pg_get_serial_sequence('users', 'id'), "
                     "COALESCE((SELECT MAX(id) FROM users), 1), (SELECT MAX(id) FROM users) IS NOT NULL)")
        conn.commit()

        got_users = conn.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"]
        got_watch = conn.execute("SELECT COUNT(*) AS n FROM watchlist").fetchone()["n"]
        if (got_users, got_watch) != (len(users), len(kept_watch)):
            raise SystemExit(f"Count mismatch after copy: users {got_users}/{len(users)}, "
                             f"watchlist {got_watch}/{len(kept_watch)}")
    finally:
        conn.close()
    return summary


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--users-db", type=Path, default=config.DATA_DIR / "orbitguard_users.db",
                    help="SQLite users database to read (default: <ORBITGUARD_DATA_DIR>/orbitguard_users.db)")
    ap.add_argument("--dry-run", action="store_true", help="report what would be copied, change nothing")
    args = ap.parse_args(argv)

    s = migrate(args.users_db, dry_run=args.dry_run)
    verb = "Would copy" if s["dry_run"] else "Copied"
    print(f"{verb} {s['users']} users and {s['watchlist']} watchlist rows.")
    if s["skipped_orphan_watchlist_rows"]:
        print(f"Skipped {s['skipped_orphan_watchlist_rows']} watchlist rows whose user does not exist.")
    db.close_pool()
    return 0


if __name__ == "__main__":
    sys.exit(main())
