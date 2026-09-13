"""
OrbitGuard - orbit engine
--------------------------
Reusable functions for fetching TLE data from CelesTrak and propagating
positions with SGP4. Both the CLI script and the FastAPI app import from here,
so there's one source of truth for "how do we get a satellite's position."
"""

import math
from datetime import datetime, timezone, timedelta

import requests
from sgp4.api import Satrec, WGS72, jday

CELESTRAK_URL = "https://celestrak.org/NORAD/elements/gp.php"
EARTH_RADIUS_KM = 6371.0

# A real ISS TLE, used only as a fallback so things still work with no
# internet access. It goes stale fast, so always prefer the live fetch.
SAMPLE_TLE = {
    "name": "ISS (ZARYA)",
    "line1": "1 25544U 98067A   24235.16000531  .00028314  00000+0  49252-3 0  9994",
    "line2": "2 25544  51.6402 348.4828 0004893 236.4095 123.6428 15.50549723468780",
}

# CelesTrak's predefined groups. GROUP=stations is small (~10 objects) and
# good for testing; GROUP=active is ~7,000+ objects and better for the
# "100 satellites" milestone once you're ready to slice into it.
GROUP_STATIONS = "stations"
GROUP_ACTIVE = "active"


def _tle_epoch_to_datetime(line1: str) -> datetime:
    """Parse the epoch (columns 19-32) out of TLE line 1 into a UTC datetime."""
    epoch_str = line1[18:32].strip()  # e.g. "24235.16000531"
    year_two_digit = int(epoch_str[:2])
    day_of_year = float(epoch_str[2:])
    year = 2000 + year_two_digit if year_two_digit < 57 else 1900 + year_two_digit
    return datetime(year, 1, 1, tzinfo=timezone.utc) + timedelta(days=day_of_year - 1)


def fetch_tle(norad_id: int) -> dict:
    """Fetch a single object's TLE from CelesTrak by NORAD catalog number."""
    params = {"CATNR": norad_id, "FORMAT": "TLE"}
    resp = requests.get(CELESTRAK_URL, params=params, timeout=10)
    resp.raise_for_status()
    lines = [ln for ln in resp.text.strip().splitlines() if ln.strip()]
    if len(lines) < 3:
        raise ValueError(f"Unexpected response from CelesTrak:\n{resp.text}")
    name, line1, line2 = lines[0].strip(), lines[1], lines[2]
    return {"name": name, "line1": line1, "line2": line2}


def fetch_many(group: str = GROUP_STATIONS, limit: int | None = None) -> list[dict]:
    """
    Fetch a whole group of TLEs from CelesTrak in a single request.

    group: a CelesTrak group name, e.g. "stations" (small, ~10 objects,
           good for testing) or "active" (~7,000+ active satellites).
    limit: optionally cap how many objects are returned (useful while your
           conjunction-detection algorithm is still O(n^2) and can't yet
           handle thousands of objects - see Week 4 of the project plan).
    """
    params = {"GROUP": group, "FORMAT": "TLE"}
    resp = requests.get(CELESTRAK_URL, params=params, timeout=30)
    resp.raise_for_status()

    lines = [ln for ln in resp.text.splitlines() if ln.strip()]
    if len(lines) % 3 != 0:
        raise ValueError(
            f"Expected TLE lines in groups of 3, got {len(lines)} lines total. "
            "CelesTrak's response format may have changed."
        )

    tles = []
    for i in range(0, len(lines), 3):
        name, line1, line2 = lines[i].strip(), lines[i + 1], lines[i + 2]
        tles.append({"name": name, "line1": line1, "line2": line2})
        if limit and len(tles) >= limit:
            break
    return tles


def propagate(tle: dict, when: datetime | None = None) -> dict:
    """Run SGP4 on a TLE for a given UTC datetime (defaults to now)."""
    when = when or datetime.now(timezone.utc)

    sat = Satrec.twoline2rv(tle["line1"], tle["line2"], WGS72)
    jd, fr = jday(when.year, when.month, when.day, when.hour, when.minute, when.second)

    error_code, position, velocity = sat.sgp4(jd, fr)
    if error_code != 0:
        raise RuntimeError(f"SGP4 propagation error code {error_code} for {tle['name']}")

    x, y, z = position  # km, TEME frame
    vx, vy, vz = velocity  # km/s

    radius = math.sqrt(x**2 + y**2 + z**2)
    altitude_km = radius - EARTH_RADIUS_KM

    return {
        "name": tle["name"],
        "norad_id": tle["line1"].split()[1].rstrip("U"),
        "timestamp_utc": when.isoformat(),
        "position_km": {"x": round(x, 3), "y": round(y, 3), "z": round(z, 3)},
        "velocity_km_s": {"x": round(vx, 3), "y": round(vy, 3), "z": round(vz, 3)},
        "altitude_km": round(altitude_km, 2),
    }


def propagate_many(tles: list[dict], when: datetime | None = None) -> list[dict]:
    """Propagate a list of TLEs, skipping any that error out (e.g. decayed objects)."""
    results = []
    for tle in tles:
        try:
            results.append(propagate(tle, when))
        except RuntimeError:
            # Some catalog objects (esp. debris) have gone decayed/invalid;
            # skip them rather than let one bad object crash the whole batch.
            continue
    return results


# Default offsets used for trajectory prediction, matching Week 3 of the plan.
DEFAULT_TRAJECTORY_HOURS = [0, 1, 6, 12, 24, 48]


def propagate_trajectory(tle: dict, hours_ahead: list[float] = None) -> list[dict]:
    """
    Predict an object's position at several points in the future.

    hours_ahead: list of hour offsets from now, e.g. [0, 1, 6, 12, 24, 48].
    Returns one propagated position per offset (skipping any that error out).
    """
    hours_ahead = hours_ahead if hours_ahead is not None else DEFAULT_TRAJECTORY_HOURS
    now = datetime.now(timezone.utc)

    trajectory = []
    for h in hours_ahead:
        when = now + timedelta(hours=h)
        try:
            point = propagate(tle, when)
            point["hours_from_now"] = h
            trajectory.append(point)
        except RuntimeError:
            continue
    return trajectory
