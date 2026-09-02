"""
config/settings.py

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
    OPENAI_API_KEY: str = ""
    GROQ_API_KEY: str = ""

    # --- LLM defaults ---
    DEFAULT_LLM_PROVIDER: str = "openai,groq"
    OPENAI_MODEL: str = "gpt-4.1-mini"
    DEFAULT_MODEL: str = "openai/gpt-oss-20b"   # Groq model (fallback)

    # --- WordPress (developer fallback; UI form overrides these per-run) ---
    WP_URL: str = ""
    WP_USERNAME: str = ""
    WP_APPLICATION_PASSWORD: str = ""

    # --- Visual / stock photo ---
    UNSPLASH_API_KEY: str = ""
    DEFAULT_IMAGE_PROVIDER: str = "pollinations"
    DEFAULT_STOCK_PROVIDER: str = "unsplash"

    # --- Pipeline limits ---
    MAX_PRODUCTS: str = "5"         # Default maximum individual product pages per brand

    # --- Cost estimate ---
    USD_IDR_RATE: str = "16300"     # Manual USD->IDR rate used to estimate token cost in Rupiah

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


# ── Product limit helper ───────────────────────────────────────────────────────

_MAX_PRODUCTS_DEFAULT = 5

def get_max_products() -> int:
    """
    Read MAX_PRODUCTS from DB → .env → default (5).
    Returns a valid int >= 1. Falls back to 5 if value missing or non-numeric.
    """
    raw = get_setting("MAX_PRODUCTS")
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return _MAX_PRODUCTS_DEFAULT
    if value < 1:
        return 1
    return value


# ── Token cost estimate helper ─────────────────────────────────────────────
# Estimasi harga per token untuk model OpenAI utama (gpt-4.1-mini).
# Token usage tidak dipisah per-provider, jadi estimasi ini mengasumsikan
# seluruh token dihitung dengan harga OpenAI (Groq hanya fallback jarang terpakai).
PRICE_PER_PROMPT_TOKEN_USD = 0.40 / 1_000_000
PRICE_PER_COMPLETION_TOKEN_USD = 1.60 / 1_000_000


def calc_token_cost(prompt_tokens: int, completion_tokens: int) -> dict:
    """Estimasi biaya token (USD & IDR) berdasarkan harga gpt-4.1-mini dan kurs USD_IDR_RATE."""
    cost_usd = (
        prompt_tokens * PRICE_PER_PROMPT_TOKEN_USD
        + completion_tokens * PRICE_PER_COMPLETION_TOKEN_USD
    )
    try:
        rate = float(get_setting("USD_IDR_RATE") or settings.USD_IDR_RATE)
    except (TypeError, ValueError):
        rate = float(settings.USD_IDR_RATE)
    return {
        "cost_usd": round(cost_usd, 4),
        "cost_idr": round(cost_usd * rate, 0),
    }
