"""Tests for time-window conjunction screening (offline, synthetic TLEs)."""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient
from sgp4.api import Satrec, WGS72, jday

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import conjunction as conj
import conjunction_window as cw
import orbit_engine as engine
import main
from tle_factory import make_tle

MM = 15.50549723
START = datetime(2024, 8, 22, 4, 0, 0, tzinfo=timezone.utc)   # TLE epoch is ~03:50 UTC

ISS = {
    "name": "ISS (ZARYA)",
    "line1": "1 25544U 98067A   24235.16000531  .00028314  00000+0  49252-3 0  9994",
    "line2": "2 25544  51.6402 348.4828 0004893 236.4095 123.6428 15.50549723468780",
}
# Same altitude as the ISS but a 98 deg orbit; phased (by search) to cross the ISS's
# path about 7788 s after START, passing ~2.4 km away at ~6 km/s relative speed.
CROSSER = make_tle(90001, "CROSSER", 98.0, 348.4828, 124.157, mean_motion=MM)
# Same orbit as CROSSER but 90 degrees behind: never meets the ISS in this window.
FAR = make_tle(90002, "FAR", 98.0, 348.4828, 214.157, mean_motion=MM)
# ISS orbit, 0.02 deg ahead (~2.4 km): flies in formation with the ISS (like a docked vehicle).
FORMATION = make_tle(90003, "FORMATION", 51.6402, 348.4828, 123.6428 + 0.02, mean_motion=MM)


def _brute_force_min(tle_a, tle_b, center: datetime, half_width_s=5.0, step_s=0.05):
    """Ground truth: scan distance at fine resolution around a time."""
    a = Satrec.twoline2rv(tle_a["line1"], tle_a["line2"], WGS72)
    b = Satrec.twoline2rv(tle_b["line1"], tle_b["line2"], WGS72)
    jd, fr = jday(center.year, center.month, center.day, center.hour, center.minute,
                  center.second + center.microsecond / 1e6)
    offs = np.arange(-half_width_s, half_width_s, step_s)
    _, ra, _ = a.sgp4_array(np.full(len(offs), jd), fr + offs / 86400)
    _, rb, _ = b.sgp4_array(np.full(len(offs), jd), fr + offs / 86400)
    d = np.linalg.norm(ra - rb, axis=1)
    return float(d.min()), float(offs[d.argmin()])


def _pairs(result):
    return {(c["object_1"]["norad_id"], c["object_2"]["norad_id"]) for c in result["conjunctions"]}


def test_finds_crossing_and_matches_brute_force():
    res = cw.find_conjunctions_in_window([ISS, CROSSER, FAR], start=START, hours=3)
    assert _pairs(res) == {(25544, 90001)}
    c = res["conjunctions"][0]

    tca = datetime.fromisoformat(c["tca_utc"])
    truth_miss, truth_off = _brute_force_min(ISS, CROSSER, tca)
    assert abs(c["miss_distance_km"] - truth_miss) < 0.01
    assert abs(truth_off) < 0.15                       # TCA within 0.15 s of the true minimum
    assert abs(c["hours_from_start"] * 3600 - 7788) < 2
    assert c["relative_velocity_km_s"] > 5             # a genuine crossing, not formation flight
    assert c["risk_level"] == "MEDIUM" and c["co_orbiting"] is False


def test_snapshot_detector_misses_what_the_window_scan_finds():
    """The motivating gap: at START the two satellites are ~thousands of km apart."""
    objs = engine.propagate_many([ISS, CROSSER], when=START)
    assert conj.find_conjunctions_naive(objs, threshold_km=5.0) == []
    assert len(cw.find_conjunctions_in_window([ISS, CROSSER], start=START, hours=3)["conjunctions"]) == 1


def test_no_conjunction_when_phased_away():
    res = cw.find_conjunctions_in_window([ISS, FAR], start=START, hours=3)
    assert res["conjunctions"] == []


def test_threshold_is_respected():
    assert cw.find_conjunctions_in_window([ISS, CROSSER], start=START, hours=3, threshold_km=2.0)["conjunctions"] == []
    assert len(cw.find_conjunctions_in_window([ISS, CROSSER], start=START, hours=3, threshold_km=3.0)["conjunctions"]) == 1


def test_event_outside_window_is_excluded():
    # window ends ~10 min before the TCA
    assert cw.find_conjunctions_in_window([ISS, CROSSER], start=START, hours=2.0)["conjunctions"] == []
    # window starts ~10 min after the TCA (objects already moving apart)
    late = START + timedelta(seconds=7788 + 600)
    assert cw.find_conjunctions_in_window([ISS, CROSSER], start=late, hours=0.5)["conjunctions"] == []


def test_step_size_does_not_change_the_answer():
    fine = cw.find_conjunctions_in_window([ISS, CROSSER], start=START, hours=3, step_seconds=20)
    coarse = cw.find_conjunctions_in_window([ISS, CROSSER], start=START, hours=3, step_seconds=240)
    a, b = fine["conjunctions"][0], coarse["conjunctions"][0]
    assert abs(a["miss_distance_km"] - b["miss_distance_km"]) < 0.01
    assert abs(a["hours_from_start"] - b["hours_from_start"]) * 3600 < 0.1


def test_formation_flight_excluded_by_default_included_on_request():
    default = cw.find_conjunctions_in_window([ISS, FORMATION], start=START, hours=1)
    assert default["conjunctions"] == []
    assert default["excluded_coorbiting_pairs"] == 1

    inc = cw.find_conjunctions_in_window([ISS, FORMATION], start=START, hours=1, include_coorbiting=True)
    assert len(inc["conjunctions"]) == 1
    c = inc["conjunctions"][0]
    assert c["co_orbiting"] is True and c["relative_velocity_km_s"] < 0.1 and c["miss_distance_km"] < 5


