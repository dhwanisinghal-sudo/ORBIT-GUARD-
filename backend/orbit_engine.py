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

import geodetic

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


class TLENotFound(Exception):
    """CelesTrak has no data for the requested NORAD ID or group."""


# SGP4 accuracy degrades quickly as a TLE ages (a few km/day in LEO, worse with drag),
# so every result carries the TLE's age and a status derived from these thresholds.
STALE_TLE_DAYS = 7.0         # older than this: usable, but flagged
UNRELIABLE_TLE_DAYS = 30.0   # older than this: positions should not be trusted

TLE_FIELDS = ("tle_epoch_utc", "tle_age_days", "tle_status", "tle_warning")

SGP4_ERRORS = {
    1: "mean eccentricity out of range",
    2: "mean motion less than zero",
    3: "perturbed eccentricity out of range",
    4: "semi-latus rectum below zero",
    5: "epoch elements are sub-orbital",
    6: "satellite has decayed",
}


class PropagationError(RuntimeError):
    """SGP4 could not propagate a TLE. Subclasses RuntimeError so existing handlers still match."""

    def __init__(self, message: str, code: int | None = None):
        super().__init__(message)
        self.code = code


class MalformedTLE(PropagationError):
    """The TLE text is not a valid two-line element set (wrong shape, not an SGP4 failure)."""


def validate_tle_format(tle: dict) -> None:
    """Cheap structural check: two 69-character lines, correctly numbered, same catalog number."""
    try:
        l1, l2 = tle["line1"].rstrip(), tle["line2"].rstrip()
    except (KeyError, AttributeError, TypeError):
        raise MalformedTLE("TLE is missing line1/line2")
    if len(l1) != 69 or len(l2) != 69 or not l1.startswith("1 ") or not l2.startswith("2 "):
        raise MalformedTLE(f"malformed TLE for {tle.get('name')}: each line must be 69 characters "
                           "and start with '1 ' / '2 '")
    if not l1[2:7].strip().isdigit() or l1[2:7] != l2[2:7]:
        raise MalformedTLE(f"malformed TLE for {tle.get('name')}: catalog numbers missing or different")


def _as_utc(when: datetime) -> datetime:
    return when.replace(tzinfo=timezone.utc) if when.tzinfo is None else when.astimezone(timezone.utc)


def tle_age_info(tle: dict, when: datetime | None = None) -> dict:
    """
    How old is this TLE, relative to `when` (default: now)?

    Returns tle_epoch_utc, tle_age_days, tle_status ("fresh" | "stale" | "unreliable")
    and, unless fresh, a human-readable tle_warning. Age is measured to the time being
    propagated, so a forecast far past the epoch is flagged too.
    """
    when = _as_utc(when or datetime.now(timezone.utc))
    epoch = _tle_epoch_to_datetime(tle["line1"])
    age_days = abs((when - epoch).total_seconds()) / 86400.0
    if age_days >= UNRELIABLE_TLE_DAYS:
        status = "unreliable"
        warning = (f"TLE is {age_days:.1f} days old (over {UNRELIABLE_TLE_DAYS:g}); "
                   "position error is likely large - do not rely on it")
    elif age_days >= STALE_TLE_DAYS:
        status = "stale"
        warning = (f"TLE is {age_days:.1f} days old (over {STALE_TLE_DAYS:g}); "
                   "accuracy is degraded")
    else:
        status, warning = "fresh", None
    info = {
        "tle_epoch_utc": epoch.isoformat(),
        "tle_age_days": round(age_days, 2),
        "tle_status": status,
    }
    if warning:
        info["tle_warning"] = warning
    return info


