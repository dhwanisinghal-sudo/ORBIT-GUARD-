"""Step 3: single-object TLE cache, stale-on-error, TLE staleness reporting, no silent drops.
CelesTrak is mocked throughout, so these run offline."""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import requests
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import auth
import cache
import orbit_engine as engine
import main
from tle_factory import ISS_LINE1, _checksum, make_tle

ISS_2024 = {
    "name": "ISS (ZARYA)",
    "line1": ISS_LINE1,
    "line2": "2 25544  51.6402 348.4828 0004893 236.4095 123.6428 15.50549723468780",
}
NOW = datetime.now(timezone.utc)


def with_epoch(tle: dict, when: datetime) -> dict:
    """Same orbit, TLE epoch moved to `when` (checksum fixed up)."""
    doy = when.timetuple().tm_yday + (when.hour * 3600 + when.minute * 60 + when.second) / 86400
    l1 = tle["line1"][:18] + f"{when.year % 100:02d}{doy:012.8f}" + tle["line1"][32:68]
    return {**tle, "line1": l1 + str(_checksum(l1))}


def fresh_tle(norad=77001, days_old=1.0, name="T"):
    return with_epoch(make_tle(norad, name, 51.6, 10.0, 20.0), NOW - timedelta(days=days_old))


class Counter:
    """A fetch_tle stand-in that counts calls per NORAD id."""

    def __init__(self, tles=None, fail=None):
        self.calls = []
        self.tles = tles or {}
        self.fail = fail or {}

    def __call__(self, norad_id):
        self.calls.append(norad_id)
        if norad_id in self.fail:
            raise self.fail[norad_id]
        return self.tles.get(norad_id) or fresh_tle(norad_id, name=f"S{norad_id}")


@pytest.fixture
def client():
    return TestClient(main.app)


# ======================= single-object cache =======================
def test_single_cache_fetches_once():
    f = Counter()
    a = cache.get_tle(100, f)
    b, meta = cache.get_tle(100, f, return_meta=True)
    assert a == b and f.calls == [100]
    assert meta["source"] == "cache"


def test_single_cache_expires(monkeypatch):
    f = Counter()
    cache.get_tle(100, f)
    monkeypatch.setattr(cache, "CACHE_TTL_SECONDS", 0)
    _, meta = cache.get_tle(100, f, return_meta=True)
    assert f.calls == [100, 100] and meta["source"] == "upstream"


def test_force_refresh_bypasses_cache():
    f = Counter()
    cache.get_tle(100, f)
    cache.get_tle(100, f, force_refresh=True)
    assert f.calls == [100, 100]


def test_serves_expired_copy_when_celestrak_is_down(monkeypatch):
    cache.get_tle(100, Counter())
    monkeypatch.setattr(cache, "CACHE_TTL_SECONDS", 0)
    down = Counter(fail={100: requests.ConnectionError("down")})
    tle, meta = cache.get_tle(100, down, return_meta=True)
    assert tle["name"] == "S100" and meta["source"] == "stale_cache"


def test_does_not_serve_expired_copy_that_is_too_old(monkeypatch):
    cache.get_tle(100, Counter())
    monkeypatch.setattr(cache, "CACHE_TTL_SECONDS", 0)
    monkeypatch.setattr(cache, "MAX_STALE_SERVE_SECONDS", 0)
    with pytest.raises(requests.ConnectionError):
        cache.get_tle(100, Counter(fail={100: requests.ConnectionError("down")}))


def test_outage_with_nothing_cached_still_raises():
    with pytest.raises(requests.ConnectionError):
        cache.get_tle(100, Counter(fail={100: requests.ConnectionError("down")}))


def test_not_found_is_never_masked_by_cache(monkeypatch):
    cache.get_tle(100, Counter())
    monkeypatch.setattr(cache, "CACHE_TTL_SECONDS", 0)
    with pytest.raises(engine.TLENotFound):
        cache.get_tle(100, Counter(fail={100: engine.TLENotFound("gone")}))


