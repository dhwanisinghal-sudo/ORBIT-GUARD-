"""Step 5: snapshot /conjunctions scales to the whole catalog (kdtree default, naive guarded).
CelesTrak is mocked, so these run offline."""
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import conjunction as conj
import main
import orbit_engine as engine
from tle_factory import make_tle, random_leo_tles

# make_tle() reuses the ISS epoch (2024-08-22), so propagate at that time to keep every object valid
EPOCH = datetime(2024, 8, 22, 12, 0, tzinfo=timezone.utc)


def with_planted_pairs(n_random: int, n_pairs: int):
    """Random satellites plus pairs that are genuinely 0-5 km apart (same orbit, tiny phase offset)."""
    tles = random_leo_tles(n_random)
    for k in range(n_pairs):
        inc, raan, ma = 30 + 3 * k, 20 + 11 * k, 40 + 17 * k
        # 0.0003 deg of mean anomaly ~ 0.002 deg of orbit ~ 0.25 km along-track; grow with k
        tles.append(make_tle(50000 + 2 * k, f"A{k}", inc, raan, ma))
        tles.append(make_tle(50001 + 2 * k, f"B{k}", inc, raan, ma + 0.0004 * (k + 1)))
    return tles


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(engine, "propagate_many_with_stats",
                        lambda tles, when=None, _f=engine.propagate_many_with_stats: _f(tles, EPOCH))
    return TestClient(main.app)


def _fake_group(monkeypatch, tles):
    monkeypatch.setattr(engine, "fetch_many", lambda group="stations", limit=None: tles)


def _key(c):
    return (c["object_1"]["norad_id"], c["object_2"]["norad_id"], c["distance_km"])


def test_kdtree_matches_naive_on_planted_close_pairs():
    objs = engine.propagate_many(with_planted_pairs(300, 8), EPOCH)
    naive = conj.find_conjunctions_naive(objs, 5.0)
    kd = conj.find_conjunctions_kdtree(objs, 5.0)
    assert len(naive) >= 8, "test data must actually contain close pairs, or it proves nothing"
    assert sorted(map(_key, naive)) == sorted(map(_key, kd))


def test_default_method_is_kdtree_and_reports_it(client, monkeypatch):
    _fake_group(monkeypatch, with_planted_pairs(50, 3))
    body = client.get("/conjunctions").json()
    assert body["method"] == "kdtree"
    assert body["count"] >= 3


def test_naive_still_available_for_small_groups_with_same_answer(client, monkeypatch):
    _fake_group(monkeypatch, with_planted_pairs(50, 3))
    kd = client.get("/conjunctions?method=kdtree").json()
    nv = client.get("/conjunctions?method=naive").json()
    assert nv["method"] == "naive"
    assert sorted(map(_key, kd["conjunctions"])) == sorted(map(_key, nv["conjunctions"]))


def test_naive_refused_on_large_groups_with_400_not_500(client, monkeypatch):
    _fake_group(monkeypatch, random_leo_tles(main.MAX_NAIVE_OBJECTS + 10))
    r = client.get("/conjunctions?method=naive")
    assert r.status_code == 400
    assert "kdtree" in r.json()["detail"]


def test_invalid_method_still_400(client, monkeypatch):
    _fake_group(monkeypatch, random_leo_tles(5))
    assert client.get("/conjunctions?method=bogus").status_code == 400


def test_whole_catalog_snapshot_is_fast(client, monkeypatch):
    """7,000 objects (about the size of CelesTrak's active group) end to end, through the API."""
    _fake_group(monkeypatch, with_planted_pairs(7000, 5))
    t = time.perf_counter()
    r = client.get("/conjunctions?group=active")
    elapsed = time.perf_counter() - t
    assert r.status_code == 200
    body = r.json()
    assert body["objects_checked"] >= 7000
    assert body["count"] >= 5
    assert elapsed < 5.0, f"took {elapsed:.1f}s"


def test_http_exceptions_inside_handlers_keep_their_status():
    from fastapi import HTTPException
    exc = HTTPException(status_code=418, detail="x")
    assert main._http_error(exc, "ctx") is exc
