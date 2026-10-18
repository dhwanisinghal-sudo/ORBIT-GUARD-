"""Regression tests for the step-1 bug fixes. CelesTrak is mocked, so these run offline."""
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
import requests
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cache
import orbit_engine as engine
import main

ISS = {
    "name": "ISS (ZARYA)",
    "line1": "1 25544U 98067A   24235.16000531  .00028314  00000+0  49252-3 0  9994",
    "line2": "2 25544  51.6402 348.4828 0004893 236.4095 123.6428 15.50549723468780",
}


@pytest.fixture(autouse=True)
def temp_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(cache, "DB_PATH", tmp_path / "cache.db")


@pytest.fixture
def client():
    return TestClient(main.app)


# ---- bug: cache ignored / truncated by `limit` ----
def test_cache_stores_full_group_and_limit_applies_on_read():
    calls = []

    def fake_fetch(group, limit=None):
        calls.append(limit)
        return [{"name": f"S{i}", "line1": "", "line2": ""} for i in range(50)]

    assert len(cache.get_tles("g", fake_fetch, limit=10)) == 10
    assert len(cache.get_tles("g", fake_fetch, limit=40)) == 40  # used to return 10
    assert len(cache.get_tles("g", fake_fetch)) == 50            # no limit -> full list
    assert len(cache.get_tles("g", fake_fetch, limit=5)) == 5    # limit honoured on a hit
    assert calls == [None]  # fetched once, and always the full group


# ---- bug: microseconds dropped ----
def test_propagate_uses_microseconds():
    t0 = datetime(2024, 8, 22, 12, 0, 0, 0, tzinfo=timezone.utc)
    t1 = datetime(2024, 8, 22, 12, 0, 0, 500_000, tzinfo=timezone.utc)
    a, b = engine.propagate(ISS, t0), engine.propagate(ISS, t1)
    pa, pb = a["position_km"], b["position_km"]
    moved = sum((pa[k] - pb[k]) ** 2 for k in "xyz") ** 0.5
    assert 3.0 < moved < 4.5  # ~7.6 km/s * 0.5 s; was exactly 0 before the fix


NEAR_EPOCH = datetime(2024, 8, 22, 12, 0, 0, tzinfo=timezone.utc)


def test_norad_id_is_int():
    assert engine.propagate(ISS, NEAR_EPOCH)["norad_id"] == 25544


# ---- bug: everything was a 502 ----
def test_unknown_norad_is_404(client, monkeypatch):
    def nf(_):
        raise engine.TLENotFound("No TLE found for NORAD ID 1")
    monkeypatch.setattr(engine, "fetch_tle", nf)
    assert client.get("/objects/1").status_code == 404


def test_upstream_failure_is_502(client, monkeypatch):
    def down(_):
        raise requests.ConnectionError("boom")
    monkeypatch.setattr(engine, "fetch_tle", down)
    assert client.get("/objects/25544").status_code == 502


def test_bad_hours_is_400(client):
    assert client.get("/trajectory/25544?hours=a,b").status_code == 400


def test_bad_method_and_threshold_are_400(client):
    assert client.get("/conjunctions?method=bogus").status_code == 400
    assert client.get("/conjunctions?threshold_km=0").status_code == 400


def test_happy_path_still_works(client, monkeypatch):
    # The fixture TLE is from 2024; SGP4 rejects it at today's date, so pin time near its epoch.
    real_propagate = engine.propagate
    monkeypatch.setattr(engine, "propagate", lambda tle, when=None: real_propagate(tle, NEAR_EPOCH))
    monkeypatch.setattr(engine, "fetch_tle", lambda _: ISS)
    r = client.get("/objects/25544")
    assert r.status_code == 200 and r.json()["norad_id"] == 25544
    r = client.get("/trajectory/25544?hours=0,1")
    assert r.status_code == 200 and r.json()["count"] == 2


# ---- bug: metrics crash when json missing ----
def test_metrics_regenerated_if_missing(tmp_path, monkeypatch):
    import ml_risk
    monkeypatch.setattr(ml_risk, "MODEL_DIR", tmp_path)
    monkeypatch.setattr(ml_risk, "MODEL_PATH", tmp_path / "m.joblib")
    monkeypatch.setattr(ml_risk, "METRICS_PATH", tmp_path / "m.json")
    monkeypatch.setattr(ml_risk, "_model", None)
    ml_risk.train()
    (tmp_path / "m.json").unlink()
    monkeypatch.setattr(ml_risk, "_model", None)
    assert "accuracy" in ml_risk.get_metrics()
