"""
OrbitGuard - runtime configuration
-----------------------------------
Everything deployment-specific comes from environment variables, validated once
at import time so a bad setup fails at startup instead of on the first request.

    ORBITGUARD_SECRET        required. JWT signing key, at least 32 characters.
                             Generate one:  python -c "import secrets; print(secrets.token_urlsafe(48))"
    ORBITGUARD_DEV           set to 1 for local development ONLY: allows a built-in
                             insecure secret (with a loud warning) when none is set.
    ORBITGUARD_CORS_ORIGINS  comma-separated browser origins allowed to call the API
                             (default: the Vite dev server, http://localhost:5173 and
                             http://127.0.0.1:5173).
    ORBITGUARD_DATA_DIR      where the SQLite databases and the ML model are stored
                             (default: this folder). Point it at a volume when deploying.
    ORBITGUARD_TRUST_PROXY   set to 1 only when running behind exactly one reverse proxy
                             that sets X-Forwarded-For; used for per-client rate limits.
    ORBITGUARD_ALERT_JOB     1 (default) runs the background job that precomputes watchlist
                             alerts and pushes them over /ws/alerts; 0 turns it off.
    ORBITGUARD_ALERT_INTERVAL  seconds between refreshes (default 300, minimum 30).
    ORBITGUARD_ALERT_GROUP / _HOURS / _THRESHOLD_KM   what the job screens: CelesTrak group
                             (default active), look-ahead window (default 24 h) and miss-distance
                             threshold (default 5 km).
"""

import logging
import os
from pathlib import Path
from urllib.parse import urlparse

log = logging.getLogger("orbitguard.config")

DEV_DEFAULT_SECRET = "dev-only-change-me"
MIN_SECRET_LENGTH = 32
DEFAULT_CORS_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]


def _flag(value: str | None) -> bool:
    return (value or "").strip().lower() in ("1", "true", "yes", "on")


def load_secret(env=os.environ) -> str:
    """Return the JWT signing secret, or raise RuntimeError if it is missing or weak."""
    secret = (env.get("ORBITGUARD_SECRET") or "").strip()
    weak = secret == DEV_DEFAULT_SECRET or len(secret) < MIN_SECRET_LENGTH

    if secret and not weak:
        return secret

    if _flag(env.get("ORBITGUARD_DEV")):
        log.warning("ORBITGUARD_DEV is set: using an INSECURE JWT secret. Anyone can forge login "
                    "tokens. Never run like this in production.")
        return secret or DEV_DEFAULT_SECRET

    problem = ("ORBITGUARD_SECRET is not set" if not secret
               else "ORBITGUARD_SECRET is the well-known development value" if secret == DEV_DEFAULT_SECRET
               else f"ORBITGUARD_SECRET is too short ({len(secret)} characters; need at least {MIN_SECRET_LENGTH})")
    raise RuntimeError(
        f"{problem}, so login tokens could be forged. Refusing to start.\n"
        '  1. Generate a secret:  python -c "import secrets; print(secrets.token_urlsafe(48))"\n'
        "  2. Set it:  Windows cmd: set ORBITGUARD_SECRET=<value>   |   macOS/Linux: export ORBITGUARD_SECRET=<value>\n"
        "  (For local development only you can set ORBITGUARD_DEV=1 instead.)"
    )


def parse_cors_origins(env=os.environ) -> list[str]:
    """Allowed browser origins from ORBITGUARD_CORS_ORIGINS (validated, trailing slashes removed)."""
    raw = env.get("ORBITGUARD_CORS_ORIGINS")
    if raw is None or not raw.strip():
        return list(DEFAULT_CORS_ORIGINS)
    origins = []
    for item in raw.split(","):
        origin = item.strip().rstrip("/")
        if not origin:
            continue
        if origin == "*":
            log.warning("ORBITGUARD_CORS_ORIGINS contains '*': every website can call this API from a browser.")
        else:
            u = urlparse(origin)
            if u.scheme not in ("http", "https") or not u.netloc or u.path or u.query or u.fragment:
                raise RuntimeError(
                    f"Invalid ORBITGUARD_CORS_ORIGINS entry {item.strip()!r}: use origins such as "
                    "https://app.example.com (scheme + host [+ port], no path)."
                )
        origins.append(origin)
    if not origins:
        raise RuntimeError("ORBITGUARD_CORS_ORIGINS is set but contains no origins.")
    return origins


def data_dir(env=os.environ) -> Path:
    """Folder for the SQLite databases and the ML model (created if missing)."""
    path = Path(env.get("ORBITGUARD_DATA_DIR") or Path(__file__).parent).expanduser()
    path.mkdir(parents=True, exist_ok=True)
    return path


def trust_proxy(env=os.environ) -> bool:
    return _flag(env.get("ORBITGUARD_TRUST_PROXY"))


DATA_DIR = data_dir()
CORS_ORIGINS = parse_cors_origins()
TRUST_PROXY = trust_proxy()


def alert_job_settings(env=os.environ) -> dict:
    """Settings for the background alert job (validated like everything else at startup)."""
    def number(name: str, default: float, low: float, high: float) -> float:
        raw = (env.get(name) or "").strip()
        if not raw:
            return default
        try:
            value = float(raw)
        except ValueError:
            raise RuntimeError(f"{name}={raw!r} is not a number")
        if not (low <= value <= high):
            raise RuntimeError(f"{name}={raw} is out of range ({low:g} to {high:g})")
        return value

    raw_flag = env.get("ORBITGUARD_ALERT_JOB")
    return {
        "enabled": True if raw_flag is None or not raw_flag.strip() else _flag(raw_flag),
        "interval_seconds": number("ORBITGUARD_ALERT_INTERVAL", 300.0, 30.0, 86_400.0),
        "group": (env.get("ORBITGUARD_ALERT_GROUP") or "active").strip(),
        "hours": number("ORBITGUARD_ALERT_HOURS", 24.0, 0.1, 168.0),
        "threshold_km": number("ORBITGUARD_ALERT_THRESHOLD_KM", 5.0, 0.1, 1000.0),
    }


ALERT_JOB = alert_job_settings()
