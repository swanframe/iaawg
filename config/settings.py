"""
config/settings.py  (replacement)

Priority order for every setting:
  1. DB (iaawg_settings.db)  — set via the web Settings page
  2. .env file               — existing behaviour, untouched fallback
  3. Empty string            — safe default so app doesn't crash

Use  get_setting("KEY_NAME")  everywhere instead of  settings.KEY_NAME
so the DB override is always respected.
"""

import os
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # --- LLM providers ---
    GROQ_API_KEY: str = ""
    CEREBRAS_API_KEY: str = ""
    GITHUB_TOKEN: str = ""          # PAT for GitHub Models

    # --- LLM defaults ---
    DEFAULT_LLM_PROVIDER: str = "groq,cerebras,github"
    DEFAULT_MODEL: str = "llama-3.1-8b-instant"
    CEREBRAS_MODEL: str = "gemma-4-31b"
    GITHUB_MODEL: str = "gpt-4o-mini"

    # --- WordPress (developer fallback; UI form overrides these per-run) ---
    WP_URL: str = ""
    WP_USERNAME: str = ""
    WP_APPLICATION_PASSWORD: str = ""

    # --- Visual / stock photo ---
    UNSPLASH_API_KEY: str = ""
    DEFAULT_IMAGE_PROVIDER: str = "pollinations"
    DEFAULT_STOCK_PROVIDER: str = "unsplash"

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )


# Module-level singleton loaded from .env at startup (original behaviour)
settings = Settings()


def get_setting(key: str) -> str:
    """
    Resolve the effective value for *key* using DB → .env priority.

    This is a lazy import to avoid a circular-import at module load time
    (db.settings_store imports nothing from config).

    Usage (replaces  settings.GROQ_API_KEY  in provider __init__ methods):

        from config.settings import get_setting
        api_key = get_setting("GROQ_API_KEY")
    """
    try:
        from db.settings_store import get_setting as _db_get
        db_value = _db_get(key)
        if db_value:
            return db_value
    except Exception:
        # If the DB isn't initialised yet (e.g. first-ever startup before
        # init_db() runs), fall through silently to the .env value.
        pass

    # Fallback: pydantic Settings loaded from .env
    return getattr(settings, key, "") or ""