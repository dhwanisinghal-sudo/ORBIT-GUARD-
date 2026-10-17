"""
OrbitGuard - authentication (registration + login)
---------------------------------------------------
User store (SQLite by default, Postgres via ORBITGUARD_DATABASE_URL; see db.py), PBKDF2
password hashing (stdlib, no extra native deps) and JWT access tokens.

Endpoints (wired up in main.py):
    POST /auth/register  -> create an account
    POST /auth/login     -> exchange email + password for a JWT
    GET  /auth/me        -> current user (requires Authorization: Bearer <token>)

ORBITGUARD_SECRET must be set (see config.py); the app refuses to start without it.

Abuse protection (in-memory, per process - see ratelimit.py):
    register: 10 attempts / hour / client IP
    login:    20 attempts / minute / client IP, and 5 FAILED attempts / 15 min per
              (client IP, email) pair - a correct password is refused while locked out.
Blocked requests get 429 with a Retry-After header.
"""

import hashlib
import hmac
import math
import re
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path

import jwt  # PyJWT
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

import config
import db
from ratelimit import SlidingWindowLimiter

DB_PATH = config.DATA_DIR / "orbitguard_users.db"
SECRET_KEY = config.load_secret()   # raises at startup if missing/weak
ALGORITHM = "HS256"
TOKEN_TTL_MINUTES = 60 * 24
PBKDF2_ITERATIONS = 200_000
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

router = APIRouter(prefix="/auth", tags=["auth"])
_bearer = HTTPBearer(auto_error=False)

_register_limiter = SlidingWindowLimiter(max_events=10, window_seconds=3600)
_login_ip_limiter = SlidingWindowLimiter(max_events=20, window_seconds=60)
_login_fail_limiter = SlidingWindowLimiter(max_events=5, window_seconds=900)


def reset_rate_limits() -> None:
    """Forget all rate-limit counters (used by tests)."""
    for limiter in (_register_limiter, _login_ip_limiter, _login_fail_limiter):
        limiter.reset()


def _client_ip(request: Request) -> str:
    """
    The caller's IP. Behind a reverse proxy (ORBITGUARD_TRUST_PROXY=1) that is the LAST
    X-Forwarded-For entry - the one our own proxy appended; earlier entries are client-supplied.
    """
    if config.TRUST_PROXY:
        forwarded = request.headers.get("x-forwarded-for", "")
        if forwarded:
            return forwarded.split(",")[-1].strip() or "unknown"
    return request.client.host if request.client else "unknown"


def _too_many(retry_after: float, message: str) -> HTTPException:
    seconds = max(1, math.ceil(retry_after))
    return HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, f"{message}. Try again in {seconds} s.",
                         headers={"Retry-After": str(seconds)})


# ---------- database ----------

def _get_conn():
    """Connection to the users database (tables are created on first use); close it when done."""
    return db.connect("users", DB_PATH, dict_rows=True)


# ---------- password hashing ----------

def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt.hex()}${digest.hex()}"


_DUMMY_HASH = hash_password("timing-equaliser")   # checked when the email is unknown, so timing doesn't reveal it


def verify_password(password: str, stored: str) -> bool:
    try:
        _, iters, salt_hex, digest_hex = stored.split("$")
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), bytes.fromhex(salt_hex), int(iters)
        )
        return hmac.compare_digest(digest.hex(), digest_hex)
    except ValueError:
        return False


# ---------- tokens ----------

def create_token(user_id: int, email: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "email": email,
        "iat": now,
        "exp": now + timedelta(minutes=TOKEN_TTL_MINUTES),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def user_from_token(token: str) -> tuple[dict, int]:
    """Validate a JWT and return (user row, expiry as a unix timestamp). Raises HTTP 401."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT id, name, email, created_at FROM users WHERE id = ?",
            (int(payload["sub"]),),
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User no longer exists")
    return dict(row), int(payload["exp"])


def get_current_user(creds: HTTPAuthorizationCredentials | None = Depends(_bearer)) -> dict:
    """Dependency: use on any endpoint that should require login."""
    if creds is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    return user_from_token(creds.credentials)[0]


# ---------- schemas ----------

class RegisterRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    email: str
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    email: str
    password: str


# ---------- routes ----------

@router.post("/register", status_code=status.HTTP_201_CREATED)
def register(body: RegisterRequest, request: Request):
    retry = _register_limiter.hit(_client_ip(request))
    if retry:
        raise _too_many(retry, "Too many registration attempts")
    email = body.email.strip().lower()
    if not EMAIL_RE.match(email):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Invalid email address")
    conn = _get_conn()
    try:
        try:
            cur = conn.execute(
                "INSERT INTO users (name, email, password_hash, created_at) VALUES (?, ?, ?, ?) RETURNING id",
                (body.name.strip(), email, hash_password(body.password),
                 datetime.now(timezone.utc).isoformat()),
            )
            user_id = cur.fetchone()["id"]
            conn.commit()
        except db.IntegrityError:
            raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists")
    finally:
        conn.close()
    return {
        "access_token": create_token(user_id, email),
        "token_type": "bearer",
        "user": {"id": user_id, "name": body.name.strip(), "email": email},
    }


@router.post("/login")
def login(body: LoginRequest, request: Request):
    ip = _client_ip(request)
    retry = _login_ip_limiter.hit(ip)
    if retry:
        raise _too_many(retry, "Too many login attempts")
    email = body.email.strip().lower()
    fail_key = f"{ip}|{email}"
    retry = _login_fail_limiter.blocked_for(fail_key)
    if retry:
        raise _too_many(retry, "Too many failed logins for this account")

    conn = _get_conn()
    try:
        row = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    finally:
        conn.close()
    stored = row["password_hash"] if row is not None else _DUMMY_HASH
    password_ok = verify_password(body.password, stored)      # always runs: same cost for unknown emails
    if row is None or not password_ok:
        _login_fail_limiter.record(fail_key)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect email or password")
    _login_fail_limiter.clear(fail_key)
    return {
        "access_token": create_token(row["id"], row["email"]),
        "token_type": "bearer",
        "user": {"id": row["id"], "name": row["name"], "email": row["email"]},
    }


@router.get("/me")
def me(user: dict = Depends(get_current_user)):
    return user