def test_batch_only_fetches_misses_and_isolates_errors():
    f = Counter(fail={3: engine.TLENotFound("no such object")})
    cache.get_tle(1, f)
    cache.get_tle(2, f)
    f.calls.clear()
    tles, errors, metas = cache.get_tles_by_ids([1, 2, 3, 4, 4], f)   # 4 listed twice
    assert sorted(f.calls) == [3, 4]                                 # 1 and 2 came from cache, 4 fetched once
    assert sorted(tles) == [1, 2, 4] and list(errors) == [3]
    assert metas[1]["source"] == "cache" and metas[4]["source"] == "upstream"
    # and the successful fetches were stored
    f.calls.clear()
    cache.get_tles_by_ids([1, 2, 4], f)
    assert f.calls == []


def test_group_cache_serves_expired_copy_when_celestrak_is_down(monkeypatch):
    full = lambda group, limit=None: [ISS_2024]
    cache.get_tles("g", full)
    monkeypatch.setattr(cache, "CACHE_TTL_SECONDS", 0)

    def down(group, limit=None):
        raise requests.ConnectionError("down")

    tles, meta = cache.get_tles("g", down, return_meta=True)
    assert tles == [ISS_2024] and meta["source"] == "stale_cache"


# ======================= endpoints use the cache =======================
def test_object_endpoints_share_one_upstream_request(client, monkeypatch):
    f = Counter()
    monkeypatch.setattr(engine, "fetch_tle", f)
    assert client.get("/objects/501").status_code == 200
    assert client.get("/objects/501").status_code == 200
    assert client.get("/trajectory/501?hours=0,1").status_code == 200
    assert client.get("/what-if", params={"norad_id": 501, "other_norad_id": 502, "altitude_delta_km": 1}).status_code == 200
    assert sorted(f.calls) == [501, 502]          # 501 once, 502 once - not 6 requests


def test_object_endpoint_reports_cache_source(client, monkeypatch):
    monkeypatch.setattr(engine, "fetch_tle", Counter())
    assert client.get("/objects/501").json()["cache"]["source"] == "upstream"
    assert client.get("/objects/501").json()["cache"]["source"] == "cache"


def test_cache_status_for_single_object(client, monkeypatch):
    monkeypatch.setattr(engine, "fetch_tle", Counter())
    assert client.get("/cache-status", params={"norad_id": 501}).json()["cached"] is False
    client.get("/objects/501")
    body = client.get("/cache-status", params={"norad_id": 501}).json()
    assert body["cached"] is True and body["is_fresh"] is True


def test_outage_serves_cached_object_with_warning(client, monkeypatch):
    f = Counter()
    monkeypatch.setattr(engine, "fetch_tle", f)
    client.get("/trajectory/501?hours=0")
    monkeypatch.setattr(cache, "CACHE_TTL_SECONDS", 0)
    f.fail[501] = requests.ConnectionError("down")
    r = client.get("/trajectory/501?hours=0")
    assert r.status_code == 200
    assert r.json()["cache"]["source"] == "stale_cache"
    assert any("unreachable" in w for w in r.json()["warnings"])


