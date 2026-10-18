# OrbitGuard API.  Build from the backend/ folder:   docker build -t orbitguard-api backend
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ORBITGUARD_DATA_DIR=/data

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Run as a non-root user; /data holds the ML model and, unless ORBITGUARD_DATABASE_URL points at Postgres,
# the SQLite databases (mount a volume there).
RUN useradd --create-home --uid 1000 app && mkdir -p /data && chown app:app /data
USER app
VOLUME /data

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/', timeout=3)" || exit 1

# ONE worker on purpose: rate-limit counters and the alert job's snapshots live in process memory
# (Postgres, when enabled, stores users/watchlists/cache but does not change that).
# ORBITGUARD_SECRET must be supplied at run time; the app refuses to start without it.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
