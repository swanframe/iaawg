# -*- coding: utf-8 -*-
"""
Blog deployment helper — wrapper di atas WordPressClient.

Kenapa modul terpisah, bukan patch di wordpress/client.py:
  - `create_post()` existing sengaja "unchanged from original" (lihat komentar di
    wp_client.py). Menambah parameter langsung di sana berisiko regresi.
  - Semua concern khusus blog (kategori, tag, featured image, scheduled date)
    diisolasi di sini supaya perubahan model blog di masa depan tidak menyentuh
    pipeline website.

Utility di modul ini:
  - ensure_category / ensure_tags : get-or-create term via REST
  - upload_featured_image         : upload media dan return numeric ID
                                    (upload_media existing return URL string)
  - create_blog_post              : create post lengkap (featured, kategori,
                                    tag, slug, meta_desc, scheduled date)
  - deploy_blog_batch             : orkestrasi batch dengan schedule staggered
                                    dan fetch featured image otomatis
"""

import httpx
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from wordpress.client import WordPressClient
from content.blog_generator import _build_cta_block


# ─────────────────────────────────────────────────────────────────────────────
# Taxonomy helpers — get or create category / tag
# ─────────────────────────────────────────────────────────────────────────────

async def _get_or_create_term(
    client: WordPressClient,
    taxonomy: str,   # "categories" atau "tags"
    name: str,
) -> Optional[int]:
    """Return term ID kalau sudah ada, kalau tidak buat baru. Return None kalau gagal."""
    endpoint = f"{client.base_url}/wp-json/wp/v2/{taxonomy}"
    async with httpx.AsyncClient(timeout=30.0) as http:
        # 1) Cari yang sudah ada (case-insensitive exact match)
        try:
            resp = await http.get(
                endpoint,
                params={"search": name, "per_page": 20},
                headers=client.headers,
            )
            if resp.status_code == 200:
                for item in resp.json():
                    if item.get("name", "").strip().lower() == name.strip().lower():
                        return item.get("id")
        except Exception as e:
            print(f"[Blog Deploy Warning] Gagal cari {taxonomy} '{name}': {e}")

        # 2) Kalau tidak ada, create
        try:
            resp = await http.post(
                endpoint,
                json={"name": name},
                headers=client.headers,
            )
            if resp.status_code in [200, 201]:
                new_id = resp.json().get("id")
                print(f"[Blog Deploy] {taxonomy.rstrip('s').capitalize()} baru dibuat: '{name}' → id {new_id}")
                return new_id
            # 400 "term_exists" bisa terjadi kalau search miss karena slug bentrok
            if resp.status_code == 400:
                try:
                    data = resp.json()
                    if data.get("code") == "term_exists":
                        existing_id = data.get("data", {}).get("term_id")
                        if existing_id:
                            return int(existing_id)
                except Exception:
                    pass
            print(f"[Blog Deploy Warning] Gagal create {taxonomy} '{name}': "
                  f"{resp.status_code} {resp.text[:200]}")
        except Exception as e:
            print(f"[Blog Deploy Warning] Kendala jaringan saat create {taxonomy} '{name}': {e}")

    return None


async def ensure_category(client: WordPressClient, name: str) -> Optional[int]:
    """Return category ID (create kalau belum ada)."""
    return await _get_or_create_term(client, "categories", name)


async def ensure_tags(client: WordPressClient, names: list[str]) -> list[int]:
    """Return list tag IDs (create yang belum ada). Skip nama kosong."""
    ids: list[int] = []
    for n in names or []:
        if not n or not str(n).strip():
            continue
        tid = await _get_or_create_term(client, "tags", str(n).strip())
        if tid:
            ids.append(tid)
    return ids


# ─────────────────────────────────────────────────────────────────────────────
# Media — upload dan return ID (upload_media existing hanya return URL)
# ─────────────────────────────────────────────────────────────────────────────

