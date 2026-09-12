"""
OrbitGuard - FastAPI backend (Week 6 endpoints, pulled forward)
-----------------------------------------------------------------
Run with:
    uvicorn main:app --reload

Then open http://127.0.0.1:8000/docs for interactive API docs (FastAPI
generates this automatically - it's a good way to hand this to your
frontend teammate without them needing to read your code).

Endpoints:
    GET /objects            -> list of tracked objects with current position
    GET /objects/{norad_id} -> single object's current position
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

import orbit_engine as engine
import conjunction as conj
import cache

app = FastAPI(title="OrbitGuard API", version="0.1.0")

# Allow the React dev server (usually localhost:5173 for Vite) to call this
# API from the browser. Tighten this once you deploy for real.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Simple in-memory cache retained as a fallback; the real cache is now
# the SQLite-backed one in cache.py, which survives server restarts.
_cache: dict = {"tles": None, "fetched_at": None}


def _get_tles(group: str = engine.GROUP_STATIONS, limit: int | None = None, force_refresh: bool = False):
    return cache.get_tles(group=group, fetch_fn=engine.fetch_many, limit=limit, force_refresh=force_refresh)


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
        raise HTTPException(status_code=502, detail=f"Failed to fetch/propagate: {exc}")


@app.get("/objects/{norad_id}")
def get_object(norad_id: int):
    """Return the current position for a single object by NORAD catalog ID."""
    try:
        tle = engine.fetch_tle(norad_id)
        return engine.propagate(tle)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Failed to fetch/propagate {norad_id}: {exc}")


@app.get("/trajectory/{norad_id}")
def get_trajectory(norad_id: int, hours: str = "0,1,6,12,24,48"):
    """
    Predict a single object's position at several points in the future.

    Query params:
      hours: comma-separated hour offsets from now, e.g. "0,1,6,12,24,48"
    """
    try:
        hours_list = [float(h) for h in hours.split(",")]
        tle = engine.fetch_tle(norad_id)
        trajectory = engine.propagate_trajectory(tle, hours_ahead=hours_list)
        return {"norad_id": norad_id, "count": len(trajectory), "trajectory": trajectory}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Failed to predict trajectory for {norad_id}: {exc}")


@app.get("/conjunctions")
def list_conjunctions(
    group: str = "stations",
    limit: int | None = None,
    threshold_km: float = 5.0,
    method: str = "naive",
):
    """
    Detect close approaches (conjunctions) among a group of tracked objects.

    Query params:
      group: CelesTrak group name (default "stations")
      limit: cap the number of objects considered
      threshold_km: distance below which two objects count as a conjunction
      method: "naive" (O(n^2), fine up to ~1000 objects) or "kdtree"
              (faster at scale - see Week 4 of the project plan)
    """
    try:
        tles = _get_tles(group=group, limit=limit)
        objects = engine.propagate_many(tles)

        if method == "kdtree":
            results = conj.find_conjunctions_kdtree(objects, threshold_km=threshold_km)
        else:
            results = conj.find_conjunctions_naive(objects, threshold_km=threshold_km)

        return {
            "objects_checked": len(objects),
            "threshold_km": threshold_km,
            "method": method,
            "count": len(results),
            "conjunctions": results,
        }
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Failed to detect conjunctions: {exc}")


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
        raise HTTPException(status_code=502, detail=f"Failed to simulate maneuver: {exc}")
