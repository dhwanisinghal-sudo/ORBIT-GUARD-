"""
OrbitGuard - ground track
---------------------------
Sub-satellite latitude / longitude over a time window, for drawing on a map.
"""

from datetime import datetime, timedelta, timezone

import numpy as np
from sgp4.api import Satrec, WGS72, jday

import geodetic
import orbit_engine as engine

MAX_TRACK_HOURS = 72.0          # same reason as the forecast window: TLE accuracy fades after ~3 days
MIN_STEP_S, MAX_STEP_S = 5.0, 600.0
MAX_TRACK_POINTS = 10_000


def _split_antimeridian(points: list[dict]) -> list[list[list[float]]]:
    """
    Break the track into [lon, lat] runs wherever it crosses +-180 degrees, so a map layer
    does not draw a line straight across the whole world.
    """
    segments, current, prev_lon = [], [], None
    for p in points:
        if prev_lon is not None and abs(p["lon"] - prev_lon) > 180.0 and current:
            segments.append(current)
            current = []
        current.append([p["lon"], p["lat"]])
        prev_lon = p["lon"]
    if current:
        segments.append(current)
    return segments


def validate_params(hours: float, step_seconds: float) -> int:
    """Cheap input checks (run before any network call). Returns the number of points."""
    if not (0 < hours <= MAX_TRACK_HOURS):
        raise ValueError(f"hours must be > 0 and <= {MAX_TRACK_HOURS:g}")
    if not (MIN_STEP_S <= step_seconds <= MAX_STEP_S):
        raise ValueError(f"step_seconds must be between {MIN_STEP_S:g} and {MAX_STEP_S:g}")
    n = int(hours * 3600 / step_seconds) + 1
    if n > MAX_TRACK_POINTS:
        raise ValueError(f"{n} points requested (max {MAX_TRACK_POINTS}); lower hours or raise step_seconds")
    return n


def compute_ground_track(tle: dict, start: datetime | None = None, hours: float = 1.5,
                         step_seconds: float = 30.0) -> dict:
    """
    {"points": [{"t", "lat", "lon", "height_km"}...], "segments": [[[lon, lat]...]...],
     "skipped_points": n, **tle_age_info(at start)}

    Raises engine.MalformedTLE for a bad TLE, ValueError for bad parameters.
    Points where SGP4 fails (decayed / far from epoch) are skipped and counted.
    """
    n = validate_params(hours, step_seconds)
    engine.validate_tle_format(tle)
    start = engine._as_utc(start or datetime.now(timezone.utc))
    sat = Satrec.twoline2rv(tle["line1"], tle["line2"], WGS72)

    jd0, fr0 = jday(start.year, start.month, start.day, start.hour, start.minute,
                    start.second + start.microsecond / 1e6)
    offsets = np.arange(n) * step_seconds
    fr = fr0 + offsets / 86400.0
    err, r, _ = sat.sgp4_array(np.full(n, jd0), fr)
    ok = err == 0
    lat, lon, h = geodetic.teme_to_geodetic(r[ok], jd0, fr[ok])

    points = [
        {"t": (start + timedelta(seconds=float(o))).isoformat(),
         "lat": round(float(a), 4), "lon": round(float(b), 4), "height_km": round(float(c), 2)}
        for o, a, b, c in zip(offsets[ok], lat, lon, h)
    ]
    return {
        "start_utc": start.isoformat(),
        "hours": hours,
        "step_seconds": step_seconds,
        "count": len(points),
        "skipped_points": int(n - ok.sum()),
        "points": points,
        "segments": _split_antimeridian(points),
        **engine.tle_age_info(tle, start),
    }