def summarize_staleness(infos) -> dict:
    """Roll a collection of tle_age_info dicts up into counts and the oldest age."""
    counts = {"fresh": 0, "stale": 0, "unreliable": 0}
    oldest = None
    for info in infos:
        counts[info["tle_status"]] += 1
        if oldest is None or info["tle_age_days"] > oldest:
            oldest = info["tle_age_days"]
    return {**counts, "oldest_age_days": oldest}


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
        # CelesTrak answers HTTP 200 with a short text such as "No GP data found"
        raise TLENotFound(f"No TLE found for NORAD ID {norad_id}")
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
    if len(lines) < 3:
        raise TLENotFound(f"No TLE data found for group '{group}'")
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

    validate_tle_format(tle)
    sat = Satrec.twoline2rv(tle["line1"], tle["line2"], WGS72)
    # Include microseconds: a 1 s truncation is ~7.5 km of along-track error in LEO.
    jd, fr = jday(
        when.year, when.month, when.day,
        when.hour, when.minute, when.second + when.microsecond / 1e6,
    )

    error_code, position, velocity = sat.sgp4(jd, fr)
    if error_code != 0:
        reason = SGP4_ERRORS.get(error_code, "unknown error")
        try:
            age = tle_age_info(tle, when)
            context = f"; TLE epoch {age['tle_epoch_utc']}, {age['tle_age_days']} days from requested time"
        except Exception:
            context = ""
        raise PropagationError(
            f"SGP4 propagation error code {error_code} ({reason}) for {tle['name']}{context}",
            code=error_code,
        )

    x, y, z = position  # km, TEME frame
    vx, vy, vz = velocity  # km/s

    radius = math.sqrt(x**2 + y**2 + z**2)
    altitude_km = radius - EARTH_RADIUS_KM
    # sub-satellite point on the WGS-84 ellipsoid (for maps); altitude_km above stays |r| - 6371
    lat_deg, lon_deg, height_km = geodetic.teme_to_geodetic_scalar(x, y, z, jd, fr)

    return {
        "name": tle["name"],
        "norad_id": int(tle["line1"][2:7]),  # fixed-width TLE column, always 5 digits
        "timestamp_utc": when.isoformat(),
        "position_km": {"x": round(x, 3), "y": round(y, 3), "z": round(z, 3)},
        "velocity_km_s": {"x": round(vx, 3), "y": round(vy, 3), "z": round(vz, 3)},
        "altitude_km": round(altitude_km, 2),
        "latitude_deg": round(lat_deg, 4),
        "longitude_deg": round(lon_deg, 4),
        "geodetic_altitude_km": round(height_km, 2),
        **tle_age_info(tle, when),
    }


MAX_SKIP_EXAMPLES = 20


def propagate_many_with_stats(tles: list[dict], when: datetime | None = None) -> dict:
    """
    Propagate a list of TLEs and report everything that was left out.

    Objects that cannot be propagated (decayed, malformed, SGP4 error) are skipped so one
    bad TLE cannot sink the batch - but they are counted, not silently dropped:

        {"objects": [...],
         "skipped": {"count", "malformed", "sgp4_error", "by_error_code", "examples"},
         "tle_staleness": {"fresh", "stale", "unreliable", "oldest_age_days"}}
    """
    objects = []
    skipped = {"count": 0, "malformed": 0, "sgp4_error": 0, "by_error_code": {}, "examples": []}

    def _skip(tle, kind, reason, code=None):
        skipped["count"] += 1
        skipped[kind] += 1
        if code is not None:
            skipped["by_error_code"][str(code)] = skipped["by_error_code"].get(str(code), 0) + 1
        if len(skipped["examples"]) < MAX_SKIP_EXAMPLES:
            try:
                norad = int(tle["line1"][2:7])
            except Exception:
                norad = None
            skipped["examples"].append({"name": tle.get("name") if isinstance(tle, dict) else None,
                                        "norad_id": norad, "reason": reason})

    for tle in tles:
        try:
            objects.append(propagate(tle, when))
        except MalformedTLE as exc:
            _skip(tle, "malformed", str(exc))
        except PropagationError as exc:
            _skip(tle, "sgp4_error", str(exc), exc.code)
        except RuntimeError as exc:
            _skip(tle, "sgp4_error", str(exc))
        except (ValueError, KeyError, TypeError, IndexError) as exc:
            # twoline2rv raises ValueError on a malformed TLE
            _skip(tle, "malformed", f"malformed TLE: {exc}")

    staleness = summarize_staleness(
        {k: o[k] for k in ("tle_status", "tle_age_days")} for o in objects
    )
    return {"objects": objects, "skipped": skipped, "tle_staleness": staleness}


def propagate_many(tles: list[dict], when: datetime | None = None) -> list[dict]:
    """Propagate a list of TLEs, skipping any that error out (use propagate_many_with_stats to see which)."""
    return propagate_many_with_stats(tles, when)["objects"]


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
            for key in TLE_FIELDS:
                point.pop(key, None)
            point["hours_from_now"] = h
            trajectory.append(point)
        except RuntimeError:
            continue   # callers can compare len(trajectory) with len(hours_ahead)
    return trajectory
