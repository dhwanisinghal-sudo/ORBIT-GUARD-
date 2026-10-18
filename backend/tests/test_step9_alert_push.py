"""Step 9: precomputed alerts + WebSocket push. CelesTrak is mocked (offline), same catalog as step 6."""
import faulthandler
import json
import sys
import time
from pathlib import Path

import jwt
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import alert_hub
import alert_service
import auth
import config
import main
import ml_risk
import orbit_engine as engine
from alert_service import Params
from test_step2_window import START
from test_step6_watchlist_alerts import CROSSER_ID, ISS_ID, START_Q, catalog, _norad

PARAMS = Params(hours=3.0, include_coorbiting=True, start_dt=START)   # fixed window: the TLEs are from 2024


@pytest.fixture(autouse=True)
def _hang_guard():
    """A broken push would block receive_json forever; die with a traceback instead."""
    faulthandler.dump_traceback_later(int(__import__("os").environ.get("HANG_S","90")), exit=True)
    yield
    faulthandler.cancel_dump_traceback_later()


# ============================ diff_snapshots ============================
def conj(a, b, tca, risk="MEDIUM", miss=2.0):
    return {"object_1": {"norad_id": a}, "object_2": {"norad_id": b}, "tca_utc": tca,
            "miss_distance_km": miss, "risk_level": risk}


def snap(conjs, computed="2026-10-17T12:00:00+00:00", sats=None, watchlist_count=1):
    return {"conjunctions": conjs, "computed_at_utc": computed, "watchlist_count": watchlist_count,
            "satellites": sats or [{"norad_id": 1, "status": "ok"}]}


def test_diff_without_previous_is_none():
    assert alert_hub.diff_snapshots(None, snap([])) is None


def test_diff_identical_feed_is_a_quiet_ping():
    prev = snap([conj(1, 2, "2026-10-17T15:00:00+00:00")])
    d = alert_hub.diff_snapshots(prev, snap([conj(2, 1, "2026-10-17T15:00:00+00:00")]))   # pair order swapped
    assert d["new"] == d["cleared"] == d["expired"] == d["escalated"] == d["updated"] == []
    assert d["notable"] is False and d["changed"] is False            # -> a ping, no snapshot


def test_diff_drifted_tca_is_the_same_event_updated_not_new_plus_cleared():
    prev = snap([conj(1, 2, "2026-10-17T15:00:00+00:00")])
    new = snap([conj(2, 1, "2026-10-17T15:04:00+00:00")])             # new TLE moved the TCA by 4 min
    d = alert_hub.diff_snapshots(prev, new)
    assert d["new"] == d["cleared"] == d["expired"] == [] and len(d["updated"]) == 1
    assert d["notable"] is False and d["changed"] is True


def test_diff_new_escalated_cleared_expired():
    prev = snap([conj(1, 2, "2026-10-17T15:00:00+00:00", "LOW"),
                 conj(1, 3, "2026-10-17T16:00:00+00:00"),            # future, then gone -> cleared
                 conj(1, 4, "2026-10-17T11:00:00+00:00")])           # passed before the new cycle -> expired
    new = snap([conj(1, 2, "2026-10-17T15:00:00+00:00", "HIGH"),
                conj(1, 5, "2026-10-17T17:00:00+00:00")])
    d = alert_hub.diff_snapshots(prev, new)
    assert [c["object_2"]["norad_id"] for c in d["new"]] == [5]
    assert d["escalated"][0]["previous_risk"] == "LOW" and d["escalated"][0]["risk_level"] == "HIGH"
    assert [c["norad_ids"] for c in d["cleared"]] == [[1, 3]]
    assert [c["norad_ids"] for c in d["expired"]] == [[1, 4]]
    assert d["notable"] is True


def test_diff_only_expiry_is_not_notable_but_is_a_change():
    prev = snap([conj(1, 4, "2026-10-17T11:00:00+00:00")])
    d = alert_hub.diff_snapshots(prev, snap([]))
    assert len(d["expired"]) == 1 and d["notable"] is False
    assert d["changed"] is True            # the client must drop the passed event


