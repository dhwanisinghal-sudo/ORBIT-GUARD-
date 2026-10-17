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
MAX_FORECAST_WORK = 12_000_000


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


def _warnings(staleness: dict | None = None, skipped: int = 0, cache_meta: dict | None = None) -> list[str]:
    """Human-readable notes about data quality, so nothing degrades silently."""
    notes = []
    if cache_meta and cache_meta.get("source") == "stale_cache":
        mins = cache_meta["age_seconds"] / 60
        notes.append(f"CelesTrak was unreachable; using cached TLEs from {mins:.0f} minutes ago")
    if staleness:
        if staleness.get("unreliable"):
            notes.append(f"{staleness['unreliable']} object(s) have TLEs older than "
                         f"{engine.UNRELIABLE_TLE_DAYS:g} days; their positions are unreliable")
        if staleness.get("stale"):
            notes.append(f"{staleness['stale']} object(s) have TLEs older than "
                         f"{engine.STALE_TLE_DAYS:g} days; accuracy is degraded")
    if skipped:
        notes.append(f"{skipped} object(s) were skipped because SGP4 could not propagate them "
                     "(decayed, malformed, or TLE too old)")
    return notes


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
    _check_limit(limit)

    try:
        tles, cache_meta = _get_tles_meta(group=group, limit=limit)
        prop = engine.propagate_many_with_stats(tles)
        objects = prop["objects"]

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
    if not (0 < hours <= conjw.MAX_WINDOW_HOURS):
        raise HTTPException(status_code=400, detail=f"hours must be > 0 and <= {conjw.MAX_WINDOW_HOURS:g}")
    if not (conjw.MIN_STEP_S <= step_seconds <= conjw.MAX_STEP_S):
        raise HTTPException(
            status_code=400,
            detail=f"step_seconds must be between {conjw.MIN_STEP_S:g} and {conjw.MAX_STEP_S:g}",
        )
    if threshold_km <= 0:
        raise HTTPException(status_code=400, detail="threshold_km must be > 0")
    _check_limit(limit)

    start_dt = None
    if start:
        try:
            start_dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(status_code=400, detail="start must be ISO-8601, e.g. 2026-10-17T12:00:00Z")

    try:
        tles, cache_meta = _get_tles_meta(group=group, limit=limit)
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

        # TLE age at the window start, per object and overall
        ref = start_dt or datetime.now(timezone.utc)
        ages = {}
        for t in tles:
            try:
                ages[int(t["line1"][2:7])] = engine.tle_age_info(t, ref)
            except Exception:
                continue          # malformed TLEs are already counted in objects_unpropagatable
        staleness = engine.summarize_staleness(ages.values())
        rank = {"fresh": 0, "stale": 1, "unreliable": 2}
        unreliable_events = 0
        for c in results:
            worst = "fresh"
            for key in ("object_1", "object_2"):
                a = ages.get(c[key]["norad_id"])
                if a:
                    c[key]["tle_age_days"] = a["tle_age_days"]
                    c[key]["tle_status"] = a["tle_status"]
                    if rank[a["tle_status"]] > rank[worst]:
                        worst = a["tle_status"]
            c["tle_status"] = worst            # the weaker of the two TLEs
            unreliable_events += worst == "unreliable"
        warnings = _warnings(staleness, out["objects_unpropagatable"], cache_meta)
        if unreliable_events:
            warnings.append(f"{unreliable_events} conjunction(s) involve a TLE older than "
                            f"{engine.UNRELIABLE_TLE_DAYS:g} days and may be spurious")

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
        tles, metas = _get_tles_by_ids([norad_id, other_norad_id])
        obj_a = engine.propagate(tles[norad_id])
        obj_b = engine.propagate(tles[other_norad_id])

        result = conj.simulate_altitude_adjustment(obj_a, obj_b, altitude_delta_km)
        warnings = [f"{o['name']}: {o['tle_warning']}" for o in (obj_a, obj_b) if o.get("tle_warning")]
        for m in metas.values():
            warnings += _warnings(cache_meta=m)
        return {
            "object_1": {"name": obj_a["name"], "norad_id": obj_a["norad_id"],
                         "tle_age_days": obj_a["tle_age_days"], "tle_status": obj_a["tle_status"]},
            "object_2": {"name": obj_b["name"], "norad_id": obj_b["norad_id"],
                         "tle_age_days": obj_b["tle_age_days"], "tle_status": obj_b["tle_status"]},
            **result,
            "warnings": list(dict.fromkeys(warnings)),
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
