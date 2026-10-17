"""Step 6: GET /watchlist/alerts and the focus filter behind it. CelesTrak is mocked (offline)."""
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest
import requests
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import conjunction_window as cw
import main
import orbit_engine as engine
from test_step2_window import CROSSER, FAR, FORMATION, ISS, START
from tle_factory import make_tle, random_leo_tles

START_Q = "2024-08-22T04:00:00Z"        # same window as the step 2 tests (ISS TLE epoch ~03:50)
ISS_ID, CROSSER_ID = 25544, 90001
# two satellites on the same orbit, a couple of km apart: a close pair that involves neither ISS nor CROSSER
PAIR_A = make_tle(91001, "PAIR-A", 70.0, 100.0, 50.0)
PAIR_B = make_tle(91002, "PAIR-B", 70.0, 100.0, 50.0 + 0.0008)


def catalog(n_random=100):
    return [ISS, CROSSER, FAR, FORMATION, PAIR_A, PAIR_B] + random_leo_tles(n_random)


def _norad(t):
    return int(t["line1"][2:7])


def _key(c):
    return (c["object_1"]["norad_id"], c["object_2"]["norad_id"], c["tca_utc"], c["miss_distance_km"])


# ============================ focus filter (module level) ============================
def test_pair_a_b_really_is_a_close_pair():
    """Guards the test data: without it the 'unwatched pair is excluded' tests prove nothing."""
    out = cw.find_conjunctions_in_window([PAIR_A, PAIR_B], start=START, hours=3, threshold_km=5.0,
                                         include_coorbiting=True)
    assert out["conjunctions"], "PAIR-A/PAIR-B must be within 5 km of each other"


@pytest.mark.parametrize("focus", [{ISS_ID}, {CROSSER_ID}, {ISS_ID, CROSSER_ID}, {91001}, {99999}])
def test_focus_equals_full_result_filtered(focus):
    tles = catalog()
    full = cw.find_conjunctions_in_window(tles, start=START, hours=6, include_coorbiting=True)
    part = cw.find_conjunctions_in_window(tles, start=START, hours=6, include_coorbiting=True,
                                          focus_norad_ids=focus)
    want = [c for c in full["conjunctions"]
            if c["object_1"]["norad_id"] in focus or c["object_2"]["norad_id"] in focus]
    assert sorted(map(_key, part["conjunctions"])) == sorted(map(_key, want))


def test_focus_finds_the_known_crossing_and_nothing_unrelated():
    part = cw.find_conjunctions_in_window(catalog(), start=START, hours=3, focus_norad_ids={ISS_ID})
    ids = {frozenset((c["object_1"]["norad_id"], c["object_2"]["norad_id"])) for c in part["conjunctions"]}
    assert frozenset((ISS_ID, CROSSER_ID)) in ids
    assert frozenset((91001, 91002)) not in ids


def test_pair_of_two_focus_objects_is_reported_once():
    part = cw.find_conjunctions_in_window(catalog(), start=START, hours=3,
                                          focus_norad_ids={ISS_ID, CROSSER_ID})
    n = sum(1 for c in part["conjunctions"]
            if {c["object_1"]["norad_id"], c["object_2"]["norad_id"]} == {ISS_ID, CROSSER_ID})
    assert n == 1


# ============================ endpoint ============================
@pytest.fixture
def env(monkeypatch):
    """Client + helpers; engine.fetch_tle / fetch_many serve the synthetic catalog."""
    tles = {_norad(t): t for t in catalog()}
    calls = {"fetch_tle": [], "fetch_many": 0}

    def fetch_tle(nid):
        calls["fetch_tle"].append(nid)
        if nid not in tles:
            raise engine.TLENotFound(f"No TLE found for NORAD ID {nid}")
        return tles[nid]

    def fetch_many(group="stations", limit=None):
        calls["fetch_many"] += 1
        return list(tles.values())

    monkeypatch.setattr(engine, "fetch_tle", fetch_tle)
    monkeypatch.setattr(engine, "fetch_many", fetch_many)
    client = TestClient(main.app)

    def user(email="a@example.com"):
        tok = client.post("/auth/register", json={"name": "A", "email": email,
                                                  "password": "password123"}).json()["access_token"]
        return {"Authorization": f"Bearer {tok}"}

    def watch(h, *ids):
        for i in ids:
            assert client.post("/watchlist", json={"norad_id": i}, headers=h).status_code == 201

    return client, user, watch, calls


