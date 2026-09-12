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

app = FastAPI(title="OrbitGuard API", version="0.1.0")

# Allow the React dev server (usually localhost:5173 for Vite) to call this
# API from the browser. Tighten this once you deploy for real.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Simple in-memory cache so we don't hit CelesTrak on every single request.
# Good enough for now; swap for SQLite/Postgres once you get to Week 6 proper.
_cache: dict = {"tles": None, "fetched_at": None}


def _get_tles(group: str = engine.GROUP_STATIONS, limit: int | None = None):
    if _cache["tles"] is None:
        _cache["tles"] = engine.fetch_many(group=group, limit=limit)
    return _cache["tles"]


@app.get("/")
def root():
    return {"status": "OrbitGuard API is running", "docs": "/docs"}


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
