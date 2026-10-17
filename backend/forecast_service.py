"""
OrbitGuard - shared helpers for the conjunction endpoints
----------------------------------------------------------
Used by main.py (/conjunctions/forecast) and watchlist.py (/watchlist/alerts), so both
validate input, describe data quality and map errors the same way.
"""

from datetime import datetime, timezone

import requests
from fastapi import HTTPException

import orbit_engine as engine
import conjunction_window as conjw

# objects x time steps allowed in one window-screening request (keeps memory bounded)
MAX_FORECAST_WORK = 12_000_000


def data_quality_warnings(staleness: dict | None = None, skipped: int = 0, cache_meta: dict | None = None) -> list[str]:
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


def http_error(exc: Exception, context: str) -> HTTPException:
    """
    Map an internal exception to the right HTTP status instead of a blanket 502.
      TLENotFound            -> 404 (CelesTrak has no such object/group)
      ValueError             -> 400 (bad input from the caller)
      RuntimeError           -> 422 (object can't be propagated, e.g. decayed)
      requests.RequestException -> 502 (CelesTrak unreachable / errored)
      HTTPException          -> passed through unchanged
      anything else          -> 500 (our bug)
    """
    if isinstance(exc, HTTPException):
        return exc
    if isinstance(exc, engine.TLENotFound):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, ValueError):
        return HTTPException(status_code=400, detail=f"{context}: {exc}")
    if isinstance(exc, RuntimeError):
        return HTTPException(status_code=422, detail=f"{context}: {exc}")
    if isinstance(exc, requests.RequestException):
        return HTTPException(status_code=502, detail=f"{context}: upstream CelesTrak error ({exc})")
    return HTTPException(status_code=500, detail=f"{context}: unexpected error ({exc})")



def validate_window_params(hours: float, threshold_km: float, step_seconds: float, start: str | None):
    """Cheap input checks, run before any network call. Returns the parsed start (or None)."""
    if not (0 < hours <= conjw.MAX_WINDOW_HOURS):
        raise HTTPException(status_code=400, detail=f"hours must be > 0 and <= {conjw.MAX_WINDOW_HOURS:g}")
    if not (conjw.MIN_STEP_S <= step_seconds <= conjw.MAX_STEP_S):
        raise HTTPException(
            status_code=400,
            detail=f"step_seconds must be between {conjw.MIN_STEP_S:g} and {conjw.MAX_STEP_S:g}",
        )
    if threshold_km <= 0:
        raise HTTPException(status_code=400, detail="threshold_km must be > 0")
    if not start:
        return None
    try:
        return datetime.fromisoformat(start.replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(status_code=400, detail="start must be ISO-8601, e.g. 2026-10-17T12:00:00Z")


def parse_start(start: str | None):
    """ISO-8601 start time -> aware datetime (None stays None). Raises HTTP 400 if unparseable."""
    if not start:
        return None
    try:
        return datetime.fromisoformat(start.replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(status_code=400, detail="start must be ISO-8601, e.g. 2026-10-17T12:00:00Z")


def check_work(n_objects: int, hours: float, step_seconds: float, limit: int | None = None) -> int:
    """Refuse requests whose objects x time steps would exhaust memory. Returns the step count."""
    limit = MAX_FORECAST_WORK if limit is None else limit     # read at call time, not definition time
    n_steps = int(hours * 3600 / step_seconds) + 1
    if n_objects * n_steps > limit:
        raise HTTPException(
            status_code=400,
            detail=(
                f"{n_objects} objects x {n_steps} time steps is too much work for one request "
                f"(max {limit:,}). Lower limit/hours or raise step_seconds."
            ),
        )
    return n_steps


def annotate_tle_age(results: list[dict], tles: list[dict], ref: datetime) -> tuple[dict, int]:
    """
    Add tle_age_days / tle_status to each object of each conjunction (and the weaker of the two
    to the conjunction itself), measured at `ref`. Returns (staleness summary, number of
    conjunctions that involve an unreliable TLE).
    """
    ages = {}
    for t in tles:
        try:
            ages[int(t["line1"][2:7])] = engine.tle_age_info(t, ref)
        except Exception:
            continue          # malformed TLEs are already counted as unpropagatable
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
        c["tle_status"] = worst
        unreliable_events += worst == "unreliable"
    return staleness, unreliable_events


def unreliable_note(count: int) -> str:
    return (f"{count} conjunction(s) involve a TLE older than "
            f"{engine.UNRELIABLE_TLE_DAYS:g} days and may be spurious")
