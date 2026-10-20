# OrbitGuard

**OrbitGuard** is an AI-assisted space situational awareness and satellite collision risk monitoring platform. It fetches live orbital data from CelesTrak, calculates satellite trajectories using high-fidelity SGP4 propagation, screens for close approaches (conjunctions) with time-of-closest-approach (TCA) forecasting, predicts collision risks using Machine Learning, models what-if avoidance maneuvers, and visualizes real-time orbits in an immersive 3D dashboard alongside an interactive space-science educational Academy.

---

## Key Features

- **Live 3D Orbital Visualization**: Real-time rendering of Earth and tracked satellites using Three.js and React Three Fiber. Dense SGP4 trajectory sampling eliminates Catmull-Rom spline loop artifacts.
- **Full-Screen Orbital Map**: Immersive viewport map with interactive camera controls, satellite selection, telemetry HUD overlays, and live status badges.
- **Conjunction Assessment & Forecasting**: High-performance spatial screening using SciPy KDTrees to screen the entire active catalog in milliseconds, paired with time-window screening with exact Time of Closest Approach (TCA).
- **Machine Learning Risk Scoring**: Random Forest classifier evaluating collision risk (Low, Medium, High, Critical) from miss distance, relative velocity, mean altitude, and orbital gap.
- **Real What-If Maneuver Simulator**: Simulates impulsive burns (along-track, radial, and cross-track delta-v in the satellite's RTN frame), re-propagates the trajectory, and reports the new closest approach distance, TCA, and post-maneuver risk.
- **Live Alert Feed & WebSockets**: Background screening job diffing snapshots and pushing real-time conjunction alerts over WebSockets (`/ws/alerts`).
- **OrbitGuard Academy**: Comprehensive space-science education platform with structured lessons on orbital mechanics, Keplerian elements, conjunction assessment, and collision avoidance maneuvers, featuring interactive quizzes and knowledge checks.
- **User Authentication & Watchlist**: Secure user registration, login, and JWT-authenticated session management with personalized satellite watchlists and per-user alert feeds.
- **Postgres & SQLite Storage**: Multi-database support with SQLite by default and optional managed PostgreSQL pooling.
- **Aerospace Design System**: High-contrast dark navy space theme (`#03070d`) with unified typography scale (>17px base everywhere) ensuring readability across desktop, tablet, and mobile displays.

---

## Project Structure

```
ORBIT-GUARD-/
├── backend/                        # Python + FastAPI Backend
│   ├── main.py                     # API routes and application entrypoint
│   ├── orbit_engine.py             # CelesTrak client & SGP4 propagation
│   ├── conjunction.py              # Snapshot conjunction detection (KDTree & naive)
│   ├── conjunction_window.py       # Time-window screening with TCA calculation
│   ├── maneuver.py                 # Delta-v impulse burns and maneuver propagation
│   ├── geodetic.py                 # TEME to latitude/longitude/height (WGS-84)
│   ├── ground_track.py             # Sub-satellite ground tracks with meridian splitting
│   ├── alert_service.py            # Watchlist screening shared by REST and background job
│   ├── alert_hub.py                # Background alert job, snapshot diffing & WebSockets
│   ├── forecast_service.py         # Validation, TLE age, and forecast helpers
│   ├── db.py                       # Database abstraction (SQLite default / Postgres option)
│   ├── cache.py                    # SQLite/Postgres TLE caching layer
│   ├── auth.py                     # Registration, login, and JWT authentication
│   ├── watchlist.py                # Per-user satellite watchlist endpoints
│   ├── ml_risk.py                  # Random Forest collision risk classifier
│   ├── ratelimit.py                # In-memory IP/user rate limiters
│   ├── validate_socrates.py        # Validation against external SOCRATES benchmarks
│   ├── migrate_sqlite_to_postgres.py # SQLite to Postgres migration utility
│   ├── fetch_and_propagate.py      # Standalone CLI prototype script
│   ├── tests/                      # Pytest suite (offline with mocked CelesTrak)
│   ├── requirements.txt            # Runtime dependencies
│   └── Dockerfile                  # Container definition
├── frontend/                       # React 19 + Vite 8 Application
│   ├── src/
│   │   ├── components/
│   │   │   ├── Earth.jsx           # 3D textured Earth sphere
│   │   │   ├── Header.jsx          # Top navigation, search, and notification panels
│   │   │   ├── RiskOverview.jsx    # Live conjunction breakdown widget
│   │   │   ├── Satellite.jsx       # 3D interactive satellite markers
│   │   │   └── SpaceScene.jsx      # Canvas setup, orbit trails & camera controls
│   │   ├── data/
│   │   │   └── lessons.js          # Academy curriculum and quiz bank
│   │   ├── pages/
│   │   │   ├── Auth.css            # Styles for authentication cards
│   │   │   ├── ConjunctionAnalysis.jsx # Deep-dive collision analysis & maneuver simulator
│   │   │   ├── Conjunctions.jsx    # Close approaches list and screening summary
│   │   │   ├── Landing.jsx         # Public overview and features landing page
│   │   │   ├── Learn.jsx           # Academy module dashboard
│   │   │   ├── Lesson.jsx          # Interactive lesson reader and quiz runner
│   │   │   ├── Login.jsx           # User sign-in
│   │   │   ├── ObjectDetails.jsx   # Detailed satellite telemetry & historical data
│   │   │   ├── Objects.jsx         # Catalog search and satellite directory
│   │   │   ├── OrbitalMap.jsx      # Full-screen 3D orbital map
│   │   │   ├── Overview.jsx        # Main operations dashboard
│   │   │   └── Register.jsx        # Account registration
│   │   ├── styles/
│   │   │   ├── Landing.css         # Public landing page stylesheet
│   │   │   └── Learn.css           # Academy platform stylesheet
│   │   ├── api.js                  # Frontend API client and auth helper
│   │   ├── App.css                 # Master aerospace design system (>17px font tokens)
│   │   ├── App.jsx                 # Route definitions and session restoration
│   │   ├── index.css               # Base CSS resets
│   │   └── main.jsx                # React DOM root
│   ├── package.json
│   └── vite.config.js
├── docker-compose.yml              # Multi-container service definitions
├── .env.example                    # Example environment configuration
└── index.html                      # Standalone zero-build single-file prototype
```

---

## Getting Started

### Prerequisites
- **Python 3.10+** (tested on 3.12)
- **Node.js 18+** and **npm**

---

### 1. Backend Setup

1. Open a terminal in the project root and navigate to the backend directory:
   ```bash
   cd backend
   ```

2. Create and activate a Python virtual environment:
   ```bash
   # Windows (PowerShell)
   python -m venv venv
   .\venv\Scripts\Activate.ps1

   # macOS / Linux
   python3 -m venv venv
   source venv/bin/activate
   ```

3. Install required dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Configure environment variables:
   Generate a secret key (required for JWT security):
   ```bash
   python -c "import secrets; print(secrets.token_urlsafe(48))"
   ```
   Set it in your terminal:
   ```bash
   # Windows PowerShell
   $env:ORBITGUARD_SECRET="<your-generated-token>"

   # Windows CMD
   set ORBITGUARD_SECRET=<your-generated-token>

   # macOS / Linux
   export ORBITGUARD_SECRET="<your-generated-token>"

   # For quick local testing without setting keys:
   # set ORBITGUARD_DEV=1
   ```

5. Launch the FastAPI server:
   ```bash
   uvicorn main:app --reload --port 8000
   ```
   *The backend will be live at `http://127.0.0.1:8000` with interactive Swagger docs at `http://127.0.0.1:8000/docs`.*

---

### 2. Frontend Setup

1. Open a new terminal and navigate to the frontend directory:
   ```bash
   cd frontend
   ```

2. Install npm dependencies:
   ```bash
   npm install
   ```

3. Start the Vite development server:
   ```bash
   npm run dev
   ```
   *Open your browser to `http://localhost:5173` to view the application.*

4. To create a production build:
   ```bash
   npm run build
   ```

---

## API Reference

| Endpoint | Method | Description |
|---|---|---|
| `/objects` | `GET` | Live satellite positions (`?group=stations\|active&limit=100`) including latitude, longitude, and geodetic altitude |
| `/objects/{norad_id}` | `GET` | Position and geodetic parameters for a single satellite by NORAD catalog ID |
| `/ground-track/{norad_id}` | `GET` | Sub-satellite coordinates over time window (`?hours=1.5&step_seconds=30`) with segments split across ±180° meridian |
| `/conjunctions` | `GET` | Snapshot close approaches with risk levels (`?threshold_km=5&method=kdtree\|naive`) |
| `/conjunctions/forecast` | `GET` | Screens time window (up to 72h) and returns close approaches with exact **Time of Closest Approach (TCA)** |
| `/trajectory/{norad_id}` | `GET` | Predicts future coordinates over sample intervals (`?hours=0,1,6,12,24`) |
| `/what-if` | `GET` | Simulates impulsive burn (`?dv_along_ms=`, `?dv_radial_ms=`, `?dv_cross_ms=`) and computes new miss distance and TCA |
| `/model-info` | `GET` | Returns Random Forest ML model metrics, accuracy, and feature importances |
| `/risk-score` | `GET` | Evaluates a hypothetical close approach with the ML model |
| `/cache-status` | `GET` | Reports TLE data freshness, age in days, and cache status |
| `/auth/register` | `POST` | Registers a new user account (`name`, `email`, `password`) |
| `/auth/login` | `POST` | Authenticates credentials and returns a JWT access token |
| `/auth/me` | `GET` | Retrieves profile of currently authenticated user |
| `/watchlist` | `GET` | Lists user's watched satellites (`?live=true` appends current coordinates) |
| `/watchlist` | `POST` | Adds a satellite to user watchlist |
| `/watchlist/{norad_id}` | `DELETE` | Removes a satellite from user watchlist |
| `/watchlist/alerts` | `GET` | Upcoming close approaches with TCA for user's watched satellites |
| `/watchlist/alerts/latest` | `GET` | Instant precomputed alert snapshot from background screening job |
| `/ws/alerts` | `WS` | Real-time WebSocket feed pushing conjunction alerts, escalations, and state updates |

---

## Background Alert Engine & WebSockets

- **Precomputed Screening**: A background worker screens the active catalog on a scheduled interval (default 300s), saving computing time and serving user feeds in milliseconds.
- **WebSocket Streaming (`/ws/alerts`)**: Clients authenticate via JWT and receive immediate state snapshots, followed by push updates carrying `changes` (`new`, `escalated`, `cleared`, `expired`, `updated`).
- **Data Freshness Tracking**: TLEs are tracked by age; items are marked **fresh** (<7 days), **stale** (7–30 days), or **unreliable** (>30 days).

---

## OrbitGuard Academy

The platform includes an integrated aerospace education suite designed for students and researchers:

- **Orbital Mechanics Fundamentals**: Kepler's Laws, orbital shapes (LEO, MEO, GEO), eccentricity, and inclination.
- **Two-Line Element Sets (TLEs)**: Decoding NORAD satellite numbers, epoch, mean motion, and drag terms.
- **Conjunction Assessment**: Screening algorithms, miss distances, covariance ellipsoids, and time of closest approach (TCA).
- **Collision Avoidance Maneuvers**: Delta-v calculations, along-track vs. radial burns, and post-maneuver tracking.
- **Interactive Quizzes**: Formative multiple-choice questions with instant feedback and pedagogical explanations.

---

## Verification & Real-World Validation

- **Real Data Verified**: Propagated orbital positions are cross-referenced with live CelesTrak TLE feeds (e.g. International Space Station altitude reliably tracks within expected ~400–430 km bounds).
- **Dense Trajectory Sampling**: Single-satellite orbit paths query dense 2-minute SGP4 intervals (60 points across ~100 minutes) to eliminate wild spline overshoot loops.
- **Accessible Typography Scale**: All headings, body copy, table cells, buttons, and metadata are scaled to ≥18px with strong contrast ratios against dark navy backgrounds.

---

## Deployment & Docker

Copy `.env.example` to `.env` and set your configuration:

```bash
docker compose up --build
```

To run with PostgreSQL instead of SQLite:
```bash
docker compose --profile postgres up --build
```

---

## Contributors

- **Dhwani Singhal** — Backend architecture, orbital mechanics engine, SGP4 propagation, API & ML scoring
- **Aishwarya-93** — Frontend implementation, 3D visualization, UI/UX design system & Academy platform