def test_diff_moved_miss_distance_is_an_update_not_an_alert():
    prev = snap([conj(1, 2, "2026-10-17T15:00:00+00:00", miss=4.8)])
    new = snap([conj(1, 2, "2026-10-17T15:00:00+00:00", miss=3.9)])
    d = alert_hub.diff_snapshots(prev, new)
    assert len(d["updated"]) == 1 and d["notable"] is False and d["changed"] is True
    tiny = alert_hub.diff_snapshots(prev, snap([conj(1, 2, "2026-10-17T15:00:00+00:00", miss=4.81)]))
    assert tiny["changed"] is False        # numerical noise is not a change


def test_diff_watchlist_size_change_counts_as_changed():
    d = alert_hub.diff_snapshots(snap([], watchlist_count=1), snap([], watchlist_count=2))
    assert d["changed"] is True and d["notable"] is False


def test_diff_same_pair_twice_matches_one_to_one():
    prev = snap([conj(1, 2, "2026-10-17T13:00:00+00:00")])
    new = snap([conj(1, 2, "2026-10-17T13:01:00+00:00"), conj(1, 2, "2026-10-17T13:10:00+00:00")])
    d = alert_hub.diff_snapshots(prev, new)
    assert len(d["new"]) == 1                    # the second pass of the same pair is a new event


def test_diff_reports_status_change():
    prev = snap([], sats=[{"norad_id": 1, "status": "ok"}])
    new = snap([], sats=[{"norad_id": 1, "status": "unavailable"}])
    d = alert_hub.diff_snapshots(prev, new)
    assert d["status_changed"] == [{"norad_id": 1, "from": "ok", "to": "unavailable"}] and d["notable"]


# ============================ settings ============================
def test_alert_settings_defaults_and_validation():
    d = config.alert_job_settings({})
    assert d == {"enabled": True, "interval_seconds": 300.0, "group": "active", "hours": 24.0,
                 "threshold_km": 5.0}
    assert config.alert_job_settings({"ORBITGUARD_ALERT_JOB": "0"})["enabled"] is False
    assert config.alert_job_settings({"ORBITGUARD_ALERT_INTERVAL": "60"})["interval_seconds"] == 60.0
    for bad in ({"ORBITGUARD_ALERT_INTERVAL": "5"}, {"ORBITGUARD_ALERT_INTERVAL": "abc"},
                {"ORBITGUARD_ALERT_HOURS": "0"}, {"ORBITGUARD_ALERT_THRESHOLD_KM": "-1"}):
        with pytest.raises(RuntimeError):
            config.alert_job_settings(bad)


# ============================ live hub + WebSocket ============================
@pytest.fixture
def env(monkeypatch):
    tles = {_norad(t): t for t in catalog()}
    calls = {"screen": 0}
    monkeypatch.setattr(engine, "fetch_tle", lambda nid: tles[nid] if nid in tles
                        else (_ for _ in ()).throw(engine.TLENotFound(f"No TLE found for NORAD ID {nid}")))
    monkeypatch.setattr(engine, "fetch_many", lambda group="stations", limit=None: list(tles.values()))
    monkeypatch.setattr(ml_risk, "warm_up", lambda: None)

    real_screen = alert_service.screen

    def counting_screen(ids, p):
        calls["screen"] += 1
        return real_screen(ids, p)
    monkeypatch.setattr(alert_service, "screen", counting_screen)

    hub = alert_hub.AlertHub(PARAMS, interval_seconds=3600, idle_ttl_seconds=900,
                             min_gap_seconds=0.0, debounce_seconds=0.05)
    monkeypatch.setattr(alert_hub, "hub", hub)
    with TestClient(main.app) as client:
        def user(email="a@example.com"):
            body = client.post("/auth/register", json={"name": "A", "email": email,
                                                       "password": "password123"}).json()
            return {"Authorization": f"Bearer {body['access_token']}"}, body["access_token"], body["user"]["id"]

        def watch(h, *ids):
            for i in ids:
                assert client.post("/watchlist", json={"norad_id": i}, headers=h).status_code == 201

        yield client, hub, user, watch, calls


def connect(client, token):
    """Open /ws/alerts and authenticate. Always finish with close_ws(): TestClient only cleans up
    its portal when the session's __exit__ runs (skipping it hangs the fixture teardown)."""
    ws = client.websocket_connect("/ws/alerts").__enter__()
    ws.send_text(json.dumps({"type": "auth", "token": token}))
    return ws


