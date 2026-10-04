"""Password hashing, signed session tokens, and the user table.

Uses PBKDF2-SHA256 from the standard library (no extra install). Tokens are
HMAC-signed, expire after TOKEN_TTL seconds, and carry user id + role.
"""
import base64
import hashlib
import hmac
import json
import os
import secrets
import time

from db import connect

TOKEN_TTL = int(os.environ.get("HF_TOKEN_TTL", 8 * 3600))   # one shift
PBKDF2_ROUNDS = 200_000
# Set HF_SECRET in production. Without it a random key is made per process,
# so tokens stop working after a restart (safe default).
SECRET = os.environ.get("HF_SECRET", "").encode() or secrets.token_bytes(32)


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PBKDF2_ROUNDS)
    return f"pbkdf2${PBKDF2_ROUNDS}${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, rounds, salt, dk = stored.split("$")
        test = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(rounds))
        return hmac.compare_digest(test.hex(), dk)
    except (ValueError, TypeError):
        return False


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def make_token(user_id: int, username: str, role: str, now: float | None = None) -> str:
    payload = {"uid": user_id, "u": username, "r": role, "exp": int((now or time.time()) + TOKEN_TTL)}
    body = _b64(json.dumps(payload, separators=(",", ":")).encode())
    sig = _b64(hmac.new(SECRET, body.encode(), hashlib.sha256).digest())
    return f"{body}.{sig}"


def read_token(token: str, now: float | None = None) -> dict | None:
    try:
        body, sig = token.split(".")
        good = _b64(hmac.new(SECRET, body.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(sig, good):
            return None
        payload = json.loads(_unb64(body))
        if payload["exp"] < (now or time.time()):
            return None
        return payload
    except (ValueError, KeyError, json.JSONDecodeError):
        return None


def create_user(username: str, password: str, role: str, path=None) -> int:
    if role not in ("nurse", "manager"):
        raise ValueError("role must be nurse or manager")
    if len(password) < 8:
        raise ValueError("password must be at least 8 characters")
    with connect(path) as con:
        cur = con.execute("INSERT INTO user (username, password_hash, role) VALUES (?,?,?)",
                          (username, hash_password(password), role))
        return cur.lastrowid


def authenticate(username: str, password: str, path=None) -> dict | None:
    with connect(path) as con:
        row = con.execute("SELECT * FROM user WHERE username = ?", (username,)).fetchone()
    if row is None:
        hash_password(password)  # spend the same time so usernames can't be probed by timing
        return None
    if not verify_password(password, row["password_hash"]):
        return None
    return {"user_id": row["user_id"], "username": row["username"], "role": row["role"]}


def seed_demo_users(path=None) -> list[str]:
    """Create demo accounts if the user table is empty. Passwords come from env or defaults."""
    with connect(path) as con:
        if con.execute("SELECT COUNT(*) FROM user").fetchone()[0]:
            return []
    nurse_pw = os.environ.get("HF_NURSE_PASSWORD", "nurse-demo-1")
    mgr_pw = os.environ.get("HF_MANAGER_PASSWORD", "manager-demo-1")
    create_user("nurse", nurse_pw, "nurse", path)
    create_user("manager", mgr_pw, "manager", path)
    return ["nurse", "manager"]
