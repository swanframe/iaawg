"""
db/settings_store.py

SQLite-backed settings store for iAAWG.
DB takes priority over .env — saving a value here overrides it without
touching the .env file. Clearing a key from DB restores the .env fallback.

Uses Python's built-in sqlite3 (no extra dependencies needed).
"""

import sqlite3
from pathlib import Path
from typing import Optional

# Store the DB next to the project root (same level as .env)
DB_PATH = Path(__file__).parent.parent / "iaawg_settings.db"

# All keys that can be managed through the UI
SETTINGS_KEYS = [
    "GROQ_API_KEY",
    "CEREBRAS_API_KEY",
    "GITHUB_TOKEN",
    "UNSPLASH_API_KEY",
    "DEFAULT_LLM_PROVIDER",
    "DEFAULT_MODEL",
    "CEREBRAS_MODEL",
    "GITHUB_MODEL",
]

# Keys that are sensitive and should be masked in the UI
SECRET_KEYS = {"GROQ_API_KEY", "CEREBRAS_API_KEY", "GITHUB_TOKEN", "UNSPLASH_API_KEY"}


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Create the settings table if it doesn't already exist. Call this at app startup."""
    with _get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS api_settings (
                key        TEXT PRIMARY KEY,
                value      TEXT NOT NULL DEFAULT '',
                updated_at TEXT DEFAULT (datetime('now'))
            )
        """)
        conn.commit()


def get_setting(key: str) -> Optional[str]:
    """
    Return the stored value for key, or None if not set / empty.
    Returns None (not empty string) so callers can chain with a .env fallback.
    """
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT value FROM api_settings WHERE key = ?", (key,)
        ).fetchone()
        value = row["value"] if row else None
        return value if value else None
    finally:
        conn.close()


def set_setting(key: str, value: str) -> None:
    """Upsert a setting. Passing an empty string is treated as a delete."""
    if not value or not value.strip():
        delete_setting(key)
        return
    conn = _get_conn()
    try:
        conn.execute("""
            INSERT INTO api_settings (key, value, updated_at)
            VALUES (?, ?, datetime('now'))
            ON CONFLICT(key) DO UPDATE SET
                value      = excluded.value,
                updated_at = datetime('now')
        """, (key, value.strip()))
        conn.commit()
    finally:
        conn.close()


def delete_setting(key: str) -> None:
    """Remove a key from DB so the .env fallback takes effect again."""
    conn = _get_conn()
    try:
        conn.execute("DELETE FROM api_settings WHERE key = ?", (key,))
        conn.commit()
    finally:
        conn.close()


def get_all_settings() -> dict[str, str]:
    """Return all stored settings as {key: value}. Only keys in SETTINGS_KEYS."""
    conn = _get_conn()
    try:
        placeholders = ",".join("?" * len(SETTINGS_KEYS))
        rows = conn.execute(
            f"SELECT key, value FROM api_settings WHERE key IN ({placeholders})",
            SETTINGS_KEYS,
        ).fetchall()
        return {row["key"]: row["value"] for row in rows if row["value"]}
    finally:
        conn.close()


def mask_value(value: str) -> str:
    """Show only the last 4 characters; everything else is replaced with bullets."""
    if not value:
        return ""
    if len(value) <= 6:
        return "••••••"
    return "•" * (len(value) - 4) + value[-4:]
