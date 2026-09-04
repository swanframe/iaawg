# -*- coding: utf-8 -*-
"""
db/brand_profiles_store.py

Profil website per-brand untuk Blog Autopost — supaya operator tidak perlu
mengetik ulang belasan field tiap kali generate batch. Cukup pilih dari dropdown.

Disimpan di SQLite yang sama dengan settings (`iaawg_settings.db`), tabel
terpisah `brand_profiles` (bukan key/value seperti `api_settings`, karena ini
data berkolom per-brand).

Catatan kredensial: `wp_app_password` DISIMPAN apa adanya di DB ini. Ini
keputusan sadar — semua site yang dikelola iAAWG adalah subdomain internal
milik perusahaan sendiri (distributor multi-brand), bukan titipan klien, dan
`iaawg_settings.db` sudah di-gitignore sejak awal sehingga tidak pernah ikut
ke repo. Untuk pindah laptop, cukup copy file .db-nya.

Ini BERBEDA dengan `db/blog_drafts_store.py`, yang tetap tidak boleh menyimpan
kredensial apa pun ke `batch.json` — folder draft bisa saja dipindah/di-share
per batch, sedangkan .db tidak.
"""

import sqlite3
from pathlib import Path
from typing import Optional

DB_PATH = Path(__file__).parent.parent / "iaawg_settings.db"

# Kolom yang boleh ditulis lewat API — dipakai create/update sebagai whitelist
# sekaligus urutan render form.
PROFILE_FIELDS = [
    "brand_name",              # wajib, unik (case-insensitive)
    "main_keyword",
    "secondary_keywords",      # comma-separated, apa adanya seperti di form
    "homepage_url",
    "reference_urls",          # newline-separated
    "external_links",          # newline-separated
    "wp_url",
    "wp_username",
    "wp_app_password",
    "llm_chain",
    "n_articles",
    "include_featured_image",
]

