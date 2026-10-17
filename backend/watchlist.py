"""
OrbitGuard - per-user satellite watchlist
------------------------------------------
Logged-in users save the satellites they care about. Every route requires a
valid JWT (see auth.py), and each user only ever sees their own list.

Endpoints (wired up in main.py):
    POST   /watchlist             -> add a satellite  {norad_id, name?}
    GET    /watchlist             -> list my satellites (?live=true adds current position)
    DELETE /watchlist/{norad_id}  -> remove a satellite
    GET    /watchlist/alerts      -> upcoming close approaches involving my satellites
"""

import sqlite3
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

import auth
import cache
import conjunction_window as conjw
import forecast_service as svc
import ml_risk
import orbit_engine as engine
from ratelimit import SlidingWindowLimiter

router = APIRouter(prefix="/watchlist", tags=["watchlist"])

# Screening the whole catalog is the most expensive thing this API does, so cap it per user.
_alerts_limiter = SlidingWindowLimiter(max_events=6, window_seconds=60)


def reset_rate_limits() -> None:
    """Forget the alerts rate-limit counters (used by tests)."""
    _alerts_limiter.reset()


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
        except sqlite3.IntegrityError as exc:
            if "FOREIGN KEY" in str(exc):   # enforced now that PRAGMA foreign_keys=ON
                raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User no longer exists")
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
    if live and items:
        # One cache lookup for the whole list; only misses go to CelesTrak (a few in parallel).
        # One bad satellite must not break the list.
        tles, errors, metas = cache.get_tles_by_ids([i["norad_id"] for i in items], engine.fetch_tle)
        for item in items:
            nid = item["norad_id"]
            if nid in errors:
                item["live_error"] = str(errors[nid])
                continue
            item["data_source"] = metas[nid]["source"]
            try:
                item.update({k: v for k, v in engine.tle_age_info(tles[nid]).items()})
                pos = engine.propagate(tles[nid])
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


_RISK_RANK = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}


