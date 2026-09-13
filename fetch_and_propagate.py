"""
OrbitGuard - Day 1 script (Person 1 track)
--------------------------------------------
Goal: Fetch real orbital data (TLE) for the ISS from CelesTrak and use SGP4
to calculate its current position (lat/lon/altitude + ECI x,y,z in km).

Usage:
    python fetch_and_propagate.py                # fetch live ISS TLE
    python fetch_and_propagate.py --norad 25544   # fetch any object by NORAD ID
    python fetch_and_propagate.py --offline       # use a bundled sample TLE (no network)
"""

import argparse
import sys
from datetime import datetime, timezone

import requests
from sgp4.api import Satrec, WGS72
from sgp4.api import jday

# A real ISS TLE, used only as a fallback so this script still runs somewhere
# with no internet access. It will get stale (TLEs are only accurate for a
# few days), so always prefer the live fetch below.
SAMPLE_TLE = {
    "name": "ISS (ZARYA)",
    "line1": "1 25544U 98067A   24235.16000531  .00028314  00000+0  49252-3 0  9994",
    "line2": "2 25544  51.6402 348.4828 0004893 236.4095 123.6428 15.50549723468780",
}

CELESTRAK_URL = "https://celestrak.org/NORAD/elements/gp.php"


def _tle_epoch_to_datetime(line1: str) -> datetime:
    """Parse the epoch (columns 19-32) out of TLE line 1 into a UTC datetime."""
    epoch_str = line1[18:32].strip()  # e.g. "24235.16000531"
    year_two_digit = int(epoch_str[:2])
    day_of_year = float(epoch_str[2:])
    year = 2000 + year_two_digit if year_two_digit < 57 else 1900 + year_two_digit
    from datetime import timedelta
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


def propagate(tle: dict, when: datetime | None = None) -> dict:
    """Run SGP4 on a TLE for a given UTC datetime (defaults to now)."""
    when = when or datetime.now(timezone.utc)

    sat = Satrec.twoline2rv(tle["line1"], tle["line2"], WGS72)
    jd, fr = jday(when.year, when.month, when.day, when.hour, when.minute, when.second)

    error_code, position, velocity = sat.sgp4(jd, fr)
    if error_code != 0:
        raise RuntimeError(f"SGP4 propagation error code {error_code} for {tle['name']}")

    x, y, z = position  # km, TEME (True Equator, Mean Equinox) frame
    vx, vy, vz = velocity  # km/s

    # Rough altitude estimate: distance from Earth's centre minus mean radius.
    earth_radius_km = 6371.0
    import math
    radius = math.sqrt(x**2 + y**2 + z**2)
    altitude_km = radius - earth_radius_km

    return {
        "name": tle["name"],
        "norad_id": tle["line1"].split()[1].rstrip("U"),
        "timestamp_utc": when.isoformat(),
        "position_km": {"x": round(x, 3), "y": round(y, 3), "z": round(z, 3)},
        "velocity_km_s": {"x": round(vx, 3), "y": round(vy, 3), "z": round(vz, 3)},
        "altitude_km": round(altitude_km, 2),
    }


def main():
    parser = argparse.ArgumentParser(description="OrbitGuard Day 1: fetch TLE + SGP4 propagate")
    parser.add_argument("--norad", type=int, default=25544, help="NORAD catalog ID (default: ISS = 25544)")
    parser.add_argument("--offline", action="store_true", help="Use bundled sample TLE instead of live fetch")
    args = parser.parse_args()

    when = None
    if args.offline:
        print("Using bundled sample TLE (offline mode) — this TLE is old, so we")
        print("propagate to its own epoch rather than 'now' (an aged TLE gives")
        print("nonsense/decayed results if pushed years past its epoch).\n")
        tle = SAMPLE_TLE
        when = _tle_epoch_to_datetime(tle["line1"])
    else:
        try:
            print(f"Fetching live TLE for NORAD ID {args.norad} from CelesTrak...")
            tle = fetch_tle(args.norad)
        except Exception as exc:
            print(f"Live fetch failed ({exc}); falling back to bundled sample TLE.\n", file=sys.stderr)
            tle = SAMPLE_TLE
            when = _tle_epoch_to_datetime(tle["line1"])

    result = propagate(tle, when)

    print(f"\n{result['name']}")
    print(f"NORAD ID: {result['norad_id']}")
    print(f"Time (UTC): {result['timestamp_utc']}")
    print(f"Position (km, ECI): {result['position_km']}")
    print(f"Velocity (km/s):    {result['velocity_km_s']}")
    print(f"Altitude (km):      {result['altitude_km']}")


if __name__ == "__main__":
    main()
