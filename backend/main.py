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

import logging
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import requests
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

import orbit_engine as engine
import conjunction as conj
import conjunction_window as conjw
import cache
import auth
import config
import ml_risk
import watchlist
import forecast_service as svc
import ground_track as gt
import maneuver

log = logging.getLogger("uvicorn.error")   # so startup messages show in uvicorn's console output


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Startup: load (or train) the ML model now rather than during the first ?ml=true request."""
    started = time.perf_counter()
    ml_risk.warm_up()
    log.info("ML risk model ready in %.1f s", time.perf_counter() - started)
    yield


app = FastAPI(title="OrbitGuard API", version="0.4.0", lifespan=lifespan)
app.include_router(auth.router)
app.include_router(watchlist.router)

# Only the configured frontend origins may call this API from a browser
# (ORBITGUARD_CORS_ORIGINS; default: the Vite dev server). Auth uses a bearer token
# header, not cookies, so credentials are not allowed cross-origin.
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


# objects x time steps allowed in one /conjunctions/forecast request (keeps memory bounded)
MAX_FORECAST_WORK = svc.MAX_FORECAST_WORK

# shared with watchlist.py; kept under their old names for the endpoints below
_warnings = svc.data_quality_warnings
_http_error = svc.http_error

# The naive snapshot check compares every pair (O(n^2)): ~1.7 s at 3,000 objects, ~9 s at 7,000.
# Above this size it is refused so one request can't tie up a worker; kdtree gives the same answer.
MAX_NAIVE_OBJECTS = 1500


def _get_tles_meta(group: str = engine.GROUP_STATIONS, limit: int | None = None, force_refresh: bool = False):
    """Group TLEs through the cache -> (tles, cache_meta)."""
    return cache.get_tles(group=group, fetch_fn=engine.fetch_many, limit=limit,
                          force_refresh=force_refresh, return_meta=True)


def _get_tles(group: str = engine.GROUP_STATIONS, limit: int | None = None, force_refresh: bool = False):
    return _get_tles_meta(group=group, limit=limit, force_refresh=force_refresh)[0]


def _get_tle(norad_id: int):
    """One object's TLE through the single-object cache -> (tle, cache_meta)."""
    return cache.get_tle(norad_id, engine.fetch_tle, return_meta=True)


def _get_tles_by_ids(norad_ids):
    """Several objects at once (fetched in parallel on a miss). Raises the first per-object error."""
    tles, errors, metas = cache.get_tles_by_ids(norad_ids, engine.fetch_tle)
    for nid in dict.fromkeys(norad_ids):
        if nid in errors:
            raise errors[nid]
    return tles, metas


def _check_limit(limit: int | None):
    if limit is not None and limit <= 0:
        raise HTTPException(status_code=400, detail="limit must be a positive integer")


@app.get("/")
def root():
    return {"status": "OrbitGuard API is running", "docs": "/docs"}