def test_requires_login(env):
    client, *_ = env
    assert client.get("/watchlist/alerts").status_code == 401


def test_alert_for_watched_satellite(env):
    client, user, watch, _ = env
    h = user()
    watch(h, ISS_ID)
    r = client.get(f"/watchlist/alerts?start={START_Q}&hours=3", headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    pairs = [{c["object_1"]["norad_id"], c["object_2"]["norad_id"]} for c in body["conjunctions"]]
    assert {ISS_ID, CROSSER_ID} in pairs
    assert {91001, 91002} not in pairs                     # not the user's business
    assert all(ISS_ID in c["watched_norad_ids"] for c in body["conjunctions"])
    iss = next(s for s in body["satellites"] if s["norad_id"] == ISS_ID)
    assert iss["status"] == "ok" and iss["alert_count"] >= 1
    assert 2.0 < iss["closest_miss_km"] < 3.0              # the known ~2.4 km crossing
    assert iss["next_tca_utc"] and iss["highest_risk"] in ("MEDIUM", "HIGH")
    assert body["count"] == len(body["conjunctions"])


def test_two_watched_satellites_in_one_conjunction(env):
    client, user, watch, _ = env
    h = user()
    watch(h, ISS_ID, CROSSER_ID)
    body = client.get(f"/watchlist/alerts?start={START_Q}&hours=3", headers=h).json()
    shared = [c for c in body["conjunctions"]
              if {c["object_1"]["norad_id"], c["object_2"]["norad_id"]} == {ISS_ID, CROSSER_ID}]
    assert len(shared) == 1 and sorted(shared[0]["watched_norad_ids"]) == [ISS_ID, CROSSER_ID]
    by_id = {s["norad_id"]: s for s in body["satellites"]}
    assert by_id[ISS_ID]["alert_count"] >= 1 and by_id[CROSSER_ID]["alert_count"] >= 1


def test_quiet_satellite_reports_zero_alerts_not_an_error(env):
    client, user, watch, _ = env
    h = user()
    watch(h, 90002)                                        # FAR: nothing near it in this window
    body = client.get(f"/watchlist/alerts?start={START_Q}&hours=3", headers=h).json()
    s = body["satellites"][0]
    assert s["status"] == "ok" and s["alert_count"] == 0 and s["closest_miss_km"] is None
    assert body["count"] == 0


def test_alerts_sorted_soonest_first(env):
    client, user, watch, _ = env
    h = user()
    watch(h, ISS_ID, 91001)
    body = client.get(f"/watchlist/alerts?start={START_Q}&hours=6&include_coorbiting=true", headers=h).json()
    tcas = [c["tca_utc"] for c in body["conjunctions"]]
    assert len(tcas) >= 2 and tcas == sorted(tcas)


def test_empty_watchlist_costs_nothing(env):
    client, user, _, calls = env
    h = user()
    body = client.get("/watchlist/alerts", headers=h).json()
    assert body["count"] == 0 and body["watchlist_count"] == 0 and body["warnings"]
    assert calls["fetch_many"] == 0 and calls["fetch_tle"] == []


def test_unfetchable_satellite_is_reported_not_silently_dropped(env):
    client, user, watch, _ = env
    h = user()
    watch(h, ISS_ID, 99999)                                # 99999 does not exist
    body = client.get(f"/watchlist/alerts?start={START_Q}&hours=3", headers=h).json()
    by_id = {s["norad_id"]: s for s in body["satellites"]}
    assert by_id[99999]["status"] == "unavailable" and "99999" in by_id[99999]["reason"]
    assert by_id[ISS_ID]["status"] == "ok" and by_id[ISS_ID]["alert_count"] >= 1   # others unaffected
    assert any("could not be checked" in w for w in body["warnings"])


def test_satellite_that_cannot_be_propagated_is_marked_unavailable(env):
    """A 2024 TLE cannot be propagated to today's date - 'no alerts' would be a lie there."""
    client, user, watch, _ = env
    h = user()
    watch(h, ISS_ID)
    body = client.get("/watchlist/alerts?hours=3", headers=h).json()      # default start = now
    s = body["satellites"][0]
    assert s["status"] == "unavailable" and s["reason"]
    assert body["count"] == 0


def test_each_user_only_sees_their_own_watchlist(env):
    client, user, watch, _ = env
    a, b = user("a@example.com"), user("b@example.com")
    watch(a, ISS_ID)
    watch(b, 90002)
    body = client.get(f"/watchlist/alerts?start={START_Q}&hours=3", headers=b).json()
    assert [s["norad_id"] for s in body["satellites"]] == [90002]
    assert body["count"] == 0


def test_stale_tle_is_flagged_on_the_alert(env):
    client, user, watch, _ = env
    h = user()
    watch(h, ISS_ID)
    # screen 10 days after the TLE epoch: SGP4 still runs, but the TLE is stale
    body = client.get("/watchlist/alerts?start=2024-09-01T04:00:00Z&hours=3", headers=h).json()
    iss = body["satellites"][0]
    assert iss["status"] == "ok" and iss["tle_status"] in ("stale", "unreliable")
    assert body["tle_staleness"]["stale"] + body["tle_staleness"]["unreliable"] >= 1


@pytest.mark.parametrize("q", ["hours=0", "hours=100", "threshold_km=0", "step_seconds=1", "start=garbage"])
def test_bad_input_is_400(env, q):
    client, user, watch, _ = env
    h = user()
    watch(h, ISS_ID)
    assert client.get(f"/watchlist/alerts?{q}", headers=h).status_code == 400


def test_oversized_request_is_400(env, monkeypatch):
    import forecast_service
    monkeypatch.setattr(forecast_service, "MAX_FORECAST_WORK", 10)
    client, user, watch, _ = env
    h = user()
    watch(h, ISS_ID)
    r = client.get(f"/watchlist/alerts?start={START_Q}&hours=3", headers=h)
    assert r.status_code == 400 and "too much work" in r.json()["detail"]


def test_celestrak_outage_is_502(env, monkeypatch):
    client, user, watch, _ = env

    def down(*a, **k):
        raise requests.ConnectionError("boom")
    monkeypatch.setattr(engine, "fetch_many", down)
    h = user()
    watch(h, ISS_ID)
    assert client.get(f"/watchlist/alerts?start={START_Q}&hours=3", headers=h).status_code == 502


def test_rate_limited_per_user(env):
    client, user, watch, _ = env
    h = user()
    codes = [client.get("/watchlist/alerts", headers=h).status_code for _ in range(8)]
    assert codes[:6] == [200] * 6
    assert codes[6] == 429
    r = client.get("/watchlist/alerts", headers=h)
    assert r.status_code == 429 and int(r.headers["Retry-After"]) >= 1
    other = user("other@example.com")                       # someone else is unaffected
    assert client.get("/watchlist/alerts", headers=other).status_code == 200


def test_ml_flag_adds_scores(env):
    client, user, watch, _ = env
    h = user()
    watch(h, ISS_ID)
    body = client.get(f"/watchlist/alerts?start={START_Q}&hours=3&ml=true", headers=h).json()
    assert body["count"] >= 1 and all("ml_risk_level" in c for c in body["conjunctions"])


def test_large_catalog_end_to_end(env, monkeypatch):
    """~2,000-object catalog through the API, 3 watched satellites: finds the crossing, quickly."""
    client, user, watch, _ = env
    big = catalog(2000)
    monkeypatch.setattr(engine, "fetch_many", lambda group="stations", limit=None: list(big))
    h = user()
    watch(h, ISS_ID, 91001)
    t = time.perf_counter()
    r = client.get(f"/watchlist/alerts?start={START_Q}&hours=6", headers=h)
    assert r.status_code == 200
    assert time.perf_counter() - t < 20
    pairs = [{c["object_1"]["norad_id"], c["object_2"]["norad_id"]} for c in r.json()["conjunctions"]]
    assert {ISS_ID, CROSSER_ID} in pairs
