# OrbitGuard

AI-assisted satellite collision risk monitoring system. Fetches real orbital data, predicts satellite positions, detects potential collisions (conjunctions), scores risk, and visualizes everything on a live 3D dashboard.

## What it does

- **Fetches real orbital data** from [CelesTrak](https://celestrak.org) (TLE / orbital elements)
- **Predicts satellite positions** using SGP4 orbital propagation, now or hours into the future
- **Detects conjunctions** (close approaches between objects) using both a naive O(n²) check and a KDTree-based spatial search for scale
- **Scores collision risk** (LOW / MEDIUM / HIGH) based on distance and relative velocity
- **Simulates "what-if" maneuvers** — shift an object's altitude and see how the risk changes
- **Visualizes it all** on a live-updating 3D Earth dashboard

## Project structure

```
orbitguard/
├── backend/              # Python + FastAPI backend
│   ├── main.py           # API endpoints
│   ├── orbit_engine.py   # CelesTrak fetch + SGP4 propagation
│   ├── conjunction.py    # Conjunction detection (snapshot)
│   ├── maneuver.py       # What-if maneuver: delta-v -> re-propagate -> new TCA / miss distance
│   ├── geodetic.py       # TEME -> latitude / longitude / height (WGS-84)
│   ├── ground_track.py   # Sub-satellite track over a time window
│   ├── conjunction_window.py  # Time-window screening with time of closest approach (TCA)
│   ├── cache.py          # SQLite TLE cache (groups + single objects)
│   ├── config.py         # Environment-variable settings, validated at startup
│   ├── ratelimit.py      # In-memory rate limiter used by login/register
│   ├── auth.py           # Registration, login, JWT auth
│   ├── watchlist.py      # Per-user satellite watchlist + conjunction alerts
│   ├── forecast_service.py  # Shared validation, TLE-age and error helpers for the forecast endpoints
│   ├── ml_risk.py        # Random Forest risk scoring
│   ├── fetch_and_propagate.py  # standalone CLI script (Day 1 prototype)
│   ├── tests/            # pytest suite (offline; CelesTrak is mocked)
│   ├── requirements.txt  # pinned runtime dependencies
│   └── Dockerfile
├── docker-compose.yml
├── .env.example
├── frontend/             # React + Three.js dashboard
└── index.html            # Standalone single-file dashboard (no build step needed)
```

## Backend

### Setup

```bash
cd backend
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # macOS/Linux

pip install -r requirements.txt

# The API refuses to start without a JWT secret (>= 32 characters). Generate and set one:
python -c "import secrets; print(secrets.token_urlsafe(48))"
set ORBITGUARD_SECRET=<paste it here>          # Windows cmd
# export ORBITGUARD_SECRET=<paste it here>     # macOS/Linux
# (local development only: set ORBITGUARD_DEV=1 instead to use an insecure built-in secret)

uvicorn main:app --reload
```

Run the tests with `pip install -r requirements-dev.txt` and `python -m pytest tests -q`. Dependencies are pinned to the versions the tests pass on (Python 3.12).

API docs available at `http://127.0.0.1:8000/docs` once running.

### Endpoints

| Endpoint | Description |
|---|---|
| `GET /objects` | Live positions for a group of tracked satellites (`?group=stations` or `?group=active`, `?limit=`) |
| `GET /objects/{norad_id}` | Position for a single satellite by NORAD catalog ID. Every position now also carries `latitude_deg`, `longitude_deg` and `geodetic_altitude_km` (height above the WGS-84 ellipsoid; `altitude_km` stays `\|r\| - 6371`) |
| `GET /ground-track/{norad_id}` | Sub-satellite latitude/longitude over `?hours=` (default 1.5, max 72) every `?step_seconds=` (default 30), from `?start=`. Returns `points` plus `segments` already split at the ±180° meridian for map layers |
| `GET /conjunctions` | Detected close approaches with risk levels (`?threshold_km=`, `?method=kdtree\|naive`; `kdtree` is the default and handles the full `active` catalog in milliseconds, `naive` is the O(n²) reference and is refused above 1,500 objects) |
| `GET /conjunctions/forecast` | Screens the next `?hours=` (max 72) and returns each close approach with its **time of closest approach (TCA)**, miss distance and relative speed (`?threshold_km=`, `?step_seconds=`, `?start=`, `?include_coorbiting=`, `?ml=true`) |
| `GET /trajectory/{norad_id}` | Predicted future positions (`?hours=0,1,6,12,24,48`) |
| `GET /what-if` | Real maneuver analysis: applies an impulsive burn to `norad_id` (`?dv_along_ms=`, `?dv_radial_ms=`, `?dv_cross_ms=` in its RTN frame, at `?burn_in_hours=`), re-propagates, and reports the closest approach to `other_norad_id` before and after (`?window_hours=`, `?step_seconds=`, `?start=`). `altitude_delta_km` still works but is deprecated (converted to the equivalent along-track burn) |
| `GET /cache-status` | Shows cache freshness for a group (`?group=`) or a single object (`?norad_id=`) |
| `GET /model-info` | ML risk model accuracy, per-class metrics, feature importance |
| `GET /risk-score` | ML risk score for a hypothetical close approach (`?distance_km=&relative_velocity_km_s=&altitude_km=`) |
| `POST /auth/register` | Create an account (`name`, `email`, `password`) and get a JWT |
| `POST /auth/login` | Log in (`email`, `password`) and get a JWT |
| `GET /auth/me` | Current user (requires `Authorization: Bearer <token>`) |
| `POST /watchlist` | Add a satellite to your watchlist (auth required) |
| `GET /watchlist` | List your watchlist (`?live=true` adds current positions) |
| `DELETE /watchlist/{norad_id}` | Remove a satellite from your watchlist |
| `GET /watchlist/alerts` | Upcoming close approaches (with TCA) involving your saved satellites (auth required; same params as `/conjunctions/forecast`, default `group=active`; limited to 6 calls/min per user) |

`GET /conjunctions` also accepts `?ml=true` to add `ml_risk_level`, `ml_risk_score` and `ml_probabilities` from the ML model.

`GET /conjunctions` only compares positions at the current instant. `GET /conjunctions/forecast` scans a whole time window instead: it propagates every object on a coarse grid, uses a KDTree plus a straight-line approach estimate to discard pairs that cannot come close, then refines the time of closest approach of the survivors with exact SGP4 states. Objects flying in formation (e.g. a vehicle docked to the ISS) are excluded by default because they are not collision risks. `GET /watchlist/alerts` runs the same screening but only for pairs that involve the caller's saved satellites, which is cheaper than a full-catalog forecast (about 9 s and 260 MB for the whole active catalog over 24 h on synthetic data, versus 25 s and 730 MB). Each watched satellite is listed with its own alert count; one whose TLE could not be fetched or propagated is marked `unavailable` with a reason, so "no alerts" is never confused with "could not check". Results are screening output: TLE accuracy degrades by several km per day, so treat distant-future TCAs with caution.

### TLE caching and data freshness

TLEs are cached in SQLite for 30 minutes, both per group and per object, so `/objects/{id}`, `/trajectory`, `/what-if` and `/watchlist?live=true` no longer hit CelesTrak on every call (a 20-satellite watchlist costs 0 requests on a warm cache and at most 20, fetched 4 at a time, on a cold one). If CelesTrak is unreachable, an expired copy up to 24 hours old is served instead of an error, and the response says so.

Nothing degrades silently. Every response carries:

- `cache` - where the data came from (`upstream`, `cache` or `stale_cache`) and its age.
- `tle_age_days` / `tle_status` (per object; `tle_staleness` rolls them up for lists) - **fresh** under 7 days, **stale** 7-30 days (accuracy degraded), **unreliable** over 30 days. Age is measured to the time being propagated. Forecast conjunctions get a `tle_status` equal to the weaker of their two TLEs.
- `skipped` / `objects_unpropagatable` - objects SGP4 could not propagate (decayed, malformed, TLE too old), with counts per SGP4 error code and a few examples, instead of vanishing from the results.
- `warnings` - plain-English notes summarising the above.

`/objects` `count` is the number of objects actually returned; `requested` is how many TLEs were fetched. A non-positive `limit` is rejected with 400.

### Security and deployment

Configuration is by environment variable (see `.env.example` and `config.py`); a bad setup stops the app at startup instead of failing later.

| Variable | Purpose |
|---|---|
| `ORBITGUARD_SECRET` | **Required.** JWT signing key, 32+ characters. The app refuses to start without it (or with the old `dev-only-change-me` default). |
| `ORBITGUARD_DEV=1` | Local development only: allows an insecure built-in secret, with a loud warning. |
| `ORBITGUARD_CORS_ORIGINS` | Comma-separated frontend origins allowed to call the API from a browser. Default: the Vite dev server (`http://localhost:5173`, `http://127.0.0.1:5173`). |
| `ORBITGUARD_DATA_DIR` | Where the SQLite databases and the ML model live (default: `backend/`). Mount a volume here when deploying. |
| `ORBITGUARD_TRUST_PROXY=1` | Only behind exactly one reverse proxy that sets `X-Forwarded-For`; rate limits then use that address instead of the proxy's. |

- **Rate limiting:** registration is limited to 10 attempts/hour per IP; login to 20 attempts/minute per IP and 5 *failed* attempts per 15 minutes per (IP, email) pair, during which even the right password is refused. Blocked requests get `429` with `Retry-After`. Counters are in memory, so they are per process and reset on restart.
- **Passwords/timing:** login does the same password-hash work for unknown emails, so response time doesn't reveal which emails are registered.
- **SQLite:** foreign keys are enforced (`PRAGMA foreign_keys=ON`) and WAL mode is on, so concurrent requests don't block each other.
- **Startup:** the ML model is loaded (or trained) when the server starts, not during the first `?ml=true` request.
- **Docker:** `docker compose up --build` after copying `.env.example` to `.env` and setting `ORBITGUARD_SECRET`. It runs **one** worker on purpose (in-memory rate limits, single SQLite file); moving to several workers means moving both to shared stores (Redis/Postgres).

### ML risk scoring

A Random Forest classifier scores each conjunction (LOW / MEDIUM / HIGH) from distance, relative velocity, mean altitude and altitude gap. **Note:** there is no public dataset of real collision outcomes, so the model is trained on synthetic labels from a physics-inspired formula plus noise. It is a scoring framework ready to be retrained on real conjunction data (e.g. CDMs), not a validated collision predictor. Run `python ml_risk.py` to retrain; `/model-info` reports the metrics.

### Authentication

Passwords are hashed with PBKDF2-SHA256 and sessions use JWT. Set the `ORBITGUARD_SECRET` environment variable in any real deployment.

### Tech

Python, FastAPI, scikit-learn, PyJWT, [sgp4](https://pypi.org/project/sgp4/), scipy (KDTree), SQLite.

## Frontend

Two options:

1. **`index.html`** — a standalone dashboard with no build step. Just open it in a browser while the backend is running. Renders a 3D Earth (Three.js via CDN) with live satellite positions and conjunction alerts, polling the backend every 15 seconds.
2. **`frontend/`** — a full React + Vite application with dedicated components (`Earth`, `Satellite`, `ConjunctionAlerts`, `RiskOverview`, etc.). Run with:

```bash
cd frontend
npm install
npm run dev
```

## Verified with real data

The backend has been tested against live CelesTrak data — e.g. the ISS reliably returns an altitude in the ~400–430 km range, matching its known real-world orbit. The what-if maneuver numerics are checked in the test suite against the Clohessy–Wiltshire relative-motion solution (within 2% over three orbits); the "before" numbers are plain SGP4, and the burn's effect is added as the difference of two identical J2 integrations. It is an impulsive-burn screening aid: no drag or solar-pressure difference, and SGP4's own TLE-age error applies.

## Roadmap

- [ ] Scale to 100+ tracked objects (currently tested with ~10–20)
- [ ] Migrate SQLite cache to Postgres
- [ ] WebSocket push instead of polling
- [x] ML-based risk scoring (Random Forest) alongside the current rule-based system
- [x] User registration, login and per-user watchlist
- [ ] Retrain ML model on real conjunction data

## Contributors

- Dhwani Singhal — Backend, orbital mechanics, API
- Aishwarya-93 — Frontend (React + Three.js)