async def upload_featured_image(
    client: WordPressClient,
    file_name: str,
    file_bytes: bytes,
    mime_type: str = "image/jpeg",
    alt_text: str = "",
) -> Optional[int]:
    """
    Upload media dan kembalikan attachment ID (bukan URL).
    Dibutuhkan karena WP REST field `featured_media` minta numeric ID.

    `alt_text` (kalau diisi) di-PATCH setelah upload — dibutuhkan supaya
    check Yoast "Keyphrase in image alt attributes" bisa hijau. `alt_text`
    adalah field REST native WordPress core untuk attachment (bukan meta key
    custom), jadi tidak butuh plugin bridge tambahan seperti field Yoast lain.
    """
    if not file_bytes:
        return None

    endpoint = f"{client.base_url}/wp-json/wp/v2/media"
    headers = {
        "Authorization":       client.headers["Authorization"],
        "Content-Disposition": f'attachment; filename="{file_name}"',
        "Content-Type":        mime_type,
    }

    async with httpx.AsyncClient(timeout=60.0) as http:
        try:
            resp = await http.post(endpoint, content=file_bytes, headers=headers)
            if resp.status_code in [200, 201]:
                media_id = resp.json().get("id")
                print(f"[Blog Deploy] Featured image di-upload: '{file_name}' → id {media_id}")

                if media_id and alt_text:
                    try:
                        alt_resp = await http.post(
                            f"{endpoint}/{media_id}",
                            json={"alt_text": alt_text},
                            headers=client.headers,
                        )
                        if alt_resp.status_code not in [200, 201]:
                            print(f"[Blog Deploy Warning] Set alt_text gagal: "
                                  f"{alt_resp.status_code} {alt_resp.text[:200]}")
                    except Exception as e:
                        print(f"[Blog Deploy Warning] Kendala set alt_text: {e}")

                return media_id
            print(f"[Blog Deploy Warning] Upload media gagal: {resp.status_code} {resp.text[:200]}")
        except Exception as e:
            print(f"[Blog Deploy Warning] Kendala upload media: {e}")
    return None


async def _download_bytes(url: str, timeout: float = 30.0) -> Optional[bytes]:
    """Fetch gambar dari URL publik (Unsplash, Pollinations, dll)."""
    if not url:
        return None
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as http:
        try:
            resp = await http.get(url)
            if resp.status_code == 200:
                return resp.content
            print(f"[Blog Deploy Warning] Download image {url} → status {resp.status_code}")
        except Exception as e:
            print(f"[Blog Deploy Warning] Kendala download image: {e}")
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Create post (extended)
# ─────────────────────────────────────────────────────────────────────────────

def _sanitize_slug(slug: str, fallback: str = "post") -> str:
    """Pastikan slug hanya [a-z0-9-] dan tidak kosong."""
    slug = (slug or "").strip().lower()
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"[\s_-]+", "-", slug).strip("-")
    slug = slug[:60].rstrip("-")
    return slug or fallback