def close_ws(ws):
    try:
        ws.__exit__(None, None, None)
    except Exception:
        pass                      # the server may already have closed it


def recv(ws, *types, limit=12):
    """Next message whose type is in `types` (others, e.g. computing, are skipped)."""
    for _ in range(limit):
        m = ws.receive_json()
        if m["type"] in types:
            return m
        if m["type"] == "error":
            raise AssertionError(m)
    raise AssertionError(f"no {types} message")


def pairs(snapshot):
    return {frozenset((c["object_1"]["norad_id"], c["object_2"]["norad_id"])) for c in snapshot["conjunctions"]}


def test_connect_receives_hello_then_precomputed_snapshot(env):
    client, hub, user, watch, _ = env
    h, tok, _ = user()
    watch(h, ISS_ID)
    ws = connect(client, tok)
    try:
        hello = recv(ws, "hello")
        assert hello["refresh_interval_seconds"] == 3600 and hello["group"] == "active"
        msg = recv(ws, "snapshot")
        assert frozenset((ISS_ID, CROSSER_ID)) in pairs(msg["snapshot"])
        assert msg["snapshot"]["computed_at_utc"]
    finally:
        close_ws(ws)


def test_snapshot_matches_the_on_demand_endpoint(env):
    client, hub, user, watch, _ = env
    h, tok, _ = user()
    watch(h, ISS_ID)
    ws = connect(client, tok)
    try:
        pushed = recv(ws, "snapshot")["snapshot"]
    finally:
        close_ws(ws)
    direct = client.get(f"/watchlist/alerts?start={START_Q}&hours=3&include_coorbiting=true", headers=h).json()
    key = lambda c: (c["object_1"]["norad_id"], c["object_2"]["norad_id"], c["tca_utc"], c["miss_distance_km"])
    assert sorted(map(key, pushed["conjunctions"])) == sorted(map(key, direct["conjunctions"]))
    assert pushed["satellites"] == direct["satellites"]


def test_second_connection_gets_the_snapshot_without_recomputing(env):
    client, hub, user, watch, calls = env
    h, tok, _ = user()
    watch(h, ISS_ID)
    ws1 = connect(client, tok)
    try:
        recv(ws1, "snapshot")
        before = calls["screen"]
        ws2 = connect(client, tok)
        try:
            first = [ws2.receive_json()["type"] for _ in range(2)]
            assert first == ["hello", "snapshot"]            # no "computing" detour
            assert calls["screen"] == before
        finally:
            close_ws(ws2)
    finally:
        close_ws(ws1)


def test_watchlist_change_pushes_new_alert_then_cleared(env):
    client, hub, user, watch, _ = env
    h, tok, _ = user()
    watch(h, ISS_ID)
    ws = connect(client, tok)
    try:
        first = recv(ws, "snapshot")["snapshot"]
        assert frozenset((91001, 91002)) not in pairs(first)
        watch(h, 91001)                                       # a close pair appears for this user
        up = recv(ws, "update")
        assert frozenset((91001, 91002)) in pairs(up["snapshot"])
        assert any({c["object_1"]["norad_id"], c["object_2"]["norad_id"]} == {91001, 91002}
                   for c in up["changes"]["new"])
        assert client.delete("/watchlist/91001", headers=h).status_code == 200
        up = recv(ws, "update")
        assert frozenset((91001, 91002)) not in pairs(up["snapshot"])
        assert [91001, 91002] in [c["norad_ids"] for c in up["changes"]["cleared"] + up["changes"]["expired"]]
    finally:
        close_ws(ws)


def test_users_only_see_their_own_satellites(env):
    client, hub, user, watch, _ = env
    ha, ta, _ = user("a@example.com")
    hb, tb, _ = user("b@example.com")
    watch(ha, ISS_ID)
    watch(hb, 91001)
    wa, wb = connect(client, ta), connect(client, tb)
    try:
        sa, sb = recv(wa, "snapshot")["snapshot"], recv(wb, "snapshot")["snapshot"]
        assert frozenset((ISS_ID, CROSSER_ID)) in pairs(sa) and frozenset((91001, 91002)) not in pairs(sa)
        assert frozenset((91001, 91002)) in pairs(sb) and frozenset((ISS_ID, CROSSER_ID)) not in pairs(sb)
    finally:
        close_ws(wa)
        close_ws(wb)


