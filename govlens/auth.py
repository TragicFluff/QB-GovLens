"""Hardcoded single-user login (bootcamp minimum scope for an individual project).

The username and a salted PBKDF2 hash of the password are stored in code, so the
plaintext password is never committed. To change the username and/or password, run
    python scripts/make_password_hash.py
from the app folder; it rewrites the three constants below for you.
"""

from __future__ import annotations

import hashlib
import hmac

USERNAME = "user1"
PASSWORD_SALT = "18fbb8be7540e8e656854dd3a0ef070e"
PASSWORD_HASH = "cd1afd2e14e0fcc07cb85a18cd455ee13f2c009e2e15b42270cda0b8b15c2175"
ITERATIONS = 200_000


def hash_password(password: str, salt_hex: str, iterations: int = ITERATIONS) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), iterations).hex()


def verify(username: str, password: str) -> bool:
    user_ok = hmac.compare_digest(username.strip().lower(), USERNAME.strip().lower())
    pass_ok = hmac.compare_digest(hash_password(password, PASSWORD_SALT), PASSWORD_HASH)
    return user_ok and pass_ok


def login_gate(st) -> bool:
    """Render the login form until the user signs in; returns True once authenticated."""
    if st.session_state.get("authenticated"):
        return True
    st.title("QB GovLens")
    st.caption("Governance-by-design review prototype for QuickBuy@SGov agency administrators")
    with st.form("login"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Sign in", type="primary")
    if submitted:
        if verify(username, password):
            st.session_state["authenticated"] = True
            st.rerun()
        else:
            st.error("Incorrect username or password.")
    st.caption("Educational prototype. Access is limited to bootcamp assessors and the project owner.")
    return False