@app.get("/cache-status")
def get_cache_status(group: str = "stations", norad_id: int | None = None):
    """Show whether a group's (or, with norad_id, a single object's) data is cached and how old it is."""
    if norad_id is not None:
        status = cache.single_cache_status(norad_id)
        return {"norad_id": norad_id, "cached": False} if status is None else {"cached": True, **status}
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

    `count` is the number of objects actually returned; `requested` is how many TLEs
    were fetched. Anything that could not be propagated is reported under `skipped`
    instead of vanishing, and each object carries its TLE age/status.
    """
    _check_limit(limit)
    try:
        tles, cache_meta = _get_tles_meta(group=group, limit=limit)
        out = engine.propagate_many_with_stats(tles)
        return {
            "count": len(out["objects"]),
            "requested": len(tles),
            "objects": out["objects"],
            "skipped": out["skipped"],
            "tle_staleness": out["tle_staleness"],
            "cache": cache_meta,
            "warnings": _warnings(out["tle_staleness"], out["skipped"]["count"], cache_meta),
        }
    except Exception as exc:
        raise _http_error(exc, "Failed to fetch/propagate")


@app.get("/objects/{norad_id}")
def get_object(norad_id: int):
    """Return the current position for a single object by NORAD catalog ID."""
    try:
        tle, cache_meta = _get_tle(norad_id)
        return {**engine.propagate(tle), "cache": cache_meta}
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
        tle, cache_meta = _get_tle(norad_id)
        trajectory = engine.propagate_trajectory(tle, hours_ahead=hours_list)
        age = engine.tle_age_info(tle)
        skipped_points = len(hours_list) - len(trajectory)
        warnings = _warnings(cache_meta=cache_meta)
        if age.get("tle_warning"):
            warnings.append(age["tle_warning"])
        if skipped_points:
            warnings.append(f"{skipped_points} of {len(hours_list)} requested point(s) could not be "
                            "propagated (SGP4 error - often a very old TLE or a time far from its epoch)")
        return {
            "norad_id": norad_id,
            "count": len(trajectory),
            "requested_points": len(hours_list),
            "skipped_points": skipped_points,
            **age,
            "trajectory": trajectory,
            "cache": cache_meta,
            "warnings": warnings,
        }
    except Exception as exc:
        raise _http_error(exc, f"Failed to predict trajectory for {norad_id}")


@app.get("/conjunctions")
def list_conjunctions(
    group: str = "stations",
    limit: int | None = None,
    threshold_km: float = 5.0,
    method: str = "kdtree",
    ml: bool = False,
):
    """
    Detect close approaches (conjunctions) among a group of tracked objects.

    Query params:
      group: CelesTrak group name (default "stations")
      limit: cap the number of objects considered
      threshold_km: distance below which two objects count as a conjunction
      method: "kdtree" (default; ~milliseconds even for the whole active catalog) or
              "naive" (O(n^2) reference implementation, refused above MAX_NAIVE_OBJECTS
              objects). Both return identical results.
      ml: if true, also add ML risk fields (ml_risk_level, ml_risk_score,
          ml_probabilities) from the Random Forest model
    """
    if method not in ("naive", "kdtree"):
        raise HTTPException(status_code=400, detail="method must be 'naive' or 'kdtree'")
    if threshold_km <= 0:
        raise HTTPException(status_code=400, detail="threshold_km must be > 0")
    _check_limit(limit)

    try:
        tles, cache_meta = _get_tles_meta(group=group, limit=limit)
        prop = engine.propagate_many_with_stats(tles)
        objects = prop["objects"]

        if method == "naive" and len(objects) > MAX_NAIVE_OBJECTS:
            raise HTTPException(
                status_code=400,
                detail=f"method=naive is limited to {MAX_NAIVE_OBJECTS} objects (got {len(objects)}); "
                       "use method=kdtree, which returns the same results far faster",
            )

        if method == "kdtree":
            results = conj.find_conjunctions_kdtree(objects, threshold_km=threshold_km)
        else:
            results = conj.find_conjunctions_naive(objects, threshold_km=threshold_km)

        if ml:
            results = ml_risk.score_conjunctions(results)

        return {
            "objects_checked": len(objects),
            "objects_skipped": prop["skipped"]["count"],
            "skipped": prop["skipped"],
            "tle_staleness": prop["tle_staleness"],
            "cache": cache_meta,
            "warnings": _warnings(prop["tle_staleness"], prop["skipped"]["count"], cache_meta),
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
    start_dt = svc.validate_window_params(hours, threshold_km, step_seconds, start)
    _check_limit(limit)

    try:
        tles, cache_meta = _get_tles_meta(group=group, limit=limit)
        svc.check_work(len(tles), hours, step_seconds, limit=MAX_FORECAST_WORK)

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

        # TLE age at the window start, per object and overall
        ref = start_dt or datetime.now(timezone.utc)
        staleness, unreliable_events = svc.annotate_tle_age(results, tles, ref)
        warnings = _warnings(staleness, out["objects_unpropagatable"], cache_meta)
        if unreliable_events:
            warnings.append(svc.unreliable_note(unreliable_events))

        return {
            "window_start_utc": ref.isoformat(),
            "hours": hours,
            "threshold_km": threshold_km,
            "step_seconds": step_seconds,
            "ml": ml,
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
        raise _http_error(exc, "Failed to forecast conjunctions")


@app.get("/what-if")
def what_if_maneuver(
    norad_id: int,
    other_norad_id: int,
    dv_along_ms: float = 0.0,
    dv_radial_ms: float = 0.0,
    dv_cross_ms: float = 0.0,
    burn_in_hours: float = 0.0,
    window_hours: float = 24.0,
    step_seconds: float = 20.0,
    start: str | None = None,
    altitude_delta_km: float | None = None,
):
    """
    What-if maneuver simulator: applies an impulsive burn to one object, re-propagates it and
    reports how the time of closest approach (TCA) and miss distance to another object change.

    Query params:
      norad_id: the object that burns
      other_norad_id: the object it is compared against
      dv_along_ms / dv_radial_ms / dv_cross_ms: delta-v in m/s in the object's RTN frame
          (+along-track = prograde, +radial = away from Earth, +cross = along the orbit normal)
      burn_in_hours: how long after `start` the burn happens (default 0)
      window_hours: how long after the burn the pair is screened (burn_in + window <= 72 h)
      step_seconds: coarse screening grid, 5-120 s (default 20)
      start: ISO-8601 UTC start time (default: now)
      altitude_delta_km: DEPRECATED. Converted to the along-track burn that changes the
          semi-major axis by this amount. Cannot be combined with the dv_* parameters.

    The "before" numbers are plain SGP4. The "after" numbers add the effect of the burn,
    computed with a two-body + J2 integrator (no drag/SRP in that difference).
    """
    if altitude_delta_km is not None and (dv_along_ms or dv_radial_ms or dv_cross_ms):
        raise HTTPException(status_code=400,
                            detail="use either altitude_delta_km (deprecated) or the dv_* parameters, not both")
    start_dt = svc.parse_start(start)
    try:
        tles, metas = _get_tles_by_ids([norad_id, other_norad_id])
        result = maneuver.analyze_maneuver(
            tles[norad_id], tles[other_norad_id],
            dv_radial_ms=dv_radial_ms, dv_along_ms=dv_along_ms, dv_cross_ms=dv_cross_ms,
            altitude_delta_km=altitude_delta_km,
            burn_in_hours=burn_in_hours, window_hours=window_hours,
            start=start_dt, step_seconds=step_seconds,
        )
        ref = start_dt or datetime.now(timezone.utc)
        objs = []
        warnings = []
        for nid in (norad_id, other_norad_id):
            t = tles[nid]
            age = engine.tle_age_info(t, ref)
            objs.append({"name": t["name"], "norad_id": int(t["line1"][2:7]),
                         "tle_age_days": age["tle_age_days"], "tle_status": age["tle_status"]})
            if age.get("tle_warning"):
                warnings.append(f"{t['name']}: {age['tle_warning']}")
        for meta in metas.values():
            warnings += _warnings(cache_meta=meta)
        warnings += result["notes"]
        return {
            "object_1": objs[0],
            "object_2": objs[1],
            **{k: v for k, v in result.items() if k not in ("notes", "deprecation")},
            **({"deprecation": result["deprecation"]} if result["deprecation"] else {}),
            "warnings": list(dict.fromkeys(warnings)),
        }
    except Exception as exc:
        raise _http_error(exc, "Failed to simulate maneuver")


@app.get("/ground-track/{norad_id}")
def get_ground_track(norad_id: int, hours: float = 1.5, step_seconds: float = 30.0, start: str | None = None):
    """
    Sub-satellite latitude/longitude over a time window, ready to draw on a map.

    Query params:
      hours: window length, 0 < hours <= 72 (default 1.5, about one ISS orbit)
      step_seconds: sample spacing, 5-600 s (default 30)
      start: ISO-8601 UTC start time (default: now)

    Returns `points` ({t, lat, lon, height_km}) and `segments` - the same track split into
    [lon, lat] runs wherever it crosses the +-180 degree meridian, so map layers do not draw a
    line across the whole globe. height_km is above the WGS-84 ellipsoid.
    """
    try:
        gt.validate_params(hours, step_seconds)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    start_dt = svc.parse_start(start)
    try:
        tle, cache_meta = _get_tle(norad_id)
        track = gt.compute_ground_track(tle, start=start_dt, hours=hours, step_seconds=step_seconds)
        warnings = _warnings(cache_meta=cache_meta)
        if track.get("tle_warning"):
            warnings.append(track["tle_warning"])
        if track["skipped_points"]:
            warnings.append(f"{track['skipped_points']} point(s) could not be propagated "
                            "(SGP4 error - often a very old TLE or a time far from its epoch)")
        return {"norad_id": norad_id, "name": tle["name"], **track, "cache": cache_meta, "warnings": warnings}
    except Exception as exc:
        raise _http_error(exc, f"Failed to compute ground track for {norad_id}")


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