def test_one_screening_pass_serves_every_user(env):
    client, hub, user, watch, calls = env
    ha, _, ida = user("a@example.com")
    hb, _, idb = user("b@example.com")
    watch(ha, ISS_ID)
    watch(hb, 91001)
    calls["screen"] = 0
    snaps = hub._compute([ida, idb])
    assert calls["screen"] == 1
    assert pairs(snaps[ida]) != pairs(snaps[idb])


def test_unchanged_refresh_sends_a_quiet_ping(env):
    client, hub, user, watch, _ = env
    h, tok, _ = user()
    watch(h, ISS_ID)
    ws = connect(client, tok)
    try:
        first = recv(ws, "snapshot")["snapshot"]
        ws.send_text(json.dumps({"type": "refresh"}))
        ping = recv(ws, "ping", "update")
        assert ping["type"] == "ping" and ping["computed_at_utc"] > first["computed_at_utc"]
    finally:
        close_ws(ws)


def test_refresh_is_rate_limited(env):
    client, hub, user, watch, _ = env
    h, tok, _ = user()
    ws = connect(client, tok)
    try:
        recv(ws, "hello")
        for _ in range(3):
            ws.send_text(json.dumps({"type": "refresh"}))
        got = []
        for _ in range(12):
            m = ws.receive_json()
            got.append(m)
            if m["type"] == "error":
                break
        assert got[-1]["type"] == "error" and got[-1]["code"] == "rate_limited"
    finally:
        close_ws(ws)


def test_failed_cycle_reports_error_and_job_recovers(env, monkeypatch):
    client, hub, user, watch, _ = env
    h, tok, _ = user()
    watch(h, ISS_ID)
    real = alert_service.screen
    state = {"fail": True}

    def flaky(ids, p):
        if state["fail"]:
            raise RuntimeError("CelesTrak exploded")
        return real(ids, p)
    monkeypatch.setattr(alert_service, "screen", flaky)
    ws = connect(client, tok)
    try:
        recv(ws, "hello")
        err = None
        for _ in range(6):
            m = ws.receive_json()
            if m["type"] == "error":
                err = m
                break
        assert err and err["code"] == "compute_failed" and "exploded" in err["detail"]
        state["fail"] = False
        ws.send_text(json.dumps({"type": "refresh"}))
        assert frozenset((ISS_ID, CROSSER_ID)) in pairs(recv(ws, "snapshot", "update")["snapshot"])
    finally:
        close_ws(ws)


# ---------- auth and limits ----------
def expect_close(ws, code):
    with pytest.raises(WebSocketDisconnect) as e:
        for _ in range(5):
            ws.receive_json()
    assert e.value.code == code


@pytest.mark.parametrize("first", ['{"type":"nope"}', "not json", '{"type":"auth"}',
                                   '{"type":"auth","token":"garbage"}', "[1,2]"])
def test_bad_first_message_or_token_is_rejected(env, first):
    client = env[0]
    with client.websocket_connect("/ws/alerts") as ws:
        ws.send_text(first)
        expect_close(ws, 4401)


def test_no_auth_message_times_out(env, monkeypatch):
    monkeypatch.setattr(alert_hub, "AUTH_TIMEOUT_S", 0.3)
    with env[0].websocket_connect("/ws/alerts") as ws:
        expect_close(ws, 4401)


def test_token_of_deleted_user_is_rejected(env):
    client, hub, user, watch, _ = env
    _, tok, uid = user()
    conn = auth._get_conn()
    conn.execute("DELETE FROM users WHERE id = ?", (uid,))
    conn.commit()
    conn.close()
    with client.websocket_connect("/ws/alerts") as ws:
        ws.send_text(json.dumps({"type": "auth", "token": tok}))
        expect_close(ws, 4401)


