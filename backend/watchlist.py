"""
OrbitGuard - per-user satellite watchlist
------------------------------------------
Logged-in users save the satellites they care about. Every route requires a
valid JWT (see auth.py), and each user only ever sees their own list.

Endpoints (wired up in main.py):
    POST   /watchlist             -> add a satellite  {norad_id, name?}
    GET    /watchlist             -> list my satellites (?live=true adds current position)
    DELETE /watchlist/{norad_id}  -> remove a satellite
"""

import sqlite3
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

import auth
import orbit_engine as engine

router = APIRouter(prefix="/watchlist", tags=["watchlist"])


def _conn() -> sqlite3.Connection:
    conn = auth._get_conn()  # same database file as the users table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS watchlist (
            user_id INTEGER NOT NULL,
            norad_id INTEGER NOT NULL,
            name TEXT,
            added_at TEXT NOT NULL,
            PRIMARY KEY (user_id, norad_id),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)
    return conn


class WatchlistAdd(BaseModel):
    norad_id: int = Field(gt=0)
    name: str | None = Field(default=None, max_length=100)


@router.post("", status_code=status.HTTP_201_CREATED)
def add_to_watchlist(body: WatchlistAdd, user: dict = Depends(auth.get_current_user)):
    conn = _conn()
    try:
        try:
            conn.execute(
                "INSERT INTO watchlist (user_id, norad_id, name, added_at) VALUES (?, ?, ?, ?)",
                (user["id"], body.norad_id, body.name,
                 datetime.now(timezone.utc).isoformat()),
            )
            conn.commit()
        except sqlite3.IntegrityError:
            raise HTTPException(status.HTTP_409_CONFLICT, "Already in your watchlist")
    finally:
        conn.close()
    return {"norad_id": body.norad_id, "name": body.name}


@router.get("")
def get_watchlist(live: bool = False, user: dict = Depends(auth.get_current_user)):
    conn = _conn()
    try:
        rows = conn.execute(
            "SELECT norad_id, name, added_at FROM watchlist WHERE user_id = ? ORDER BY added_at",
            (user["id"],),
        ).fetchall()
    finally:
        conn.close()

    items = [dict(r) for r in rows]
    if live:
        # Attach the current position/altitude; one bad satellite must not break the list.
        for item in items:
            try:
                pos = engine.propagate(engine.fetch_tle(item["norad_id"]))
                item["name"] = item["name"] or pos["name"]
                item["altitude_km"] = pos["altitude_km"]
                item["position_km"] = pos["position_km"]
                item["timestamp_utc"] = pos["timestamp_utc"]
            except Exception as exc:
                item["live_error"] = str(exc)
    return {"count": len(items), "items": items}


@router.delete("/{norad_id}")
def remove_from_watchlist(norad_id: int, user: dict = Depends(auth.get_current_user)):
    conn = _conn()
    try:
        cur = conn.execute(
            "DELETE FROM watchlist WHERE user_id = ? AND norad_id = ?",
            (user["id"], norad_id),
        )
        conn.commit()
        if cur.rowcount == 0:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Not in your watchlist")
    finally:
        conn.close()
    return {"removed": norad_id}