def _watched_ids(user_id: int) -> list[dict]:
    conn = _conn()
    try:
        rows = conn.execute(
            "SELECT norad_id, name FROM watchlist WHERE user_id = ? ORDER BY added_at", (user_id,)
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


def _norad(tle: dict) -> int | None:
    try:
        return int(tle["line1"][2:7])
    except Exception:
        return None


@router.get("/alerts")
def watchlist_alerts(
    group: str = "active",
    hours: float = 24.0,
    threshold_km: float = 5.0,
    step_seconds: float = 60.0,
    include_coorbiting: bool = False,
    start: str | None = None,
    ml: bool = False,
    user: dict = Depends(auth.get_current_user),
):
    """
    Upcoming close approaches (with time of closest approach) involving the satellites
    on MY watchlist, screened against every object in `group` (default: the active catalog).

    Query params are the same as /conjunctions/forecast. The response also lists each
    watched satellite with its own alert count, so "no alerts" can be told apart from
    "could not check": a satellite whose TLE could not be fetched or propagated has
    status "unavailable" and a reason.
    """
    wait = _alerts_limiter.hit(f"user:{user['id']}")
    if wait:
        seconds = int(wait) + 1
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS,
                            f"Too many alert checks. Try again in {seconds} s.",
                            headers={"Retry-After": str(seconds)})
    start_dt = svc.validate_window_params(hours, threshold_km, step_seconds, start)
    ref = start_dt or datetime.now(timezone.utc)

    watched = _watched_ids(user["id"])
    base = {"window_start_utc": ref.isoformat(), "hours": hours, "threshold_km": threshold_km,
            "step_seconds": step_seconds, "group": group, "ml": ml, "watchlist_count": len(watched)}
    if not watched:
        return {**base, "satellites": [], "count": 0, "conjunctions": [],
                "warnings": ["Your watchlist is empty; add satellites with POST /watchlist"]}

    try:
        # 1. the user's own satellites (cache first, only misses go to CelesTrak)
        wl_tles, wl_errors, wl_metas = cache.get_tles_by_ids([w["norad_id"] for w in watched],
                                                             engine.fetch_tle)
        # 2. everything they could collide with
        group_tles, cache_meta = cache.get_tles(group=group, fetch_fn=engine.fetch_many,
                                                return_meta=True)
        # one TLE per object; the watchlist's copy wins so a satellite is never in there twice
        merged = {}
        for t in group_tles:
            nid = _norad(t)
            if nid is not None:
                merged[nid] = t
        merged.update(wl_tles)
        all_tles = list(merged.values())
        svc.check_work(len(all_tles), hours, step_seconds)

        # 3. can each watched satellite actually be propagated? (else "no alerts" would mislead)
        sats, focus = {}, set()
        for w in watched:
            nid = w["norad_id"]
            entry = {"norad_id": nid, "name": w["name"], "status": "ok", "alert_count": 0,
                     "closest_miss_km": None, "next_tca_utc": None, "highest_risk": None}
            if nid in wl_errors:
                entry.update(status="unavailable", reason=f"TLE unavailable: {wl_errors[nid]}")
            else:
                try:
                    pos = engine.propagate(wl_tles[nid], ref)
                    entry["name"] = entry["name"] or pos["name"]
                    entry["tle_status"] = pos["tle_status"]
                    entry["tle_age_days"] = pos["tle_age_days"]
                    focus.add(nid)
                except Exception as exc:
                    entry.update(status="unavailable", reason=str(exc))
            sats[nid] = entry

        out = {"conjunctions": [], "objects_checked": 0, "objects_unpropagatable": 0,
               "candidate_pairs": 0, "excluded_coorbiting_pairs": 0}
        if focus:
            out = conjw.find_conjunctions_in_window(
                all_tles, start=start_dt, hours=hours, threshold_km=threshold_km,
                step_seconds=step_seconds, include_coorbiting=include_coorbiting,
                focus_norad_ids=focus,
            )
        results = out["conjunctions"]
        if ml:
            results = ml_risk.score_conjunctions(results)

        staleness, unreliable_events = svc.annotate_tle_age(results, all_tles, ref)
        results.sort(key=lambda c: c["tca_utc"])      # an alert feed: soonest first

        for c in results:
            hits = [c[k]["norad_id"] for k in ("object_1", "object_2") if c[k]["norad_id"] in focus]
            c["watched_norad_ids"] = hits
            for nid in hits:
                e = sats[nid]
                e["alert_count"] += 1
                if e["closest_miss_km"] is None or c["miss_distance_km"] < e["closest_miss_km"]:
                    e["closest_miss_km"] = c["miss_distance_km"]
                if e["next_tca_utc"] is None or c["tca_utc"] < e["next_tca_utc"]:
                    e["next_tca_utc"] = c["tca_utc"]
                if e["highest_risk"] is None or _RISK_RANK[c["risk_level"]] > _RISK_RANK[e["highest_risk"]]:
                    e["highest_risk"] = c["risk_level"]

        warnings = svc.data_quality_warnings(staleness, out["objects_unpropagatable"], cache_meta)
        unavailable = [e for e in sats.values() if e["status"] == "unavailable"]
        if unavailable:
            warnings.append(f"{len(unavailable)} watched satellite(s) could not be checked; "
                            "see their reason in 'satellites'")
        if unreliable_events:
            warnings.append(svc.unreliable_note(unreliable_events))

        return {
            **base,
            "satellites": list(sats.values()),
            "objects_checked": out["objects_checked"],
            "objects_unpropagatable": out["objects_unpropagatable"],
            "candidate_pairs": out["candidate_pairs"],
            "excluded_coorbiting_pairs": out["excluded_coorbiting_pairs"],
            "tle_staleness": staleness,
            "cache": cache_meta,
            "warnings": warnings,
            "count": len(results),
            "conjunctions": results,
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise svc.http_error(exc, "Failed to compute watchlist alerts")