def test_foreign_origin_is_refused(env):
    client = env[0]
    with pytest.raises(WebSocketDisconnect) as e:
        with client.websocket_connect("/ws/alerts", headers={"origin": "https://evil.example"}):
            pass
    assert e.value.code == 4403
    with client.websocket_connect("/ws/alerts", headers={"origin": config.CORS_ORIGINS[0]}) as ws:
        assert ws is not None                       # the handshake was accepted


def test_connection_closes_when_token_expires(env):
    client, hub, user, watch, _ = env
    _, _, uid = user()
    tok = jwt.encode({"sub": str(uid), "exp": int(time.time()) + 1}, auth.SECRET_KEY, algorithm=auth.ALGORITHM)
    ws = connect(client, tok)
    try:
        saw_expired = False
        with pytest.raises(WebSocketDisconnect) as e:
            for _ in range(10):
                m = ws.receive_json()
                saw_expired |= m.get("code") == "token_expired"
        assert saw_expired and e.value.code == 4401
    finally:
        close_ws(ws)


def test_per_user_connection_limit(env, monkeypatch):
    monkeypatch.setattr(alert_hub, "MAX_CONNECTIONS_PER_USER", 2)
    client, hub, user, watch, _ = env
    _, tok, _ = user()
    a, b = connect(client, tok), connect(client, tok)
    try:
        recv(a, "hello"), recv(b, "hello")
        c = connect(client, tok)
        try:
            expect_close(c, 4429)
        finally:
            close_ws(c)
    finally:
        close_ws(a)
        close_ws(b)


def test_job_disabled_means_ws_unavailable_and_rest_503(monkeypatch):
    hub = alert_hub.AlertHub(PARAMS)                           # never started
    monkeypatch.setattr(alert_hub, "hub", hub)
    client = TestClient(main.app)                              # no lifespan -> hub stays off
    tok = client.post("/auth/register", json={"name": "A", "email": "z@example.com",
                                              "password": "password123"}).json()["access_token"]
    with pytest.raises(WebSocketDisconnect) as e:
        with client.websocket_connect("/ws/alerts"):
            pass
    assert e.value.code == 1013
    r = client.get("/watchlist/alerts/latest", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 503
    # and the watchlist endpoints still work with the job off
    assert client.post("/watchlist", json={"norad_id": 25544},
                       headers={"Authorization": f"Bearer {tok}"}).status_code == 201


# ---------- REST: /watchlist/alerts/latest ----------
def test_latest_requires_login(env):
    assert env[0].get("/watchlist/alerts/latest").status_code == 401


def test_latest_is_202_then_instant_200(env):
    client, hub, user, watch, calls = env
    h, tok, _ = user()
    watch(h, ISS_ID)
    r = client.get("/watchlist/alerts/latest", headers=h)
    assert r.status_code == 202 and r.json()["status"] == "computing" and r.headers["retry-after"]
    for _ in range(60):                                       # the job computes in the background
        time.sleep(0.25)
        r = client.get("/watchlist/alerts/latest", headers=h)
        if r.status_code == 200:
            break
    assert r.status_code == 200
    body = r.json()
    assert frozenset((ISS_ID, CROSSER_ID)) in pairs(body) and body["age_seconds"] >= 0
    n = calls["screen"]
    assert client.get("/watchlist/alerts/latest", headers=h).status_code == 200
    assert calls["screen"] == n                               # served from the snapshot, nothing screened


def test_latest_empty_watchlist_is_an_empty_feed(env):
    client, hub, user, watch, _ = env
    h, _, _ = user()
    for _ in range(60):
        r = client.get("/watchlist/alerts/latest", headers=h)
        if r.status_code == 200:
            break
        time.sleep(0.25)
    assert r.status_code == 200 and r.json()["count"] == 0 and r.json()["watchlist_count"] == 0


def test_stale_snapshot_is_dropped_when_watchlist_changes_while_idle(env):
    client, hub, user, watch, _ = env
    h, tok, uid = user()
    watch(h, ISS_ID)
    ws = connect(client, tok)
    recv(ws, "snapshot")
    close_ws(ws)
    time.sleep(0.2)
    assert hub.latest(uid) is not None
    hub._last_seen[uid] -= 10_000                              # long idle: not interested any more
    watch(h, 91001)
    time.sleep(0.3)
    assert hub.latest(uid) is None                              # never serve a feed for an old watchlist
