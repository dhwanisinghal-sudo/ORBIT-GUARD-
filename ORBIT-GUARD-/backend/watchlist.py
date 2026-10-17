"""
OrbitGuard - per-user satellite watchlist
------------------------------------------
Logged-in users save the satellites they care about. Every route requires a
valid JWT (see auth.py), and each user only ever sees their own list.

Endpoints (wired up in main.py):
    POST   /watchlist             -> add a satellite  {norad_id, name?}
    GET    /watchlist             -> list my satellites (?live=true adds current position)
    DELETE /watchlist/{norad_id}  -> remove a satellite
    GET    /watchlist/alerts      -> upcoming close approaches involving my satellites (computed now)
    GET    /watchlist/alerts/latest -> the same feed, precomputed by the background job (instant)
    (live push of the same feed: WebSocket /ws/alerts, see alert_hub.py)
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

import alert_hub
import alert_service
import auth
import cache
import db
import forecast_service as svc
import orbit_engine as engine
from ratelimit import SlidingWindowLimiter

router = APIRouter(prefix="/watchlist", tags=["watchlist"])

# Screening the whole catalog is the most expensive thing this API does, so cap it per user.
_alerts_limiter = SlidingWindowLimiter(max_events=6, window_seconds=60)


def reset_rate_limits() -> None:
    """Forget the alerts rate-limit counters (used by tests)."""
    _alerts_limiter.reset()


def _conn():
    return auth._get_conn()  # same database as the users table (the watchlist table is created with it)


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
        except db.IntegrityError as exc:
            if db.is_foreign_key_violation(exc):   # the user row is gone (foreign keys are enforced)
                raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User no longer exists")
            raise HTTPException(status.HTTP_409_CONFLICT, "Already in your watchlist")
    finally:
        conn.close()
    alert_hub.hub.mark_dirty(user["id"])          # the precomputed feed is now out of date
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
    alert_hub.hub.mark_dirty(user["id"])
    return {"removed": norad_id}


def _watched_ids(user_id: int) -> list[dict]:
    conn = _conn()
    try:
        rows = conn.execute(
            "SELECT norad_id, name FROM watchlist WHERE user_id = ? ORDER BY added_at", (user_id,)
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


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
    params = alert_service.Params(group=group, hours=hours, threshold_km=threshold_km,
                                  step_seconds=step_seconds, include_coorbiting=include_coorbiting,
                                  ml=ml, start_dt=start_dt)
    watched = _watched_ids(user["id"])
    try:
        scr = alert_service.screen({w["norad_id"] for w in watched}, params) if watched else None
        return alert_service.build_response(watched, scr, params)
    except HTTPException:
        raise
    except Exception as exc:
        raise svc.http_error(exc, "Failed to compute watchlist alerts")


@router.get("/alerts/latest")
def watchlist_alerts_latest(user: dict = Depends(auth.get_current_user)):
    """
    The alert feed the background job precomputed for me (default window; see the settings in
    config.py). Instant, because nothing is screened while you wait. The first call for a user
    returns 202 and starts the computation; call again (or open /ws/alerts) in a few seconds.
    """
    hub = alert_hub.hub
    if not hub.running:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                            "The background alert job is disabled; use GET /watchlist/alerts")
    snap = hub.latest(user["id"])
    hub.touch(user["id"])
    if snap is None:
        return JSONResponse({"status": "computing", "retry_after_seconds": 10}, status_code=202,
                            headers={"Retry-After": "10"})
    age = (datetime.now(timezone.utc) - datetime.fromisoformat(snap["computed_at_utc"])).total_seconds()
    return {**snap, "age_seconds": round(age, 1), "refresh_interval_seconds": hub.interval}
