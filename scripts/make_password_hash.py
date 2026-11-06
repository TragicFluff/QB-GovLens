"""Change the app's sign-in username and password.

Usage (from the app folder, with the virtual environment active):
    python scripts/make_password_hash.py

You are asked for a new username (press Enter to keep the current one) and a new
password (typed twice, hidden). The script then updates govlens/auth.py in place.
Only a salted hash of the password is written; the plaintext is never saved.
Restart the app afterwards, and push govlens/auth.py to GitHub to update a deployed app.
"""

from __future__ import annotations

from getpass import getpass
from pathlib import Path
import re
import secrets
import sys

APP_DIR = Path(__file__).resolve().parents[1]
AUTH_FILE = APP_DIR / "govlens" / "auth.py"
sys.path.insert(0, str(APP_DIR))
from govlens.auth import USERNAME, hash_password  # noqa: E402

USERNAME_RULE = re.compile(r"[a-z0-9._-]{3,40}")


def update_auth_file(path: Path, username: str, password: str) -> None:
    """Rewrite USERNAME, PASSWORD_SALT and PASSWORD_HASH in auth.py, or change nothing."""
    username = username.strip().lower()
    if not USERNAME_RULE.fullmatch(username):
        raise ValueError("Username must be 3-40 characters: letters, digits, dot, dash or underscore.")
    if len(password) < 10:
        raise ValueError("Password must be at least 10 characters.")
    salt = secrets.token_hex(16)
    values = {"USERNAME": username, "PASSWORD_SALT": salt, "PASSWORD_HASH": hash_password(password, salt)}
    text = path.read_text(encoding="utf-8")
    for name, value in values.items():
        text, count = re.subn(rf'^{name} = "[^"]*"$', f'{name} = "{value}"', text, flags=re.MULTILINE)
        if count != 1:
            raise ValueError(f"Could not find the {name} line in {path}; nothing was changed.")
    path.write_text(text, encoding="utf-8")


def main() -> None:
    username = input(f"New username (Enter keeps '{USERNAME}'): ").strip() or USERNAME
    password = getpass("New password (hidden, at least 10 characters): ")
    if password != getpass("Repeat new password: "):
        sys.exit("Passwords do not match. Nothing was changed.")
    try:
        update_auth_file(AUTH_FILE, username, password)
    except ValueError as exc:
        sys.exit(f"{exc} Nothing was changed.")
    print(f"Updated {AUTH_FILE}. Sign in with username '{username.lower()}' and your new password.")
    print("Restart the app (and push govlens/auth.py to GitHub if the app is deployed).")


if __name__ == "__main__":
    main()
