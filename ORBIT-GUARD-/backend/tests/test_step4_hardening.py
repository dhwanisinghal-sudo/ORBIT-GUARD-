"""Step 4: startup secret check, CORS, rate limiting, foreign keys, ML warm-up, data dir."""
import os
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

import auth
import cache
import config
import db
import main
import ml_risk
import watchlist
from ratelimit import SlidingWindowLimiter

GOOD_SECRET = "a" * 40


@pytest.fixture
def client():
    return TestClient(main.app)


def register(client, email="a@example.com", headers=None):
    return client.post("/auth/register", json={"name": "A", "email": email, "password": "password123"}, headers=headers or {})


def login(client, email="a@example.com", password="password123", headers=None):
    return client.post("/auth/login", json={"email": email, "password": password}, headers=headers or {})


# ======================= secret =======================
def test_missing_secret_is_refused():
    with pytest.raises(RuntimeError, match="ORBITGUARD_SECRET is not set"):
        config.load_secret({})


@pytest.mark.parametrize("secret,msg", [("dev-only-change-me", "well-known"), ("short", "too short")])
def test_weak_secret_is_refused(secret, msg):
    with pytest.raises(RuntimeError, match=msg):
        config.load_secret({"ORBITGUARD_SECRET": secret})


def test_good_secret_is_accepted():
    assert config.load_secret({"ORBITGUARD_SECRET": f"  {GOOD_SECRET}  "}) == GOOD_SECRET


def test_dev_flag_allows_fallback_with_a_warning(caplog):
    with caplog.at_level("WARNING", logger="orbitguard.config"):
        assert config.load_secret({"ORBITGUARD_DEV": "1"}) == config.DEV_DEFAULT_SECRET
    assert "INSECURE" in caplog.text


def _run_import(env_extra, code="import auth"):
    env = {k: v for k, v in os.environ.items() if not k.startswith("ORBITGUARD_")}
    env.update(env_extra)
    return subprocess.run([sys.executable, "-c", code], cwd=BACKEND, env=env, capture_output=True, text=True)


def test_app_really_fails_to_start_without_a_secret():
    r = _run_import({}, "import main")
    assert r.returncode != 0 and "ORBITGUARD_SECRET is not set" in r.stderr


def test_app_starts_with_a_secret_and_with_the_dev_flag(tmp_path):
    data = {"ORBITGUARD_DATA_DIR": str(tmp_path)}
    assert _run_import({"ORBITGUARD_SECRET": GOOD_SECRET, **data}, "import main").returncode == 0
    assert _run_import({"ORBITGUARD_DEV": "1", **data}, "import main").returncode == 0


def test_tokens_are_signed_with_the_configured_secret():
    import jwt
    token = auth.create_token(1, "a@example.com")
    assert jwt.decode(token, auth.SECRET_KEY, algorithms=["HS256"])["sub"] == "1"
    assert auth.SECRET_KEY != config.DEV_DEFAULT_SECRET


# ======================= CORS =======================
def test_cors_defaults_to_the_vite_dev_server():
    assert config.parse_cors_origins({}) == ["http://localhost:5173", "http://127.0.0.1:5173"]


def test_cors_origins_are_parsed_and_validated():
    got = config.parse_cors_origins({"ORBITGUARD_CORS_ORIGINS": "https://app.example.com/, http://localhost:3000 ,"})
    assert got == ["https://app.example.com", "http://localhost:3000"]
    for bad in ("app.example.com", "https://app.example.com/path", "ftp://x.com", " , "):
        with pytest.raises(RuntimeError):
            config.parse_cors_origins({"ORBITGUARD_CORS_ORIGINS": bad})


def test_preflight_allows_the_frontend_and_nobody_else(client):
    def preflight(origin):
        return client.options("/objects", headers={"Origin": origin, "Access-Control-Request-Method": "GET"})

    ok = preflight("http://localhost:5173")
    assert ok.status_code == 200 and ok.headers["access-control-allow-origin"] == "http://localhost:5173"
    evil = preflight("https://evil.example")
    assert "access-control-allow-origin" not in evil.headers


def test_simple_request_from_other_origin_gets_no_cors_header(client):
    r = client.get("/", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in r.headers


def test_cors_does_not_allow_arbitrary_methods(client):
    r = client.options("/objects", headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "PUT"})
    assert r.status_code == 400


