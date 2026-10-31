"""Step 7: real what-if maneuver (delta-v -> re-propagate -> new TCA / miss distance). Offline."""
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import main
import maneuver
import orbit_engine as engine
from tle_factory import make_tle

# Two circular orbits (51.6 and 98 deg) with the same RAAN: they cross at the nodes, ~13 min after epoch.
A = make_tle(40001, "A", 51.6402, 100.0, 128.0, ecc=0, argp=0.0)
B = make_tle(40002, "B", 98.0, 100.0, 128.0, ecc=0, argp=0.0)
EPOCH = engine._tle_epoch_to_datetime(A["line1"])


def run(**kw):
    kw.setdefault("window_hours", 3.0)
    return maneuver.analyze_maneuver(A, B, start=EPOCH, **kw)


def offset_s(iso: str) -> float:
    return (datetime.fromisoformat(iso) - EPOCH).total_seconds()


# ---------------------------------------------------------------- physics
@pytest.mark.parametrize("orbits", [0.25, 1, 2, 3])
def test_numerical_burn_effect_matches_clohessy_wiltshire(orbits):
    """Along-track burn on a circular orbit: the textbook relative-motion solution is the reference."""
    r = 6778.0
    r0 = np.array([r, 0.0, 0.0])
    vc = math.sqrt(maneuver.MU / r)
    v0 = np.array([0.0, vc * math.cos(math.radians(51.6)), vc * math.sin(math.radians(51.6))])
    dv = maneuver.rtn_to_inertial(r0, v0, [0.0, 0.001, 0.0])      # 1 m/s prograde
    n = math.sqrt(maneuver.MU / r ** 3)
    t = orbits * 2 * math.pi / n
    along = 0.001 / n * (4 * math.sin(n * t) - 3 * n * t)
    radial = 0.001 / n * 2 * (1 - math.cos(n * t))
    expected = math.hypot(along, radial)
    got = np.linalg.norm(maneuver.make_burn_effect(r0, v0, dv, 3.5 * 2 * math.pi / n)(t)[:3])
    assert got == pytest.approx(expected, rel=0.02)            # J2 explains the small remainder


def test_rtn_frame_directions():
    r, v = np.array([7000.0, 0, 0]), np.array([0, 7.5, 0])
    assert maneuver.rtn_to_inertial(r, v, [1, 0, 0]) == pytest.approx([1, 0, 0])      # radial = away from Earth
    assert maneuver.rtn_to_inertial(r, v, [0, 1, 0]) == pytest.approx([0, 1, 0])      # along-track = prograde
    assert maneuver.rtn_to_inertial(r, v, [0, 0, 1]) == pytest.approx([0, 0, 1])      # cross-track = r x v


def test_prograde_burn_raises_semi_major_axis():
    r, v = np.array([6778.0, 0, 0]), np.array([0, 7.67, 0])
    dv = maneuver.along_track_dv_for_sma_change(r, v, 10.0)
    assert dv > 0
    v2 = v + np.array([0, dv / 1000.0, 0])
    assert maneuver.semi_major_axis_km(r, v2) - maneuver.semi_major_axis_km(r, v) == pytest.approx(10.0, rel=0.01)


# ---------------------------------------------------------------- the analysis
def test_zero_burn_changes_nothing():
    out = run()
    assert out["before"]["distance_km"] == out["after"]["distance_km"]
    assert out["before"]["tca_utc"] == out["after"]["tca_utc"]
    assert out["miss_distance_change_km"] == 0
    assert out["after"]["distance_at_original_tca_km"] == out["before"]["distance_km"]
    assert out["maneuver"]["dv_total_ms"] == 0


def test_before_numbers_do_not_depend_on_the_burn():
    plain, burned = run(), run(dv_along_ms=2.0, burn_in_hours=0.0)
    assert plain["before"] == burned["before"]


def cw_displacement_km(axis: str, dv_ms: float, t: float, r: float = 6778.0) -> float:
    """Clohessy-Wiltshire displacement t seconds after an impulse on a circular orbit."""
    n = math.sqrt(maneuver.MU / r ** 3)
    k = dv_ms / 1000.0 / n
    if axis == "dv_along_ms":
        x, y, z = 2 * k * (1 - math.cos(n * t)), k * (4 * math.sin(n * t) - 3 * n * t), 0.0
    elif axis == "dv_radial_ms":
        x, y, z = k * math.sin(n * t), 2 * k * (math.cos(n * t) - 1), 0.0
    else:
        x, y, z = 0.0, 0.0, k * math.sin(n * t)
    return math.sqrt(x * x + y * y + z * z)


@pytest.mark.parametrize("axis", ["dv_radial_ms", "dv_along_ms", "dv_cross_ms"])
def test_effect_on_the_original_encounter_is_real_but_bounded_by_the_displacement(axis):
    """Moving A by d km can change its distance to a fixed B by at most d km - and a 3 m/s burn does move it."""
    out = run(**{axis: 3.0}, burn_in_hours=0.0, window_hours=2.0)
    t = offset_s(out["closest_approaches"]["before"][0]["tca_utc"])
    change = abs(out["after"]["distance_at_original_tca_km"] - out["before"]["distance_km"])
    assert 0.01 < change <= 1.15 * cw_displacement_km(axis, 3.0, t) + 0.05
    assert out["maneuver"]["dv_total_ms"] == pytest.approx(3.0, abs=1e-3)


def test_radial_burn_can_shrink_the_miss_distance_and_the_tool_reports_it():
    """A what-if can make things better OR worse; for this pair a radial push cuts the miss by more than half."""
    out = run(dv_radial_ms=3.0, burn_in_hours=0.0, window_hours=2.0)
    assert out["after"]["distance_km"] < 0.5 * out["before"]["distance_km"]
    assert out["miss_distance_change_km"] < 0