def test_unpropagatable_objects_are_counted_not_fatal():
    stale = datetime(2026, 10, 17, tzinfo=timezone.utc)      # ISS TLE is 2 years old by then
    res = cw.find_conjunctions_in_window([ISS, CROSSER], start=stale, hours=1)
    assert res["objects_checked"] + res["objects_unpropagatable"] == 2
    assert res["conjunctions"] == []


def test_malformed_tle_is_skipped():
    bad = {"name": "BAD", "line1": "garbage", "line2": "garbage"}
    res = cw.find_conjunctions_in_window([bad, ISS, CROSSER], start=START, hours=3)
    assert res["objects_unpropagatable"] == 1 and len(res["conjunctions"]) == 1
    # names/ids must still line up with the right satellites after skipping the bad one
    assert _pairs(res) == {(25544, 90001)}
    c = res["conjunctions"][0]
    assert (c["object_1"]["name"], c["object_2"]["name"]) == ("ISS (ZARYA)", "CROSSER")


@pytest.mark.parametrize("kwargs", [
    {"hours": 0}, {"hours": 100}, {"step_seconds": 1}, {"step_seconds": 1000}, {"threshold_km": 0},
])
def test_module_validates_arguments(kwargs):
    with pytest.raises(ValueError):
        cw.find_conjunctions_in_window([ISS, CROSSER], start=START, **kwargs)


# ---------------- API endpoint ----------------
@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(main, "_get_tles", lambda group="stations", limit=None, force_refresh=False: [ISS, CROSSER, FAR])
    return TestClient(main.app)


def test_endpoint_returns_forecast(client):
    r = client.get("/conjunctions/forecast", params={"start": "2024-08-22T04:00:00Z", "hours": 3})
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 1 and body["objects_checked"] == 3
    c = body["conjunctions"][0]
    assert c["miss_distance_km"] < 5 and "tca_utc" in c and "risk_level" in c


def test_endpoint_ml_flag_adds_scores(client):
    r = client.get("/conjunctions/forecast", params={"start": "2024-08-22T04:00:00Z", "hours": 3, "ml": True})
    assert r.status_code == 200
    assert "ml_risk_level" in r.json()["conjunctions"][0]


@pytest.mark.parametrize("params", [
    {"hours": 0}, {"hours": 500}, {"step_seconds": 2}, {"threshold_km": -1}, {"start": "not-a-date"},
])
def test_endpoint_rejects_bad_input_with_400(client, params):
    assert client.get("/conjunctions/forecast", params=params).status_code == 400


def test_endpoint_guards_against_oversized_requests(client, monkeypatch):
    monkeypatch.setattr(main, "MAX_FORECAST_WORK", 10)
    r = client.get("/conjunctions/forecast", params={"start": "2024-08-22T04:00:00Z", "hours": 3})
    assert r.status_code == 400 and "too much work" in r.json()["detail"]


def test_old_snapshot_endpoint_still_works(client, monkeypatch):
    real = engine.propagate
    monkeypatch.setattr(engine, "propagate", lambda tle, when=None: real(tle, START))
    assert client.get("/conjunctions").status_code == 200


# ---------------- recall against brute force ----------------
@pytest.mark.parametrize("step_seconds", [30, 60, 300])
def test_no_conjunction_is_missed_vs_brute_force(step_seconds):
    """
    Compare against an exhaustive 1-second scan of every pair on a seeded random catalog.
    Any event the brute force finds but the detector misses fails the test (and vice versa).
    """
    import itertools
    from sgp4.api import SatrecArray
    from tle_factory import random_leo_tles

    n, hours, thr = 120, 3, 80.0
    tles = random_leo_tles(n)
    res = cw.find_conjunctions_in_window(tles, start=START, hours=hours, threshold_km=thr,
                                         step_seconds=step_seconds)

    sats = [Satrec.twoline2rv(t["line1"], t["line2"], WGS72) for t in tles]
    jd, fr = jday(START.year, START.month, START.day, START.hour, START.minute, 0)
    secs = np.arange(0, hours * 3600 + 1, 1.0)
    err, R, V = SatrecArray(sats).sgp4(np.full(len(secs), jd), fr + secs / 86400)
    R[err != 0] = np.nan
    V[err != 0] = np.nan

    truth = []
    for i, j in itertools.combinations(range(n), 2):
        d = np.linalg.norm(R[i] - R[j], axis=1)
        m = np.zeros(len(d), bool)
        m[1:-1] = (d[1:-1] < d[:-2]) & (d[1:-1] <= d[2:])
        m &= np.isfinite(d) & (d < thr)
        for k in np.nonzero(m)[0]:
            if np.linalg.norm(V[i, k] - V[j, k]) >= 0.1:
                truth.append((10000 + i, 10000 + j, float(secs[k])))

    found = [(c["object_1"]["norad_id"], c["object_2"]["norad_id"], c["hours_from_start"] * 3600)
             for c in res["conjunctions"]]
    assert len(truth) >= 5, "test data should contain several events"
    missed = [t for t in truth if not any(a == t[0] and b == t[1] and abs(s - t[2]) < 3 for a, b, s in found)]
    extra = [f for f in found if not any(f[0] == t[0] and f[1] == t[1] and abs(f[2] - t[2]) < 3 for t in truth)]
    assert missed == [] and extra == []
