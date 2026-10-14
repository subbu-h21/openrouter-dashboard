"""Settings loaded from the project-root .env file (real environment variables win)."""
import os
import secrets
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "dashboard.db"
FRONTEND_DIST = ROOT / "frontend" / "dist"


def _read_env_file(path: Path) -> dict:
    values = {}
    if not path.exists():
        return values
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[name.strip()] = value
    return values


_file_env = _read_env_file(ROOT / ".env")


def _get(name: str, default: str | None = None) -> str | None:
    value = os.environ.get(name) or _file_env.get(name)
    return value if value else default


MANAGEMENT_KEY = _get("OPENROUTER_MANAGEMENT_KEY")
# Dashboard login. The password is stored only as a salted PBKDF2 hash; create or change it
# with `python -m app.set_login` (run from backend/), which setup.bat does for you.
DASHBOARD_USERNAME = _get("DASHBOARD_USERNAME")
PASSWORD_SALT = _get("DASHBOARD_PASSWORD_SALT")
PASSWORD_HASH = _get("DASHBOARD_PASSWORD_HASH")
SYNC_INTERVAL_SECONDS = int(_get("SYNC_INTERVAL_SECONDS", "300"))
SESSION_DAYS = int(_get("SESSION_DAYS", "7"))


def validate() -> None:
    if not MANAGEMENT_KEY:
        raise RuntimeError("Missing required setting in .env: OPENROUTER_MANAGEMENT_KEY")
    if not (DASHBOARD_USERNAME and PASSWORD_SALT and PASSWORD_HASH):
        raise RuntimeError("No dashboard login in .env. Run setup.bat, or `python -m app.set_login` from backend/.")
    try:
        bytes.fromhex(PASSWORD_SALT)
        bytes.fromhex(PASSWORD_HASH)
    except ValueError:
        raise RuntimeError("DASHBOARD_PASSWORD_SALT / DASHBOARD_PASSWORD_HASH in .env are not valid; "
                           "run `python -m app.set_login` from backend/ to recreate them.") from None


def session_secret() -> bytes:
    """SESSION_SECRET from .env, else a random secret persisted in data/."""
    configured = _get("SESSION_SECRET")
    if configured:
        return configured.encode()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = DATA_DIR / ".session_secret"
    if not path.exists():
        path.write_text(secrets.token_hex(32), encoding="utf-8")
    return path.read_text(encoding="utf-8").strip().encode()
