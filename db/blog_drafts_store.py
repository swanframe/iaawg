# -*- coding: utf-8 -*-
"""
db/blog_drafts_store.py

File-based persistence for Blog Autopost drafts — same convention as
`output/<brand>/content/*.json` used by the website pipeline (not SQLite,
unlike db/settings_store.py, because this data is per-brand batch output,
not global key/value config).

Layout on disk:
    output/<brand>/blog_drafts/<batch_id>/batch.json
    output/<brand>/blog_drafts/<batch_id>/images/<file>   (custom uploads)

WP credentials are never written here (see CLAUDE.md-adjacent design note in
the review/publish flow) — operator re-enters them at publish time.
"""

import json
import re
from pathlib import Path
from typing import Optional

OUTPUT_ROOT = Path(__file__).parent.parent / "output"


def slugify_brand(brand: str) -> str:
    """Sama seperti pola brand slug dipakai pipeline website (folder output/<brand>/)."""
    slug = (brand or "").strip().lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug).strip("-")
    return slug or "brand"


def batch_dir(brand: str, batch_id: str) -> Path:
    return OUTPUT_ROOT / slugify_brand(brand) / "blog_drafts" / batch_id


def images_dir(brand: str, batch_id: str) -> Path:
    return batch_dir(brand, batch_id) / "images"


def save_batch(brand: str, batch_id: str, data: dict) -> None:
    d = batch_dir(brand, batch_id)
    d.mkdir(parents=True, exist_ok=True)
    (d / "batch.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def load_batch(brand: str, batch_id: str) -> Optional[dict]:
    f = batch_dir(brand, batch_id) / "batch.json"
    if not f.exists():
        return None
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except Exception:
        return None


def list_batches() -> list[dict]:
    """
    Scan output/*/blog_drafts/*/batch.json — return ringkasan tiap batch
    (bukan full artikel) untuk halaman /blog/drafts.
    """
    results: list[dict] = []
    if not OUTPUT_ROOT.exists():
        return results
    for batch_json in OUTPUT_ROOT.glob("*/blog_drafts/*/batch.json"):
        try:
            data = json.loads(batch_json.read_text(encoding="utf-8"))
        except Exception:
            continue
        articles = data.get("articles", [])
        results.append({
            "batch_id": data.get("batch_id", batch_json.parent.name),
            "brand_name": data.get("brand_name", ""),
            "brand_slug": batch_json.parent.parent.parent.name,
            "main_keyword": data.get("main_keyword", ""),
            "created_at": data.get("created_at", ""),
            "n_articles": len(articles),
            "n_published": sum(1 for a in articles if a.get("status") == "published"),
        })
    results.sort(key=lambda b: b.get("created_at", ""), reverse=True)
    return results


def update_article(brand: str, batch_id: str, article_id: str, **fields) -> Optional[dict]:
    """Update field-field artikel tertentu di batch.json. Return artikel yang sudah diupdate, atau None kalau tidak ketemu."""
    data = load_batch(brand, batch_id)
    if not data:
        return None
    for article in data.get("articles", []):
        if article.get("id") == article_id:
            article.update(fields)
            save_batch(brand, batch_id, data)
            return article
    return None


def find_batch_brand(batch_id: str) -> Optional[str]:
    """Cari nama brand (bukan slug) dari batch_id — dipakai endpoint yang cuma dapat batch_id di URL."""
    if not OUTPUT_ROOT.exists():
        return None
    for batch_json in OUTPUT_ROOT.glob(f"*/blog_drafts/{batch_id}/batch.json"):
        try:
            data = json.loads(batch_json.read_text(encoding="utf-8"))
            return data.get("brand_name", "")
        except Exception:
            continue
    return None
