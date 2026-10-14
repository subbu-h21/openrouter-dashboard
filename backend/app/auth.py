"""Single-user login (username + password) with an HMAC-signed session cookie."""
import base64
import hashlib
import hmac
import json
import threading
import time

from fastapi import HTTPException, Request

from . import config

# The login lives in .env (see config.py); the password only as a salted hash.
PBKDF2_ITERATIONS = 200_000

COOKIE_NAME = "ord_session"
FAIL_WINDOW = 15 * 60
MAX_FAILS_PER_CLIENT = 5
MAX_FAILS_GLOBAL = 30

_fails: dict[str, list[float]] = {}
_fails_lock = threading.Lock()


def _signing_key() -> bytes:
    # Mixing in the login means changing it invalidates every existing session.
    login = f"{config.DASHBOARD_USERNAME}:{config.PASSWORD_HASH}"
    return hashlib.sha256(config.session_secret() + b"\x00" + login.encode()).digest()


def _sign(payload: bytes) -> str:
    return base64.urlsafe_b64encode(hmac.new(_signing_key(), payload, hashlib.sha256).digest()).decode().rstrip("=")


def create_token() -> str:
    payload = json.dumps({"exp": int(time.time()) + config.SESSION_DAYS * 86400}).encode()
    return base64.urlsafe_b64encode(payload).decode().rstrip("=") + "." + _sign(payload)


def verify_token(token: str | None) -> bool:
    if not token or "." not in token:
        return False
    body, signature = token.rsplit(".", 1)
    try:
        payload = base64.urlsafe_b64decode(body + "=" * (-len(body) % 4))
    except ValueError:
        return False
    if not hmac.compare_digest(_sign(payload), signature):
        return False
    try:
        return json.loads(payload)["exp"] > time.time()
    except (ValueError, KeyError, TypeError):
        return False


def hash_password(password: str, salt_hex: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), PBKDF2_ITERATIONS).hex()


def check_credentials(username: str, password: str) -> bool:
    password_ok = hmac.compare_digest(hash_password(password, config.PASSWORD_SALT), config.PASSWORD_HASH.lower())
    username_ok = hmac.compare_digest(username.strip().encode(), config.DASHBOARD_USERNAME.encode())
    return password_ok and username_ok


def client_id(request: Request) -> str:
    # Behind a tunnel every request comes from 127.0.0.1, so prefer the forwarded client address.
    # These headers can be spoofed, which is why there is also a global failure cap.
    for header in ("cf-connecting-ip", "x-forwarded-for"):
        value = request.headers.get(header)
        if value:
            return value.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _recent(times: list[float], now: float) -> list[float]:
    return [t for t in times if now - t < FAIL_WINDOW]


def login_allowed(client: str) -> bool:
    now = time.time()
    with _fails_lock:
        for key in list(_fails):
            _fails[key] = _recent(_fails[key], now)
            if not _fails[key]:
                del _fails[key]
        total = sum(len(v) for v in _fails.values())
        return len(_fails.get(client, [])) < MAX_FAILS_PER_CLIENT and total < MAX_FAILS_GLOBAL


def record_failure(client: str) -> None:
    with _fails_lock:
        _fails.setdefault(client, []).append(time.time())


def require_auth(request: Request) -> None:
    if not verify_token(request.cookies.get(COOKIE_NAME)):
        raise HTTPException(status_code=401, detail="Not logged in")
