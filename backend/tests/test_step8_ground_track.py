"""Step 8: latitude / longitude on every object, and a ground-track endpoint. Offline."""
import math
import sys
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient
from sgp4.propagation import gstime

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import geodetic
import ground_track
import main
import orbit_engine as engine
from tle_factory import ISS_LINE1

ISS = {"name": "ISS (ZARYA)", "line1": ISS_LINE1,
       "line2": "2 25544  51.6402 348.4828 0004893 236.4095 123.6428 15.50549723468780"}
EPOCH = engine._tle_epoch_to_datetime(ISS["line1"])
ISS_INCLINATION = 51.6402


# ---------------------------------------------------------------- the maths
@pytest.mark.parametrize("jd", [2460544.5, 2461000.123, 2451545.0])
def test_gmst_matches_the_sgp4_library(jd):
    assert float(geodetic.gmst_rad(jd, 0.0)) == pytest.approx(gstime(jd), abs=1e-9)


def _ecef_to_teme(lat_deg, lon_deg, h_km, jd, fr):
    a, e2 = geodetic.WGS84_A_KM, geodetic.WGS84_E2
    la, lo = math.radians(lat_deg), math.radians(lon_deg)
    n = a / math.sqrt(1 - e2 * math.sin(la) ** 2)
    ex, ey = (n + h_km) * math.cos(la) * math.cos(lo), (n + h_km) * math.cos(la) * math.sin(lo)
    ez = (n * (1 - e2) + h_km) * math.sin(la)
    th = float(geodetic.gmst_rad(jd, fr))
    c, s = math.cos(th), math.sin(th)
    return [c * ex - s * ey, s * ex + c * ey, ez]


@pytest.mark.parametrize("lat,lon", [(45, 30), (89.9, -170), (-60, 179.9), (0, 0), (-89.99, 10), (0.001, -179.99)])
def test_round_trip_ellipsoid_to_geodetic(lat, lon):
    jd, fr = 2460544.5, 0.3
    got = geodetic.teme_to_geodetic([_ecef_to_teme(lat, lon, 500.0, jd, fr)], jd, fr)
    assert got[0][0] == pytest.approx(lat, abs=1e-6)
    assert ((got[1][0] - lon + 180) % 360 - 180) == pytest.approx(0, abs=1e-6)
    assert got[2][0] == pytest.approx(500.0, abs=1e-4)


def test_height_uses_the_ellipsoid_not_a_sphere():
    lat, lon, h = geodetic.teme_to_geodetic([[0, 0, 7000.0], [7000.0, 0, 0]], 2460544.5, 0.0)
    assert lat[0] == pytest.approx(90.0)
    assert h[0] == pytest.approx(7000.0 - 6356.7523, abs=0.01)       # polar radius
    assert h[1] == pytest.approx(7000.0 - 6378.137, abs=0.01)        # equatorial radius


def test_scalar_and_array_versions_agree():
    rng = np.random.default_rng(3)
    pts = rng.normal(size=(300, 3)) * 4000
    la, lo, h = geodetic.teme_to_geodetic(pts, 2460544.5, 0.3)
    for p, a, b, c in zip(pts, la, lo, h):
        sa, sb, sc = geodetic.teme_to_geodetic_scalar(*p, 2460544.5, 0.3)
        assert sa == pytest.approx(a, abs=1e-6) and sc == pytest.approx(c, abs=1e-5)
        assert (sb - b + 180) % 360 - 180 == pytest.approx(0, abs=1e-6)


# ---------------------------------------------------------------- engine + ground track
def test_propagate_reports_lat_lon_within_the_orbit_inclination():
    seen = []
    for k in range(0, 93 * 60, 300):
        p = engine.propagate(ISS, EPOCH.replace(microsecond=0) + __import__("datetime").timedelta(seconds=k))
        assert -180 <= p["longitude_deg"] < 180
        assert abs(p["latitude_deg"]) <= ISS_INCLINATION + 0.35
        assert 380 < p["geodetic_altitude_km"] < 460
        seen.append(p["latitude_deg"])
    assert max(seen) > 45 and min(seen) < -45                 # a full orbit reaches both extremes


def test_ground_track_shape_and_segments():
    t = ground_track.compute_ground_track(ISS, start=EPOCH, hours=3, step_seconds=30)
    assert t["count"] == 361 and t["skipped_points"] == 0 and len(t["points"]) == 361
    assert t["segments"] and sum(len(s) for s in t["segments"]) == 361
    assert len(t["segments"]) >= 2                              # 3 h is ~2 orbits: it must cross the antimeridian
    for seg in t["segments"]:
        lons = [p[0] for p in seg]
        assert max(abs(b - a) for a, b in zip(lons, lons[1:])) < 180 if len(lons) > 1 else True
    assert all(abs(p["lat"]) <= ISS_INCLINATION + 0.35 for p in t["points"])


def test_ground_track_matches_engine_propagate():
    t = ground_track.compute_ground_track(ISS, start=EPOCH, hours=0.2, step_seconds=60)
    p = t["points"][5]
    ref = engine.propagate(ISS, EPOCH + __import__("datetime").timedelta(seconds=300))
    assert p["lat"] == pytest.approx(ref["latitude_deg"], abs=1e-3)
    assert p["lon"] == pytest.approx(ref["longitude_deg"], abs=1e-3)


@pytest.mark.parametrize("hours,step", [(0, 30), (-1, 30), (100, 30), (1, 1), (1, 9999), (72, 5)])
def test_ground_track_rejects_bad_parameters(hours, step):
    with pytest.raises(ValueError):
        ground_track.validate_params(hours, step)


def test_ground_track_counts_unpropagatable_points_instead_of_hiding_them():
    far = EPOCH.replace(year=EPOCH.year + 40)           # SGP4 gives up (or decays) this far from epoch
    t = ground_track.compute_ground_track(ISS, start=far, hours=1, step_seconds=60)
    assert t["skipped_points"] + t["count"] == 61


# ---------------------------------------------------------------- endpoints
@pytest.fixture
def client(monkeypatch):
    from test_step3_cache_staleness import fresh_tle        # epoch = now, so "now" endpoints can propagate
    monkeypatch.setattr(engine, "fetch_tle", lambda n: fresh_tle(n, days_old=0.5))
    return TestClient(main.app)


def test_ground_track_endpoint(client):
    r = client.get("/ground-track/25544", params={"hours": 2, "step_seconds": 60})
    assert r.status_code == 200
    body = r.json()
    assert body["norad_id"] == 25544 and body["count"] == 121 and body["segments"]
    assert {"t", "lat", "lon", "height_km"} <= body["points"][0].keys()


@pytest.mark.parametrize("params", [{"hours": 0}, {"hours": 500}, {"step_seconds": 1}, {"start": "yesterday"}])
def test_ground_track_endpoint_validation_is_400(client, params):
    assert client.get("/ground-track/25544", params=params).status_code == 400


def test_object_endpoints_now_include_lat_lon(client):
    body = client.get("/objects/25544").json()
    assert {"latitude_deg", "longitude_deg", "geodetic_altitude_km"} <= body.keys()
    traj = client.get("/trajectory/25544?hours=0,1").json()["trajectory"]
    assert all("latitude_deg" in p for p in traj)