# ======================= rate limiter unit =======================
def test_limiter_blocks_after_max_and_recovers(monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(time, "monotonic", lambda: now[0])
    lim = SlidingWindowLimiter(max_events=3, window_seconds=60)
    assert [lim.hit("k") for _ in range(3)] == [0.0, 0.0, 0.0]
    wait = lim.hit("k")
    assert 59 < wait <= 60                      # blocked; and the blocked hit is not counted
    now[0] += 30
    assert 29 < lim.hit("k") <= 30
    now[0] += 31                                # first event has now left the window
    assert lim.hit("k") == 0.0
    assert lim.hit("other") == 0.0              # keys are independent


def test_limiter_record_clear_and_blocked_for():
    lim = SlidingWindowLimiter(max_events=2, window_seconds=60)
    assert lim.blocked_for("k") == 0
    lim.record("k"); lim.record("k")
    assert lim.blocked_for("k") > 0
    lim.clear("k")
    assert lim.blocked_for("k") == 0


def test_limiter_memory_is_bounded():
    lim = SlidingWindowLimiter(max_events=1, window_seconds=3600, max_keys=50)
    for i in range(500):
        lim.hit(f"ip{i}")
    assert len(lim._events) <= 50


# ======================= rate limiting on the API =======================
def test_registration_is_rate_limited(client, monkeypatch):
    monkeypatch.setattr(auth._register_limiter, "max_events", 3)
    assert [register(client, f"u{i}@example.com").status_code for i in range(3)] == [201, 201, 201]
    r = register(client, "u3@example.com")
    assert r.status_code == 429 and int(r.headers["retry-after"]) > 0


def test_repeated_failed_logins_lock_out_even_the_right_password(client):
    register(client)
    for _ in range(5):
        assert login(client, password="wrong-password").status_code == 401
    r = login(client)                           # correct password, but locked out
    assert r.status_code == 429 and int(r.headers["retry-after"]) > 0


def test_lockout_is_per_account_not_global(client):
    register(client, "a@example.com"); register(client, "b@example.com")
    for _ in range(5):
        login(client, "a@example.com", "wrong-password")
    assert login(client, "a@example.com").status_code == 429
    assert login(client, "b@example.com").status_code == 200


def test_lockout_is_per_client_so_attackers_cannot_lock_out_the_owner(client, monkeypatch):
    monkeypatch.setattr(config, "TRUST_PROXY", True)
    register(client)
    attacker = {"X-Forwarded-For": "6.6.6.6"}
    for _ in range(5):
        login(client, password="wrong-password", headers=attacker)
    assert login(client, headers=attacker).status_code == 429
    assert login(client, headers={"X-Forwarded-For": "7.7.7.7"}).status_code == 200


def test_successful_login_resets_the_failure_count(client):
    register(client)
    for _ in range(4):
        login(client, password="wrong-password")
    assert login(client).status_code == 200
    for _ in range(4):                          # would be locked out by now if the count had not reset
        assert login(client, password="wrong-password").status_code == 401


def test_login_has_a_per_ip_cap_too(client, monkeypatch):
    monkeypatch.setattr(auth._login_ip_limiter, "max_events", 3)
    codes = [login(client, f"nobody{i}@example.com").status_code for i in range(4)]
    assert codes == [401, 401, 401, 429]


def test_forwarded_header_is_ignored_unless_proxy_is_trusted(client):
    # without ORBITGUARD_TRUST_PROXY a client cannot dodge the limit by faking X-Forwarded-For
    register(client)
    for i in range(5):
        login(client, password="wrong-password", headers={"X-Forwarded-For": f"9.9.9.{i}"})
    assert login(client, headers={"X-Forwarded-For": "1.2.3.4"}).status_code == 429


def test_proxy_mode_uses_the_last_forwarded_address(client, monkeypatch):
    monkeypatch.setattr(config, "TRUST_PROXY", True)
    register(client)
    # the client-supplied first entry changes every time, our proxy's appended entry does not
    for i in range(5):
        login(client, password="wrong-password", headers={"X-Forwarded-For": f"10.0.0.{i}, 5.5.5.5"})
    assert login(client, headers={"X-Forwarded-For": "10.0.0.99, 5.5.5.5"}).status_code == 429


def test_unknown_email_still_costs_a_password_hash(client, monkeypatch):
    calls = []
    real = auth.verify_password
    monkeypatch.setattr(auth, "verify_password", lambda p, s: calls.append(s) or real(p, s))
    assert login(client, "ghost@example.com").status_code == 401
    assert calls == [auth._DUMMY_HASH]          # so response time doesn't reveal which emails exist


def test_normal_login_still_works(client):
    token = register(client).json()["access_token"]
    assert client.get("/auth/me", headers={"Authorization": f"Bearer {token}"}).json()["email"] == "a@example.com"
    assert login(client).status_code == 200


# ======================= SQLite pragmas =======================
# (Postgres equivalents live in test_step10_postgres.py)
needs_sqlite = pytest.mark.skipif(db.is_postgres(), reason="SQLite-specific; Postgres runs test_step10_postgres.py")


@needs_sqlite
def test_foreign_keys_are_enforced():
    conn = auth._get_conn()
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    wconn = watchlist._conn()
    with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
        wconn.execute("INSERT INTO watchlist (user_id, norad_id, name, added_at) VALUES (999, 1, 'x', 'now')")
    conn.close(); wconn.close()


@needs_sqlite
def test_wal_mode_on_both_databases():
    a, c = auth._get_conn(), cache._get_conn()
    assert a.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
    assert c.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
    a.close(); c.close()


# ======================= ML warm-up =======================
def test_model_is_loaded_at_startup_not_on_first_request(tmp_path, monkeypatch):
    monkeypatch.setattr(ml_risk, "MODEL_DIR", tmp_path)
    monkeypatch.setattr(ml_risk, "MODEL_PATH", tmp_path / "m.joblib")
    monkeypatch.setattr(ml_risk, "METRICS_PATH", tmp_path / "m.json")
    monkeypatch.setattr(ml_risk, "_model", None)
    TestClient(main.app)                                   # no lifespan without `with`
    assert ml_risk._model is None
    with TestClient(main.app):                             # entering the context runs startup
        assert ml_risk._model is not None
        assert (tmp_path / "m.joblib").exists()


def test_concurrent_first_use_trains_once(tmp_path, monkeypatch):
    import threading
    monkeypatch.setattr(ml_risk, "MODEL_PATH", tmp_path / "missing.joblib")
    monkeypatch.setattr(ml_risk, "_model", None)
    trained = []
    monkeypatch.setattr(ml_risk, "train", lambda save=True: trained.append(1) or time.sleep(0.2) or {"model": object()})
    threads = [threading.Thread(target=ml_risk._get_model) for _ in range(6)]
    [t.start() for t in threads]; [t.join() for t in threads]
    assert len(trained) == 1


# ======================= data dir =======================
def test_data_dir_is_configurable_and_created(tmp_path):
    target = tmp_path / "nested" / "data"
    assert config.data_dir({"ORBITGUARD_DATA_DIR": str(target)}) == target and target.is_dir()
    assert config.data_dir({}) == BACKEND