async def create_blog_post(
    client: WordPressClient,
    title: str,
    content: str,
    excerpt: str = "",
    slug: str = "",
    meta_description: str = "",
    featured_media: Optional[int] = None,
    category_ids: Optional[list[int]] = None,
    tag_ids: Optional[list[int]] = None,
    publish_date: Optional[datetime] = None,
    focus_keyphrase: str = "",
    seo_title: str = "",
) -> dict:
    """
    Extended create_post yang support featured image, kategori, tag, slug,
    dan scheduled publishing.

    `publish_date` di masa depan → status "future" (WordPress native scheduler
    akan publish otomatis pada waktu tersebut).
    `publish_date` None / masa lalu → status "publish" langsung.

    `focus_keyphrase` dan `seo_title` dikirim ke Yoast (via meta — Yoast versi
    terbaru sudah mendaftarkan field ini sendiri untuk REST, terverifikasi
    2026-09; `iaawg-yoast-rest-bridge.php` disimpan sebagai fallback opsional
    kalau ada instalasi Yoast lain yang belum) dan ke AIOSEO (via
    `aioseo_meta_data`, didukung native tanpa plugin tambahan — lihat docs
    aioseo.com).
    """
    endpoint = f"{client.base_url}/wp-json/wp/v2/posts"

    payload: dict = {
        "title":   title,
        "content": content,
        "excerpt": excerpt or meta_description or "",
    }

    if slug:
        payload["slug"] = _sanitize_slug(slug, fallback=_sanitize_slug(title))
    if featured_media:
        payload["featured_media"] = featured_media
    if category_ids:
        payload["categories"] = category_ids
    if tag_ids:
        payload["tags"] = tag_ids

    now = datetime.now()
    if publish_date and publish_date > now:
        payload["status"] = "future"
        payload["date"] = publish_date.strftime("%Y-%m-%dT%H:%M:%S")
    else:
        payload["status"] = "publish"

    # Meta Yoast — Yoast versi terbaru sudah mendaftarkan field ini sendiri
    # untuk REST (terverifikasi 2026-09). Kalau instalasi Yoast lain ternyata
    # belum, field ini akan dibuang diam-diam oleh WordPress core kecuali
    # `iaawg-yoast-rest-bridge.php` diaktifkan sebagai fallback.
    meta: dict = {}
    if meta_description:
        meta["_yoast_wpseo_metadesc"] = meta_description
    if focus_keyphrase:
        meta["_yoast_wpseo_focuskw"] = focus_keyphrase
    if seo_title:
        meta["_yoast_wpseo_title"] = seo_title
    if meta:
        payload["meta"] = meta

    # AIOSEO — didukung native lewat wp/v2/posts (tidak butuh plugin bridge),
    # asal user REST punya capability aioseo_page_general_settings (default
    # dimiliki role Administrator).
    aioseo_meta: dict = {}
    if seo_title:
        aioseo_meta["title"] = seo_title
    if meta_description:
        aioseo_meta["description"] = meta_description
    if focus_keyphrase:
        aioseo_meta["keyphrases"] = {"focus": {"keyphrase": focus_keyphrase}}
    if aioseo_meta:
        payload["aioseo_meta_data"] = aioseo_meta

    async with httpx.AsyncClient(timeout=60.0) as http:
        try:
            resp = await http.post(endpoint, json=payload, headers=client.headers)
            if resp.status_code in [200, 201]:
                data = resp.json()
                status_label = "dijadwalkan" if payload["status"] == "future" else "dipublish"
                sched = f" @ {payload['date']}" if payload.get("date") else ""
                print(f"[Blog Deploy] ✓ Post {status_label}: '{title[:50]}' "
                      f"(id={data.get('id')}){sched}")
                if aioseo_meta:
                    # Echo balik dari response — cara paling gampang verifikasi
                    # apakah struktur "keyphrases" yang kita kirim benar-benar
                    # tersimpan (formatnya tidak didokumentasikan publik).
                    print(f"[Blog Deploy] AIOSEO meta hasil simpan: "
                          f"{data.get('aioseo_meta_data')}")
                return data
            print(f"[Blog Deploy Error] Gagal post '{title[:50]}': "
                  f"{resp.status_code} {resp.text[:300]}")
            return {}
        except Exception as e:
            print(f"[Blog Deploy Error] Kendala jaringan create_blog_post: {e}")
            return {}


# ─────────────────────────────────────────────────────────────────────────────
# Batch deployment dengan staggered schedule
# ─────────────────────────────────────────────────────────────────────────────