def test_watchlist_live_uses_cache(client, monkeypatch, tmp_path):
    monkeypatch.setattr(auth, "DB_PATH", tmp_path / "users.db")
    token = client.post("/auth/register", json={"name": "T", "email": "t@example.com", "password": "password123"}).json()["access_token"]
    h = {"Authorization": f"Bearer {token}"}
    for nid in (601, 602, 603):
        assert client.post("/watchlist", json={"norad_id": nid}, headers=h).status_code == 201
    f = Counter(fail={603: engine.TLENotFound("gone")})
    monkeypatch.setattr(engine, "fetch_tle", f)

    body = client.get("/watchlist?live=true", headers=h).json()
    by_id = {i["norad_id"]: i for i in body["items"]}
    assert sorted(f.calls) == [601, 602, 603]
    assert by_id[601]["altitude_km"] > 0 and by_id[601]["tle_status"] == "fresh"
    assert by_id[601]["data_source"] == "upstream"
    assert "live_error" in by_id[603] and "altitude_km" not in by_id[603]   # one bad satellite doesn't break the list

    f.calls.clear()
    body = client.get("/watchlist?live=true", headers=h).json()
    assert f.calls == [603]                                                 # only the failed one is retried
    assert {i["norad_id"]: i["data_source"] for i in body["items"] if "data_source" in i} == {601: "cache", 602: "cache"}


# ======================= TLE age / staleness =======================
@pytest.mark.parametrize("days,status", [(0.5, "fresh"), (6.9, "fresh"), (7.1, "stale"), (29.9, "stale"),
                                         (30.1, "unreliable"), (200, "unreliable")])
def test_tle_status_thresholds(days, status):
    info = engine.tle_age_info(with_epoch(ISS_2024, NOW - timedelta(days=days)), NOW)
    assert info["tle_status"] == status
    assert abs(info["tle_age_days"] - days) < 0.02
    assert ("tle_warning" in info) == (status != "fresh")


def test_tle_age_is_measured_to_the_propagation_time():
    tle = with_epoch(ISS_2024, NOW)
    assert engine.tle_age_info(tle, NOW)["tle_status"] == "fresh"
    assert engine.tle_age_info(tle, NOW + timedelta(days=10))["tle_status"] == "stale"


def test_propagate_carries_tle_age():
    p = engine.propagate(fresh_tle(days_old=10))
    assert p["tle_status"] == "stale" and 9.9 < p["tle_age_days"] < 10.1 and "tle_warning" in p


def test_propagate_error_names_the_cause_and_the_age():
    with pytest.raises(engine.PropagationError) as ei:       # 2024 ISS TLE at today's date: decayed
        engine.propagate(ISS_2024)
    assert ei.value.code == 6 and "decayed" in str(ei.value) and "days from requested time" in str(ei.value)
    assert isinstance(ei.value, RuntimeError)                # existing handlers (-> 422) still match


# ======================= nothing is dropped silently =======================
def test_propagate_many_reports_skipped_objects():
    garbage = {"name": "GARBAGE", "line1": "not a tle", "line2": "nope"}
    out = engine.propagate_many_with_stats([fresh_tle(1), ISS_2024, garbage, fresh_tle(2, days_old=12)])
    assert [o["norad_id"] for o in out["objects"]] == [1, 2]
    sk = out["skipped"]
    assert sk["count"] == 2 and sk["malformed"] == 1 and sk["sgp4_error"] == 1
    assert sk["by_error_code"] == {"6": 1}
    assert {e["name"] for e in sk["examples"]} == {"GARBAGE", "ISS (ZARYA)"}
    assert out["tle_staleness"]["fresh"] == 1 and out["tle_staleness"]["stale"] == 1
    assert out["tle_staleness"]["oldest_age_days"] > 11.9


def test_malformed_tle_is_reported_as_malformed_not_as_an_sgp4_failure():
    garbage = {"name": "GARBAGE", "line1": "x", "line2": "y"}
    with pytest.raises(engine.MalformedTLE):
        engine.propagate(garbage)
    out = engine.propagate_many_with_stats([fresh_tle(1), garbage])
    assert len(out["objects"]) == 1 and out["skipped"]["malformed"] == 1 and out["skipped"]["sgp4_error"] == 0


