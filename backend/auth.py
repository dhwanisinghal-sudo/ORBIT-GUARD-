"""
OrbitGuard - authentication (registration + login)
---------------------------------------------------
SQLite-backed user store, PBKDF2 password hashing (stdlib, no extra
native deps) and JWT access tokens.

Endpoints (wired up in main.py):
    POST /auth/register  -> create an account
    POST /auth/login     -> exchange email + password for a JWT
    GET  /auth/me        -> current user (requires Authorization: Bearer <token>)

Set ORBITGUARD_SECRET in the environment for any real deployment.
"""

import hashlib
import hmac
import os
import re
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import jwt  # PyJWT
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

DB_PATH = Path(__file__).parent / "orbitguard_users.db"
SECRET_KEY = os.environ.get("ORBITGUARD_SECRET", "dev-only-change-me")
ALGORITHM = "HS256"
TOKEN_TTL_MINUTES = 60 * 24
PBKDF2_ITERATIONS = 200_000
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

router = APIRouter(prefix="/auth", tags=["auth"])
_bearer = HTTPBearer(auto_error=False)


# ---------- database ----------

def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)
    return conn


# ---------- password hashing ----------

def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt.hex()}${digest.hex()}"


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


def get_current_user(creds: HTTPAuthorizationCredentials | None = Depends(_bearer)) -> dict:
    """Dependency: use on any endpoint that should require login."""
    if creds is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    try:
        payload = jwt.decode(creds.credentials, SECRET_KEY, algorithms=[ALGORITHM])
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
    return dict(row)


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
def register(body: RegisterRequest):
    email = body.email.strip().lower()
    if not EMAIL_RE.match(email):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Invalid email address")
    conn = _get_conn()
    try:
        try:
            cur = conn.execute(
                "INSERT INTO users (name, email, password_hash, created_at) VALUES (?, ?, ?, ?)",
                (body.name.strip(), email, hash_password(body.password),
                 datetime.now(timezone.utc).isoformat()),
            )
            conn.commit()
        except sqlite3.IntegrityError:
            raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists")
        user_id = cur.lastrowid
    finally:
        conn.close()
    return {
        "access_token": create_token(user_id, email),
        "token_type": "bearer",
        "user": {"id": user_id, "name": body.name.strip(), "email": email},
    }


@router.post("/login")
def login(body: LoginRequest):
    email = body.email.strip().lower()
    conn = _get_conn()
    try:
        row = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    finally:
        conn.close()
    if row is None or not verify_password(body.password, row["password_hash"]):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect email or password")
    return {
        "access_token": create_token(row["id"], row["email"]),
        "token_type": "bearer",
        "user": {"id": row["id"], "name": row["name"], "email": row["email"]},
    }


@router.get("/me")
def me(user: dict = Depends(get_current_user)):
    return user