async def deploy_blog_batch(
    client: WordPressClient,
    articles: list[dict],
    category_name: str = "",
    start_date: Optional[datetime] = None,
    interval_days: int = 1,
    publish_hour: int = 9,
    featured_image_urls: Optional[list[Optional[str]]] = None,
    main_keyword: str = "",
    log=print,
) -> list[dict]:
    """
    Deploy batch artikel ke WordPress dengan schedule staggered.

    Args:
        articles           : Hasil `generate_blog_batch(...)`.
        category_name      : Nama kategori tunggal (misal "Insight" / "Blog").
                             Kosong → tanpa kategori (WP akan pakai "Uncategorized").
        start_date         : Tanggal publish artikel pertama. None → publish
                             semua sekaligus (immediate).
        interval_days      : Jarak hari antar artikel (default 1 = harian).
        publish_hour       : Jam publish (0-23, default 9 pagi).
        featured_image_urls: List URL image (parallel dengan `articles`). Item
                             boleh None untuk skip. Kalau list None sama sekali,
                             semua artikel tanpa featured image.
        main_keyword       : Keyword utama batch ini — dipakai sebagai focus
                             keyphrase Yoast/AIOSEO untuk semua artikel, dan
                             sebagai basis alt text featured image. Kosong →
                             field SEO ini di-skip (tidak dikirim ke WP).
        log                : Callback log.

    Returns:
        List response dict WP untuk setiap artikel. Item {} = deploy gagal.
    """
    # 1) Ensure kategori sekali di awal
    cat_ids: list[int] = []
    if category_name:
        cid = await ensure_category(client, category_name)
        if cid:
            cat_ids = [cid]

    results: list[dict] = []
    for idx, article in enumerate(articles):
        # 2) Ensure tag per artikel
        tag_ids = await ensure_tags(client, article.get("tags", []) or [])

        # 3) Featured image (opsional)
        featured_id: Optional[int] = None
        if featured_image_urls and idx < len(featured_image_urls):
            img_url = featured_image_urls[idx]
            if img_url:
                img_bytes = await _download_bytes(img_url)
                if img_bytes:
                    safe_slug = _sanitize_slug(article.get("slug", ""), fallback=f"post-{idx+1}")
                    filename = f"{safe_slug}-featured.jpg"
                    alt_text = (f"{main_keyword}: {article.get('title', '')}"[:125]
                                if main_keyword else "")
                    featured_id = await upload_featured_image(
                        client, filename, img_bytes, mime_type="image/jpeg",
                        alt_text=alt_text,
                    )

        # 4) Hitung tanggal publish
        publish_date: Optional[datetime] = None
        if start_date:
            publish_date = start_date + timedelta(days=idx * interval_days)
            publish_date = publish_date.replace(
                hour=publish_hour, minute=0, second=0, microsecond=0,
            )

        # 5) Create post — CTA box (kalau ada) di-append di sini, bukan
        # disimpan permanen di article["content"] (lihat catatan di
        # content/blog_generator.py::generate_article).
        content = article.get("content", "")
        if article.get("cta_url"):
            content += _build_cta_block(
                article.get("cta_headline", ""),
                article.get("cta_button_text", ""),
                article["cta_url"],
            )
        result = await create_blog_post(
            client,
            title=article.get("title", "Untitled"),
            content=content,
            excerpt=article.get("excerpt", ""),
            slug=article.get("slug", ""),
            meta_description=article.get("meta_description", ""),
            featured_media=featured_id,
            category_ids=cat_ids or None,
            tag_ids=tag_ids or None,
            publish_date=publish_date,
            focus_keyphrase=main_keyword,
            seo_title=article.get("seo_title", ""),
        )
        results.append(result)

    total = len(results)
    ok = sum(1 for r in results if r)
    log(f"[Blog Deploy] Batch selesai — {ok}/{total} artikel berhasil di-deploy.")
    return results


# ─────────────────────────────────────────────────────────────────────────────
# Publish artikel dari halaman Review (Blog Autopost) — sumber gambar bisa
# stock (URL, sama seperti deploy_blog_batch) ATAU custom upload operator
# (file lokal di disk, hasil edit di halaman review).
# ─────────────────────────────────────────────────────────────────────────────

