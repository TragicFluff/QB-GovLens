"""API key lookup: environment variable, then local .env file, then Streamlit secrets."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Callable

APP_DIR = Path(__file__).resolve().parents[1]


def _read_dotenv(path: Path, name: str) -> str:
    try:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    except OSError:
        return ""
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip().removeprefix("export ").strip()
        if key == name:
            return value.strip().strip('"').strip("'")
    return ""


def get_api_key(secrets_getter: Callable[[str], str] | None = None,
                name: str = "OPENAI_API_KEY", dotenv: Path = APP_DIR / ".env") -> str:
    key = os.getenv(name, "").strip()
    if key:
        return key
    key = _read_dotenv(dotenv, name)
    if key:
        return key
    if secrets_getter is not None:
        try:
            return str(secrets_getter(name) or "").strip()
        except Exception:
            return ""
    return ""