SECRET_FIELDS = {"wp_app_password"}


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Buat tabel brand_profiles kalau belum ada. Dipanggil bareng settings_store.init_db()."""
    with _get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS brand_profiles (
                id                     INTEGER PRIMARY KEY AUTOINCREMENT,
                brand_name             TEXT NOT NULL,
                main_keyword           TEXT NOT NULL DEFAULT '',
                secondary_keywords     TEXT NOT NULL DEFAULT '',
                homepage_url           TEXT NOT NULL DEFAULT '',
                reference_urls         TEXT NOT NULL DEFAULT '',
                external_links         TEXT NOT NULL DEFAULT '',
                wp_url                 TEXT NOT NULL DEFAULT '',
                wp_username            TEXT NOT NULL DEFAULT '',
                wp_app_password        TEXT NOT NULL DEFAULT '',
                llm_chain              TEXT NOT NULL DEFAULT 'openai,groq',
                n_articles             TEXT NOT NULL DEFAULT '3',
                include_featured_image TEXT NOT NULL DEFAULT 'yes',
                created_at             TEXT DEFAULT (datetime('now')),
                updated_at             TEXT DEFAULT (datetime('now'))
            )
        """)
        # Unik case-insensitive supaya "Zecurion" dan "zecurion" tidak jadi 2 profil.
        conn.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_brand_profiles_name
            ON brand_profiles (LOWER(brand_name))
        """)
        conn.commit()


def _row_to_dict(row: sqlite3.Row) -> dict:
    return {k: row[k] for k in row.keys()}


def _strip_secrets(profile: dict) -> dict:
    """Ganti nilai rahasia dengan flag boolean has_<field> untuk dikirim ke browser."""
    for key in SECRET_FIELDS:
        profile[f"has_{key}"] = bool(profile.get(key))
        profile[key] = ""
    return profile


def _clean(payload: dict) -> dict:
    """Ambil hanya field yang di-whitelist, buang spasi pinggir."""
    out = {}
    for key in PROFILE_FIELDS:
        if key in payload and payload[key] is not None:
            out[key] = str(payload[key]).strip()
    return out


def list_profiles(include_secrets: bool = False) -> list[dict]:
    """Semua profil, urut nama. Password dikosongkan kecuali diminta eksplisit."""
    conn = _get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM brand_profiles ORDER BY LOWER(brand_name) ASC"
        ).fetchall()
        result = [_row_to_dict(r) for r in rows]
    finally:
        conn.close()
    if not include_secrets:
        result = [_strip_secrets(p) for p in result]
    return result


def get_profile(profile_id: int, include_secrets: bool = False) -> Optional[dict]:
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM brand_profiles WHERE id = ?", (profile_id,)
        ).fetchone()
    finally:
        conn.close()
    if not row:
        return None
    profile = _row_to_dict(row)
    return profile if include_secrets else _strip_secrets(profile)


def get_profile_by_brand(brand_name: str, include_secrets: bool = False) -> Optional[dict]:
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM brand_profiles WHERE LOWER(brand_name) = LOWER(?)",
            ((brand_name or "").strip(),),
        ).fetchone()
    finally:
        conn.close()
    if not row:
        return None
    profile = _row_to_dict(row)
    return profile if include_secrets else _strip_secrets(profile)


def create_profile(payload: dict) -> dict:
    """Simpan profil baru. Raise ValueError kalau nama kosong / sudah dipakai."""
    data = _clean(payload)
    brand = data.get("brand_name", "")
    if not brand:
        raise ValueError("Nama brand wajib diisi.")
    if get_profile_by_brand(brand):
        raise ValueError(f"Profil untuk brand '{brand}' sudah ada — edit yang existing saja.")

    cols = list(data.keys())
    placeholders = ",".join("?" * len(cols))
    conn = _get_conn()
    try:
        cur = conn.execute(
            f"INSERT INTO brand_profiles ({','.join(cols)}) VALUES ({placeholders})",
            [data[c] for c in cols],
        )
        conn.commit()
        new_id = cur.lastrowid
    finally:
        conn.close()
    return get_profile(new_id)


def update_profile(profile_id: int, payload: dict) -> Optional[dict]:
    """
    Update sebagian field. Field yang tidak dikirim tidak disentuh.

    Khusus `wp_app_password`: string kosong berarti "jangan diubah", bukan
    "hapus" — supaya form edit bisa menampilkan field password kosong tanpa
    menghapus password yang sudah tersimpan.
    """
    data = _clean(payload)
    if not data:
        return get_profile(profile_id)

    if "brand_name" in data:
        if not data["brand_name"]:
            raise ValueError("Nama brand wajib diisi.")
        existing = get_profile_by_brand(data["brand_name"])
        if existing and existing["id"] != profile_id:
            raise ValueError(f"Profil untuk brand '{data['brand_name']}' sudah ada.")

    for key in SECRET_FIELDS:
        if key in data and not data[key]:
            del data[key]

    if not data:
        return get_profile(profile_id)

    assignments = ", ".join(f"{c} = ?" for c in data.keys())
    conn = _get_conn()
    try:
        cur = conn.execute(
            f"UPDATE brand_profiles SET {assignments}, updated_at = datetime('now') WHERE id = ?",
            [*data.values(), profile_id],
        )
        conn.commit()
        if cur.rowcount == 0:
            return None
    finally:
        conn.close()
    return get_profile(profile_id)


def upsert_by_brand(payload: dict) -> dict:
    """
    Dipakai checkbox "Simpan sebagai profil" di form Blog — buat kalau brand
    belum terdaftar, update kalau sudah, tanpa operator perlu tahu bedanya.
    """
    brand = (payload.get("brand_name") or "").strip()
    if not brand:
        raise ValueError("Nama brand wajib diisi.")
    existing = get_profile_by_brand(brand)
    if existing:
        return update_profile(existing["id"], payload)
    return create_profile(payload)


def delete_profile(profile_id: int) -> bool:
    conn = _get_conn()
    try:
        cur = conn.execute("DELETE FROM brand_profiles WHERE id = ?", (profile_id,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()