async def publish_reviewed_articles(
    client: WordPressClient,
    articles: list[dict],
    images_dir: Path,
    category_name: str = "",
    start_date: Optional[datetime] = None,
    interval_days: int = 1,
    publish_hour: int = 9,
    main_keyword: str = "",
    log=print,
) -> list[dict]:
    """
    Publish artikel yang sudah direview/diedit operator ke WordPress.

    Beda dengan `deploy_blog_batch`:
      - `articles` bisa berisi field hasil edit manual (title/content/dll
        sudah diedit operator di halaman review, bukan langsung dari LLM).
      - Featured image per-artikel: `article["featured_image"]` dict
        `{"type": "stock", "url": "..."}` (fetch via HTTP, sama seperti
        sebelumnya) atau `{"type": "custom", "filename": "..."}` (baca
        langsung dari `images_dir` — hasil upload operator di halaman
        review, lihat db/blog_drafts_store.py).
      - Return list dict `{"id": article_id, "wp": <result create_blog_post>}`
        supaya caller bisa update status "published" per artikel di batch.json
        (index-based seperti deploy_blog_batch tidak cukup karena publish
        bisa partial/per-artikel, bukan selalu seluruh batch).

    Jadwal staggered dihitung dari urutan `articles` yang di-pass masuk
    (sama seperti deploy_blog_batch) — caller bertanggung jawab urutan.
    """
    cat_ids: list[int] = []
    if category_name:
        cid = await ensure_category(client, category_name)
        if cid:
            cat_ids = [cid]

    results: list[dict] = []
    for idx, article in enumerate(articles):
        tag_ids = await ensure_tags(client, article.get("tags", []) or [])

        # Featured image — stock (URL) atau custom (file lokal)
        featured_id: Optional[int] = None
        fi = article.get("featured_image") or {}
        alt_text = (f"{main_keyword}: {article.get('title', '')}"[:125]
                    if main_keyword else "")
        safe_slug = _sanitize_slug(article.get("slug", ""), fallback=f"post-{idx+1}")

        if fi.get("type") == "custom" and fi.get("filename"):
            img_path = images_dir / fi["filename"]
            if img_path.exists():
                img_bytes = img_path.read_bytes()
                mime = "image/png" if img_path.suffix.lower() == ".png" else "image/jpeg"
                featured_id = await upload_featured_image(
                    client, img_path.name, img_bytes, mime_type=mime, alt_text=alt_text,
                )
            else:
                log(f"[Blog Deploy Warning] File gambar custom tidak ditemukan: {img_path}")
        elif fi.get("type") == "stock" and fi.get("url"):
            img_bytes = await _download_bytes(fi["url"])
            if img_bytes:
                filename = f"{safe_slug}-featured.jpg"
                featured_id = await upload_featured_image(
                    client, filename, img_bytes, mime_type="image/jpeg", alt_text=alt_text,
                )

        publish_date: Optional[datetime] = None
        if start_date:
            publish_date = start_date + timedelta(days=idx * interval_days)
            publish_date = publish_date.replace(
                hour=publish_hour, minute=0, second=0, microsecond=0,
            )

        content = article.get("content", "")
        if article.get("cta_url"):
            content += _build_cta_block(
                article.get("cta_headline", ""),
                article.get("cta_button_text", ""),
                article["cta_url"],
            )

        wp_result = await create_blog_post(
            client,
            title=article.get("title", "Untitled"),
            content=content,
            excerpt=article.get("excerpt", ""),
            slug=article.get("slug", ""),
            meta_description=article.get("meta_description", ""),
            featured_media=featured_id,
            category_ids=cat_ids or None,
            tag_ids=tag_ids or None,
            publish_date=publish_date,
            focus_keyphrase=main_keyword,
            seo_title=article.get("seo_title", ""),
        )
        results.append({"id": article.get("id"), "wp": wp_result})

    total = len(results)
    ok = sum(1 for r in results if r["wp"])
    log(f"[Blog Deploy] Publish review — {ok}/{total} artikel berhasil.")
    return results
