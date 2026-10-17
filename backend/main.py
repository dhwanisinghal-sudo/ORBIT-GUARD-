"""
OrbitGuard - FastAPI backend (Week 6 endpoints, pulled forward)
-----------------------------------------------------------------
Run with:
    uvicorn main:app --reload

Then open http://127.0.0.1:8000/docs for interactive API docs (FastAPI
generates this automatically - it's a good way to hand this to your
frontend teammate without them needing to read your code).

See README.md for the full endpoint list, or open /docs when running.
"""

from datetime import datetime, timezone

import requests
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

import orbit_engine as engine
import conjunction as conj
import conjunction_window as conjw
import cache
import auth
import ml_risk
import watchlist

app = FastAPI(title="OrbitGuard API", version="0.3.0")
app.include_router(auth.router)
app.include_router(watchlist.router)

# Allow the React dev server (usually localhost:5173 for Vite) to call this
# API from the browser. Tighten this once you deploy for real.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# objects x time steps allowed in one /conjunctions/forecast request (keeps memory bounded)
MAX_FORECAST_WORK = 12_000_000


def _get_tles(group: str = engine.GROUP_STATIONS, limit: int | None = None, force_refresh: bool = False):
    return cache.get_tles(group=group, fetch_fn=engine.fetch_many, limit=limit, force_refresh=force_refresh)


def _http_error(exc: Exception, context: str) -> HTTPException:
    """
    Map an internal exception to the right HTTP status instead of a blanket 502.
      TLENotFound            -> 404 (CelesTrak has no such object/group)
      ValueError             -> 400 (bad input from the caller)
      RuntimeError           -> 422 (object can't be propagated, e.g. decayed)
      requests.RequestException -> 502 (CelesTrak unreachable / errored)
      anything else          -> 500 (our bug)
    """
    if isinstance(exc, engine.TLENotFound):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, ValueError):
        return HTTPException(status_code=400, detail=f"{context}: {exc}")
    if isinstance(exc, RuntimeError):
        return HTTPException(status_code=422, detail=f"{context}: {exc}")
    if isinstance(exc, requests.RequestException):
        return HTTPException(status_code=502, detail=f"{context}: upstream CelesTrak error ({exc})")
    return HTTPException(status_code=500, detail=f"{context}: unexpected error ({exc})")


@app.get("/")
def root():
    return {"status": "OrbitGuard API is running", "docs": "/docs"}


@app.get("/cache-status")
def get_cache_status(group: str = "stations"):
    """Show whether this group's data is cached and how old it is."""
    status = cache.cache_status(group)
    if status is None:
        return {"group": group, "cached": False}
    return {"cached": True, **status}


@app.get("/objects")
def list_objects(group: str = "stations", limit: int | None = None):
    """
    Return current positions for a group of tracked objects.

    Query params:
      group: CelesTrak group name (default "stations", ~10 objects for
             quick testing; try "active" once you're ready to scale to 100+)
      limit: cap the number of objects returned
    """
    try:
        tles = _get_tles(group=group, limit=limit)
        return {"count": len(tles), "objects": engine.propagate_many(tles)}
    except Exception as exc:
        raise _http_error(exc, "Failed to fetch/propagate")


@app.get("/objects/{norad_id}")
def get_object(norad_id: int):
    """Return the current position for a single object by NORAD catalog ID."""
    try:
        tle = engine.fetch_tle(norad_id)
        return engine.propagate(tle)
    except Exception as exc:
        raise _http_error(exc, f"Failed to fetch/propagate {norad_id}")


@app.get("/trajectory/{norad_id}")
def get_trajectory(norad_id: int, hours: str = "0,1,6,12,24,48"):
    """
    Predict a single object's position at several points in the future.

    Query params:
      hours: comma-separated hour offsets from now, e.g. "0,1,6,12,24,48"
    """
    try:
        hours_list = [float(h) for h in hours.split(",")]
    except ValueError:
        raise HTTPException(status_code=400, detail="hours must be comma-separated numbers, e.g. '0,1,6'")

    try:
        tle = engine.fetch_tle(norad_id)
        trajectory = engine.propagate_trajectory(tle, hours_ahead=hours_list)
        return {"norad_id": norad_id, "count": len(trajectory), "trajectory": trajectory}
    except Exception as exc:
        raise _http_error(exc, f"Failed to predict trajectory for {norad_id}")


@app.get("/conjunctions")
def list_conjunctions(
    group: str = "stations",
    limit: int | None = None,
    threshold_km: float = 5.0,
    method: str = "naive",
    ml: bool = False,
):
    """
    Detect close approaches (conjunctions) among a group of tracked objects.

    Query params:
      group: CelesTrak group name (default "stations")
      limit: cap the number of objects considered
      threshold_km: distance below which two objects count as a conjunction
      method: "naive" (O(n^2), fine up to ~1000 objects) or "kdtree"
              (faster at scale - see Week 4 of the project plan)
      ml: if true, also add ML risk fields (ml_risk_level, ml_risk_score,
          ml_probabilities) from the Random Forest model
    """
    if method not in ("naive", "kdtree"):
        raise HTTPException(status_code=400, detail="method must be 'naive' or 'kdtree'")
    if threshold_km <= 0:
        raise HTTPException(status_code=400, detail="threshold_km must be > 0")

    try:
        tles = _get_tles(group=group, limit=limit)
        objects = engine.propagate_many(tles)

        if method == "kdtree":
            results = conj.find_conjunctions_kdtree(objects, threshold_km=threshold_km)
        else:
            results = conj.find_conjunctions_naive(objects, threshold_km=threshold_km)

        if ml:
            results = ml_risk.score_conjunctions(results)

        return {
            "objects_checked": len(objects),
            "threshold_km": threshold_km,
            "method": method,
            "ml": ml,
            "count": len(results),
            "conjunctions": results,
        }
    except Exception as exc:
        raise _http_error(exc, "Failed to detect conjunctions")


