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
│   ├── conjunction.py    # Conjunction detection + what-if simulator
│   ├── cache.py          # SQLite caching layer
│   └── fetch_and_propagate.py  # standalone CLI script (Day 1 prototype)
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
uvicorn main:app --reload
```

API docs available at `http://127.0.0.1:8000/docs` once running.

### Endpoints

| Endpoint | Description |
|---|---|
| `GET /objects` | Live positions for a group of tracked satellites (`?group=stations` or `?group=active`, `?limit=`) |
| `GET /objects/{norad_id}` | Position for a single satellite by NORAD catalog ID |
| `GET /conjunctions` | Detected close approaches with risk levels (`?threshold_km=`, `?method=naive\|kdtree`) |
| `GET /trajectory/{norad_id}` | Predicted future positions (`?hours=0,1,6,12,24,48`) |
| `GET /what-if` | Simulates an altitude adjustment and shows before/after risk (`?norad_id=&other_norad_id=&altitude_delta_km=`) |
| `GET /cache-status` | Shows cache freshness for a given group |

### Tech

Python, FastAPI, [sgp4](https://pypi.org/project/sgp4/), [skyfield](https://rhodesmill.org/skyfield/), scipy (KDTree), SQLite.

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

The backend has been tested against live CelesTrak data — e.g. the ISS reliably returns an altitude in the ~400–430 km range, matching its known real-world orbit. The what-if simulator has been verified to correctly reduce a conjunction's risk level when a sufficient altitude adjustment is applied.

## Roadmap

- [ ] Scale to 100+ tracked objects (currently tested with ~10–20)
- [ ] Migrate SQLite cache to Postgres
- [ ] WebSocket push instead of polling
- [ ] ML-based risk scoring (Random Forest / XGBoost) alongside the current rule-based system

## Contributors

- Dhwani Singhal — Backend, orbital mechanics, API
- Aishwarya-93 — Frontend (React + Three.js)
