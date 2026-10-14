"""Create or change the dashboard login. Run from backend/:  .venv\\Scripts\\python -m app.set_login

Writes DASHBOARD_USERNAME, DASHBOARD_PASSWORD_SALT and DASHBOARD_PASSWORD_HASH into the project's
.env, leaving every other line untouched. The password itself is never stored.
"""
import getpass
import secrets
from pathlib import Path

from .auth import hash_password
from .config import ROOT

MIN_PASSWORD_LENGTH = 8
OBSOLETE_KEYS = {"DASHBOARD_PASSWORD"}  # plain-text password used by an earlier version


def update_env_file(path: Path, updates: dict[str, str], remove: set[str] = frozenset()) -> None:
    lines = path.read_text(encoding="utf-8-sig").splitlines() if path.exists() else []
    out, written = [], set()
    for line in lines:
        name = line.split("=", 1)[0].strip() if "=" in line and not line.lstrip().startswith("#") else None
        if name in remove:
            continue
        if name in updates:
            if name not in written:
                out.append(f"{name}={updates[name]}")
                written.add(name)
            continue
        out.append(line)
    out += [f"{name}={value}" for name, value in updates.items() if name not in written]
    path.write_text("\n".join(out) + "\n", encoding="utf-8")


def main() -> None:
    print("Set the dashboard login (saved to .env as a salted hash).")
    username = ""
    while not username or any(c.isspace() for c in username):
        username = input("Username (no spaces): ").strip()
    while True:
        password = getpass.getpass(f"Password (at least {MIN_PASSWORD_LENGTH} characters): ")
        if len(password) < MIN_PASSWORD_LENGTH:
            print("Too short.")
        elif getpass.getpass("Repeat password: ") != password:
            print("Passwords don't match.")
        else:
            break
    salt = secrets.token_hex(16)
    update_env_file(ROOT / ".env", {
        "DASHBOARD_USERNAME": username,
        "DASHBOARD_PASSWORD_SALT": salt,
        "DASHBOARD_PASSWORD_HASH": hash_password(password, salt),
    }, remove=OBSOLETE_KEYS)
    print("Login saved. Restart the dashboard (start.bat) for it to take effect.")


if __name__ == "__main__":
    main()