@app.get("/conjunctions/forecast")
def forecast_conjunctions(
    group: str = "stations",
    limit: int | None = None,
    hours: float = 24.0,
    threshold_km: float = 5.0,
    step_seconds: float = 60.0,
    include_coorbiting: bool = False,
    start: str | None = None,
    ml: bool = False,
):
    """
    Time-window conjunction screening: finds every close approach in the next
    `hours` and reports the time of closest approach (TCA) and miss distance.
    Unlike /conjunctions (a snapshot of "right now"), this catches pairs that
    will pass close later.

    Query params:
      group: CelesTrak group name (default "stations")
      limit: cap the number of objects considered
      hours: window length, 0 < hours <= 72 (TLE accuracy degrades beyond ~3 days)
      threshold_km: miss distance below which a pair is reported
      step_seconds: coarse screening grid, 10-300 s (smaller = safer but slower)
      include_coorbiting: also report objects that fly together (e.g. docked
          vehicles). Excluded by default - they are not collision risks.
      start: ISO-8601 UTC start time (default: now)
      ml: add ML risk fields, as in /conjunctions
    """
    # validate cheaply before any network call
    if not (0 < hours <= conjw.MAX_WINDOW_HOURS):
        raise HTTPException(status_code=400, detail=f"hours must be > 0 and <= {conjw.MAX_WINDOW_HOURS:g}")
    if not (conjw.MIN_STEP_S <= step_seconds <= conjw.MAX_STEP_S):
        raise HTTPException(
            status_code=400,
            detail=f"step_seconds must be between {conjw.MIN_STEP_S:g} and {conjw.MAX_STEP_S:g}",
        )
    if threshold_km <= 0:
        raise HTTPException(status_code=400, detail="threshold_km must be > 0")

    start_dt = None
    if start:
        try:
            start_dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(status_code=400, detail="start must be ISO-8601, e.g. 2026-10-17T12:00:00Z")

    try:
        tles = _get_tles(group=group, limit=limit)
        n_steps = int(hours * 3600 / step_seconds) + 1
        if len(tles) * n_steps > MAX_FORECAST_WORK:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"{len(tles)} objects x {n_steps} time steps is too much work for one request "
                    f"(max {MAX_FORECAST_WORK:,}). Lower limit/hours or raise step_seconds."
                ),
            )

        out = conjw.find_conjunctions_in_window(
            tles,
            start=start_dt,
            hours=hours,
            threshold_km=threshold_km,
            step_seconds=step_seconds,
            include_coorbiting=include_coorbiting,
        )
        results = out["conjunctions"]
        if ml:
            results = ml_risk.score_conjunctions(results)

        return {
            "window_start_utc": (start_dt or datetime.now(timezone.utc)).isoformat(),
            "hours": hours,
            "threshold_km": threshold_km,
            "step_seconds": step_seconds,
            "ml": ml,
            "objects_checked": out["objects_checked"],
            "objects_unpropagatable": out["objects_unpropagatable"],
            "candidate_pairs": out["candidate_pairs"],
            "excluded_coorbiting_pairs": out["excluded_coorbiting_pairs"],
            "count": len(results),
            "conjunctions": results,
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise _http_error(exc, "Failed to forecast conjunctions")


@app.get("/what-if")
def what_if_maneuver(
    norad_id: int,
    other_norad_id: int,
    altitude_delta_km: float,
):
    """
    What-if maneuver simulator (Week 7 - the "wow feature").

    Simulates shifting one object's altitude and shows how the predicted
    distance to another object changes as a result.

    Query params:
      norad_id: the object being maneuvered (altitude adjusted)
      other_norad_id: the object it's being compared against
      altitude_delta_km: how much to shift altitude (+outward, -inward)
    """
    try:
        tle_a = engine.fetch_tle(norad_id)
        tle_b = engine.fetch_tle(other_norad_id)
        obj_a = engine.propagate(tle_a)
        obj_b = engine.propagate(tle_b)

        result = conj.simulate_altitude_adjustment(obj_a, obj_b, altitude_delta_km)
        return {
            "object_1": {"name": obj_a["name"], "norad_id": obj_a["norad_id"]},
            "object_2": {"name": obj_b["name"], "norad_id": obj_b["norad_id"]},
            **result,
        }
    except Exception as exc:
        raise _http_error(exc, "Failed to simulate maneuver")


@app.get("/model-info")
def model_info():
    """Describe the ML risk model: accuracy, per-class metrics, feature importance."""
    return ml_risk.get_metrics()


@app.get("/risk-score")
def risk_score(distance_km: float, relative_velocity_km_s: float, altitude_km: float = 500.0, altitude_gap_km: float = 0.0):
    """Score a hypothetical close approach with the ML model (handy for demos and the what-if UI)."""
    conj_like = {
        "distance_km": distance_km,
        "relative_velocity_km_s": relative_velocity_km_s,
        "altitude_km": {"object_1": altitude_km + altitude_gap_km / 2, "object_2": altitude_km - altitude_gap_km / 2},
    }
    return ml_risk.score_conjunctions([conj_like])[0] | {"rule_based_risk_level": conj._risk_level(distance_km)}