def test_along_track_burn_moves_the_closest_approach_to_another_encounter_and_says_so():
    out = run(dv_along_ms=3.0, burn_in_hours=0.0, window_hours=3.0)
    assert offset_s(out["after"]["tca_utc"]) - offset_s(out["before"]["tca_utc"]) > 3000    # next orbit's crossing
    assert any("different encounter" in n for n in out["notes"])


def test_burn_after_the_closest_approach_cannot_change_it():
    out = run(dv_along_ms=5.0, burn_in_hours=1.0, window_hours=2.0)      # encounter is ~13 min after epoch
    assert out["after"]["distance_at_original_tca_km"] == out["before"]["distance_km"]
    assert any("before the burn" in n for n in out["notes"])


def test_longer_lead_time_gives_a_bigger_displacement():
    """The famous along-track growth: the same burn done earlier moves the object farther by a later TCA."""
    late = run(dv_along_ms=1.0, burn_in_hours=0.2, window_hours=2.0)
    early = run(dv_along_ms=1.0, burn_in_hours=0.0, window_hours=2.0)
    assert (abs(early["after"]["distance_at_original_tca_km"] - early["before"]["distance_km"])
            >= abs(late["after"]["distance_at_original_tca_km"] - late["before"]["distance_km"]))


def test_legacy_altitude_input_is_converted_and_flagged():
    out = run(altitude_delta_km=5.0, window_hours=2.0)
    assert out["maneuver"]["dv_rtn_ms"]["along_track"] > 0
    assert "deprecated" in out["deprecation"]
    assert run(window_hours=2.0)["deprecation"] is None


@pytest.mark.parametrize("kw", [
    {"window_hours": 0}, {"window_hours": -1}, {"burn_in_hours": -1},
    {"burn_in_hours": 60, "window_hours": 20}, {"step_seconds": 1}, {"step_seconds": 500},
    {"dv_along_ms": 5000.0}, {"dv_along_ms": float("nan")},
])
def test_bad_parameters_raise_value_error(kw):
    with pytest.raises(ValueError):
        run(**kw)


# ---------------------------------------------------------------- the endpoint
@pytest.fixture
def client(monkeypatch):
    tles = {40001: A, 40002: B}
    monkeypatch.setattr(engine, "fetch_tle", lambda n: tles[n])
    return TestClient(main.app)


PARAMS = {"norad_id": 40001, "other_norad_id": 40002, "start": EPOCH.isoformat(), "window_hours": 3}


def test_endpoint_returns_before_after_with_frontend_fields(client):
    body = client.get("/what-if", params={**PARAMS, "dv_along_ms": 2.0}).json()
    for side in ("before", "after"):
        assert {"distance_km", "risk_level", "tca_utc"} <= body[side].keys()
    assert body["object_1"]["norad_id"] == 40001 and body["object_2"]["norad_id"] == 40002
    assert body["maneuver"]["dv_rtn_ms"]["along_track"] == 2.0


def test_endpoint_legacy_param_still_works_and_says_so(client):
    r = client.get("/what-if", params={**PARAMS, "altitude_delta_km": 3})
    assert r.status_code == 200 and "deprecated" in r.json()["deprecation"]


def test_endpoint_rejects_mixing_legacy_and_dv(client):
    r = client.get("/what-if", params={**PARAMS, "altitude_delta_km": 3, "dv_along_ms": 1})
    assert r.status_code == 400


def test_endpoint_validation_errors_are_400(client):
    assert client.get("/what-if", params={**PARAMS, "window_hours": 100}).status_code == 400
    assert client.get("/what-if", params={**PARAMS, "start": "not-a-date"}).status_code == 400
    assert client.get("/what-if", params={"norad_id": 40001}).status_code == 422      # other id missing


# ---------------------------------------------------------------- docked / co-located pair
def test_co_located_pair_is_flagged_and_burn_effect_still_visible():
    """Two objects with identical orbital data (e.g. docked): TCA is the start instant, so the burn
    can't change the headline number - the API must say so and expose the post-burn drift."""
    twin = dict(A, name="TWIN")
    out = maneuver.analyze_maneuver(A, twin, start=EPOCH, dv_along_ms=10.0, window_hours=6.0)
    assert out["scenario"]["co_located_at_start"] is True
    assert out["before"]["distance_km"] == 0 and out["after"]["distance_km"] == 0
    assert any("co-located" in n for n in out["notes"])
    assert out["post_burn_separation_km"]["before"]["max"] == 0
    assert out["post_burn_separation_km"]["after"]["max"] > 100        # 10 m/s -> hundreds of km of drift


def test_normal_pair_not_flagged_co_located():
    assert run(dv_along_ms=1.0)["scenario"]["co_located_at_start"] is False


def test_conjunctions_endpoint_flags_co_located_pairs():
    from fastapi.testclient import TestClient
    import conjunction as conj
    objs = [
        {"name": "STATION", "norad_id": 1, "position_km": {"x": 7000.0, "y": 0.0, "z": 0.0},
         "velocity_km_s": {"x": 0.0, "y": 7.5, "z": 0.0}, "altitude_km": 400},
        {"name": "DOCKED", "norad_id": 2, "position_km": {"x": 7000.0, "y": 0.0, "z": 0.0},
         "velocity_km_s": {"x": 0.0, "y": 7.5, "z": 0.0}, "altitude_km": 400},
    ]
    res = conj.find_conjunctions_kdtree(objs, threshold_km=5.0)
    assert res and res[0]["distance_km"] == 0
    r = res[0]
    assert (r["distance_km"] < maneuver.CO_LOCATED_KM and r["relative_velocity_km_s"] < maneuver.MIN_FAST_REL_SPEED)
