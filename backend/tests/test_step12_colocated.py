"""Step 12: docked / co-located pairs are flagged in /conjunctions and get no collision risk. Offline."""
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import main
import orbit_engine as engine
from tle_factory import make_tle

EPOCH = datetime(2024, 8, 22, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(engine, "propagate_many_with_stats",
                        lambda tles, when=None, _f=engine.propagate_many_with_stats: _f(tles, EPOCH))
    return TestClient(main.app)


def _group(monkeypatch):
    tles = [
        make_tle(60001, "STATION", 41.47, 100.0, 128.0),
        make_tle(60002, "DOCKED", 41.47, 100.0, 128.0),                 # identical state -> docked
        make_tle(60003, "NEAR_A", 70.0, 200.0, 40.0),
        make_tle(60004, "NEAR_B", 70.0, 200.0, 40.0004),                 # ~0.2 km away, moving apart
    ]
    monkeypatch.setattr(engine, "fetch_many", lambda group="stations", limit=None: tles)


def test_conjunctions_endpoint_flags_docked_pair(client, monkeypatch):
    _group(monkeypatch)
    items = client.get("/conjunctions?threshold_km=5").json()["conjunctions"]
    docked = [c for c in items if {c["object_1"]["norad_id"], c["object_2"]["norad_id"]} == {60001, 60002}]
    assert len(docked) == 1
    assert docked[0]["co_located"] is True
    assert docked[0]["risk_level"] == "DOCKED"
    assert all("co_located" in c for c in items)


def test_ml_scoring_skips_docked_pair(client, monkeypatch):
    _group(monkeypatch)
    items = client.get("/conjunctions?threshold_km=5&ml=true").json()["conjunctions"]
    docked = next(c for c in items if c["co_located"])
    assert docked["ml_risk_score"] is None and docked["risk_level"] == "DOCKED"
    for c in items:
        if not c["co_located"]:
            assert c["ml_risk_score"] is not None


def test_what_if_reports_docked_risk(client, monkeypatch):
    _group(monkeypatch)
    monkeypatch.setattr(main, "_get_tles_by_ids",
                        lambda ids: ({60001: make_tle(60001, "STATION", 41.47, 100.0, 128.0),
                                      60002: make_tle(60002, "DOCKED", 41.47, 100.0, 128.0)},
                                     {60001: {}, 60002: {}}))
    body = client.get("/what-if", params={"norad_id": 60001, "other_norad_id": 60002,
                                           "dv_along_ms": 10, "start": EPOCH.isoformat()}).json()
    assert body["scenario"]["co_located_at_start"] is True
    assert body["before"]["risk_level"] == "DOCKED"
    assert body["post_burn_separation_km"]["after"]["max"] > 100