def test_objects_endpoint_reports_what_it_skipped(client, monkeypatch):
    garbage = {"name": "GARBAGE", "line1": "x", "line2": "y"}
    monkeypatch.setattr(engine, "fetch_many", lambda group, limit=None: [fresh_tle(1), ISS_2024, garbage, fresh_tle(2, days_old=45)])
    body = client.get("/objects").json()
    assert body["count"] == 2 and body["requested"] == 4          # `count` used to say 4 here
    assert body["skipped"]["count"] == 2
    assert body["tle_staleness"]["unreliable"] == 1
    assert any("skipped" in w for w in body["warnings"]) and any("unreliable" in w for w in body["warnings"])
    assert body["cache"]["source"] == "upstream"
    assert client.get("/objects").json()["cache"]["source"] == "cache"


def test_conjunctions_snapshot_reports_skipped(client, monkeypatch):
    monkeypatch.setattr(engine, "fetch_many", lambda group, limit=None: [fresh_tle(1), fresh_tle(2), ISS_2024])
    body = client.get("/conjunctions").json()
    assert body["objects_checked"] == 2 and body["objects_skipped"] == 1 and body["warnings"]


def test_trajectory_reports_skipped_points_and_age(client, monkeypatch):
    monkeypatch.setattr(engine, "fetch_tle", lambda _: fresh_tle(days_old=10))
    body = client.get("/trajectory/1?hours=0,1,72000").json()     # last point is ~8 years out: SGP4 fails
    assert body["count"] == 2 and body["requested_points"] == 3 and body["skipped_points"] == 1
    assert body["tle_status"] == "stale" and 9.9 < body["tle_age_days"] < 10.1
    assert all("tle_age_days" not in p for p in body["trajectory"])   # reported once, not per point
    assert any("could not be propagated" in w for w in body["warnings"])


def test_undecodable_single_object_is_422_and_explains_why(client, monkeypatch):
    monkeypatch.setattr(engine, "fetch_tle", lambda _: ISS_2024)
    r = client.get("/objects/25544")
    assert r.status_code == 422 and "decayed" in r.json()["detail"]


def test_what_if_reports_staleness(client, monkeypatch):
    monkeypatch.setattr(engine, "fetch_tle", lambda n: fresh_tle(n, days_old=10 if n == 1 else 1))
    body = client.get("/what-if", params={"norad_id": 1, "other_norad_id": 2, "altitude_delta_km": 1}).json()
    assert body["object_1"]["tle_status"] == "stale" and body["object_2"]["tle_status"] == "fresh"
    assert len(body["warnings"]) == 1


# ======================= forecast =======================
def test_forecast_reports_staleness(monkeypatch):
    import test_step2_window as t2
    monkeypatch.setattr(main, "_get_tles_meta", lambda group="stations", limit=None, force_refresh=False:
                        ([t2.ISS, t2.CROSSER, t2.FAR], {"source": "cache", "age_seconds": 0.0}))
    c = TestClient(main.app)
    params = {"start": "2024-08-22T04:00:00Z", "hours": 3}

    body = c.get("/conjunctions/forecast", params=params).json()
    assert body["tle_staleness"]["fresh"] == 3 and body["warnings"] == []
    ev = body["conjunctions"][0]
    assert ev["tle_status"] == "fresh" and ev["object_1"]["tle_age_days"] < 1

    # shrink the thresholds so the (~0.007 day old) TLEs count as unreliable
    monkeypatch.setattr(engine, "STALE_TLE_DAYS", 0.001)
    monkeypatch.setattr(engine, "UNRELIABLE_TLE_DAYS", 0.005)
    body = c.get("/conjunctions/forecast", params=params).json()
    assert body["tle_staleness"]["unreliable"] == 3
    assert body["conjunctions"][0]["tle_status"] == "unreliable"
    assert any("may be spurious" in w for w in body["warnings"])


@pytest.mark.parametrize("path", ["/objects", "/conjunctions", "/conjunctions/forecast"])
@pytest.mark.parametrize("limit", [0, -5])
def test_non_positive_limit_is_400(client, path, limit):
    assert client.get(path, params={"limit": limit}).status_code == 400
