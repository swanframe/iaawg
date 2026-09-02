# -*- coding: utf-8 -*-
"""
Web UI routes untuk Blog Autopost Generator.

Additive module — tidak menyentuh `web.py` existing. Cukup import
`register_blog_routes` di web.py dan panggil dengan instance `app` FastAPI-nya.

Routes:
  GET  /blog              → form generator + autopost
  POST /blog/generate     → trigger background task (scrape → generate → deploy)
  GET  /blog/status       → polling status batch

Berbagi state opsional dengan pipeline website via `website_is_running_getter`
untuk mencegah dua batch jalan berbarengan.
"""

import asyncio
import uuid
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, Form, BackgroundTasks, Request, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse

from content.blog_generator import (
    collect_brand_material,
    generate_blog_batch,
)
from wordpress.client import WordPressClient
from wordpress.blog_deploy import publish_reviewed_articles
from config.settings import calc_token_cost
from visual.image_fetch import StockImageFetcher
from db import blog_drafts_store as drafts_store


# ─────────────────────────────────────────────────────────────────────────────
# Module-level state (batch blog)
# ─────────────────────────────────────────────────────────────────────────────

_blog_state = {
    "is_running": False,
    "logs": [],
    "progress_current": 0,
    "progress_total": 0,
    "progress_message": "",
    "articles": [],
    "batch_id": None,
    "brand_name": "",
    "prompt_tokens": 0,
    "completion_tokens": 0,
    "material_chars": 0,
    "started_at": None,
    "finished_at": None,
    "error": None,
}


def _log(msg: str):
    print(msg)
    _blog_state["logs"].append(msg)
    if len(_blog_state["logs"]) > 500:
        _blog_state["logs"] = _blog_state["logs"][-400:]


def _on_progress(current: int, total: int, message: str):
    _blog_state["progress_current"] = current
    _blog_state["progress_total"] = total
    _blog_state["progress_message"] = message


def _reset_state():
    _blog_state.update({
        "is_running": True,
        "logs": [],
        "progress_current": 0,
        "progress_total": 0,
        "progress_message": "Memulai...",
        "articles": [],
        "batch_id": None,
        "brand_name": "",
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "material_chars": 0,
        "started_at": datetime.now().isoformat(),
        "finished_at": None,
        "error": None,
    })


# ─────────────────────────────────────────────────────────────────────────────
# Background worker
# ─────────────────────────────────────────────────────────────────────────────

async def _run_blog_pipeline(
    brand_name: str,
    homepage_url: str,
    reference_urls: list[str],
    manual_content: str,
    main_keyword: str,
    secondary_keywords: list[str],
    n_articles: int,
    provider_chain_str: str,
    wp_url: str,
    wp_username: str,
    wp_app_password: str,
    include_featured_image: bool,
    external_links: list[str],
):
    """
    Background task — collect material → generate → simpan sebagai draft.

    Tidak pernah deploy ke WordPress di sini — deploy hanya terjadi lewat
    endpoint `/blog/draft/{batch_id}/publish` setelah operator review/edit
    hasil generate (lihat halaman `/blog/review/{batch_id}`).

    `wp_url`/`wp_username`/`wp_app_password` di sini OPSIONAL dan cuma dipakai
    untuk 2 hal read-only: (1) ambil kandidat link internal (halaman/post
    yang sudah live) supaya artikel bisa nyisip inbound link, dan (2)
    auto-detect halaman Kontak untuk CTA box. Bukan untuk publish — kredensial
    ini tidak pernah disimpan ke disk.
    """
    try:
        # ── Kandidat link internal (inbound) — ambil live dari WordPress ────
        # Best-effort: kalau credential belum lengkap atau situs belum siap
        # (mis. baru mau deploy pertama kali), kandidat kosong dan artikel
        # cukup skip poin link internal (lihat _format_internal_candidates).
        internal_link_candidates: list[dict] = []
        cta_url: str = ""
        if wp_url and wp_username and wp_app_password:
            try:
                wp_probe = WordPressClient(
                    url=wp_url, username=wp_username, app_password=wp_app_password,
                )
                pages = await wp_probe.list_pages()
                posts = await wp_probe.list_posts()
                internal_link_candidates = [
                    {"title": p["title"], "link": p["link"]} for p in (pages + posts)
                ]
                _log(f"[Blog] Kandidat link internal: {len(pages)} halaman + "
                     f"{len(posts)} post lama = {len(internal_link_candidates)} total.")

                # Auto-detect halaman Kontak (dibuat pipeline website) untuk
                # tujuan CTA box — reuse `pages` yang sudah diambil di atas,
                # tidak perlu request WP tambahan.
                contact_page = next(
                    (p for p in pages
                     if p.get("title", "").strip().lower() in ("kontak", "contact")),
                    None,
                )
                if contact_page:
                    cta_url = contact_page["link"]
                    _log(f"[Blog] Halaman Kontak ditemukan untuk CTA: {cta_url}")
                else:
                    _log("[Blog] Halaman Kontak tidak ditemukan di WordPress — "
                         "artikel batch ini tidak akan punya CTA box.")
            except Exception as e:
                _log(f"[Blog Warning] Gagal ambil kandidat link internal dari WordPress: {e}")
        else:
            _log("[Blog] WordPress credential belum diisi — link internal (inbound) "
                 "dan CTA box di-skip untuk batch ini.")

        # ── Hitung total langkah yang benar ─────────────────────────────────
        # scrape(1) + topics+N artikel(N+1) + featured image(1)
        total_steps = n_articles + 3

        # ── Step A: Kumpulkan materi brand ──────────────────────────────────
        _on_progress(0, total_steps, "Mengumpulkan materi brand (scrape + manual)")
        material = await collect_brand_material(
            homepage_url=homepage_url,
            reference_urls=reference_urls,
            manual_content=manual_content,
            log=_log,
        )
        _blog_state["material_chars"] = len(material)

        if not material.strip():
            msg = ("Materi brand kosong — tidak ada sumber yang berhasil di-scrape "
                   "dan tidak ada manual content. Isi minimal salah satu: homepage "
                   "URL yang valid, reference URL, atau paste manual content.")
            _blog_state["error"] = msg
            _log(f"[Blog Fatal] {msg}")
            return

        # ── Step B: Generate ─────────────────────────────────────────────────
        # Bungkus _on_progress dengan offset +1 supaya generate_blog_batch
        # tidak menimpa total_steps milik pipeline utama.
        # generate_blog_batch memanggil on_progress(0..N, N+1, msg),
        # kita mapping ke (1..N+1, total_steps, msg).
        def _progress_gen(current: int, _inner_total: int, message: str):
            _on_progress(1 + current, total_steps, message)

        articles, stats = await asyncio.to_thread(
            generate_blog_batch,
            brand_name=brand_name,
            brand_material=material,
            main_keyword=main_keyword,
            secondary_keywords=secondary_keywords,
            n_articles=n_articles,
            provider_chain_str=provider_chain_str,
            log=_log,
            on_progress=_progress_gen,         # ← ganti dari _on_progress
            internal_link_candidates=internal_link_candidates,
            external_links=external_links,
            cta_url=cta_url,
        )

        _blog_state["articles"] = articles
        _blog_state["prompt_tokens"] = stats.get("prompt_tokens", 0)
        _blog_state["completion_tokens"] = stats.get("completion_tokens", 0)

        if not articles:
            _blog_state["error"] = "Tidak ada artikel yang berhasil di-generate."
            return

        # ── Step C: Featured image (stock, opsional) — selalu jalan kalau
        # diaktifkan (tidak lagi digantung ke flag deploy, supaya draft yang
        # cuma di-generate tanpa deploy tetap punya gambar default yang bisa
        # dipreview/diganti di halaman review) ──
        _on_progress(n_articles + 2, total_steps, "Mengambil featured image")
        featured_images: list[Optional[dict]] = []
        if include_featured_image:
            _log("[Blog] Mengambil featured image via Unsplash...")
            fetcher = StockImageFetcher()
            for a in articles:
                query = a.get("_topic_target_keyword") or main_keyword
                try:
                    url = await fetcher.fetch_stock_url(query)
                    featured_images.append({"type": "stock", "url": url} if url else None)
                except Exception as e:
                    _log(f"[Blog Warning] Featured image fetch gagal: {e}")
                    featured_images.append(None)
                await asyncio.sleep(5)
        else:
            featured_images = [None] * len(articles)

        # ── Susun & simpan draft ke disk ──────────────────────────────────────
        batch_id = uuid.uuid4().hex[:12]
        for i, a in enumerate(articles):
            a["id"] = uuid.uuid4().hex[:10]
            a["status"] = "draft"
            a["featured_image"] = featured_images[i]
            a["published_post_id"] = None
            a["published_link"] = None

        drafts_store.save_batch(brand_name, batch_id, {
            "batch_id": batch_id,
            "brand_name": brand_name,
            "main_keyword": main_keyword,
            "external_links": external_links,
            "created_at": datetime.now().isoformat(),
            "articles": articles,
        })
        _blog_state["batch_id"] = batch_id
        _blog_state["brand_name"] = brand_name

        _log(f"[Blog] Draft tersimpan (batch {batch_id}) — buka /blog/review/{batch_id} untuk review & publish.")
        _on_progress(total_steps, total_steps, "Selesai — siap direview")   # ← 100%

    except Exception as e:
        _blog_state["error"] = f"Unhandled: {e}"
        _log(f"[Blog Fatal] {e}")
    finally:
        _blog_state["is_running"] = False
        _blog_state["finished_at"] = datetime.now().isoformat()


# ─────────────────────────────────────────────────────────────────────────────
# HTML form
# ─────────────────────────────────────────────────────────────────────────────

_FORM_HTML = """<!DOCTYPE html>
<html lang="id">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>iAAWG — Blog Autopost Generator</title>
    <link rel="icon" type="image/png" href="https://img.icons8.com/?size=100&id=e5sopTWYpy6o&format=png&color=000000">
    <script src="https://cdn.tailwindcss.com"></script>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
    <script src="https://unpkg.com/lucide@latest"></script>
    <script>
        tailwind.config = {
            theme: {
                extend: {
                    colors: {
                        ilogo: {
                            green: '#1E7E34',
                            orange: '#FF9E1B',
                        }
                    },
                    fontFamily: {
                        sans: ['Inter', 'sans-serif'],
                        mono: ['JetBrains Mono', 'monospace'],
                    }
                }
            }
        }
    </script>
</head>
<body class="bg-slate-50 text-slate-800 min-h-screen antialiased">

    <header class="border-b border-slate-200 bg-white sticky top-0 z-50 px-6 py-3 shadow-sm">
        <div class="max-w-7xl mx-auto flex items-center justify-between gap-3">
            <a href="/" class="flex items-center gap-2.5 flex-shrink-0 min-w-0 group" aria-label="iAAWG home">
                <div class="bg-ilogo-green text-white p-2 rounded-lg flex-shrink-0 group-hover:bg-green-700 transition-colors">
                    <i data-lucide="cpu" class="w-5 h-5"></i>
                </div>
                <div class="hidden md:block min-w-0">
                    <div class="text-sm font-bold tracking-tight text-slate-950 leading-tight">iAAWG</div>
                    <div class="text-[10px] text-slate-500 leading-tight">iLogo AI Auto Website Generator</div>
                </div>
            </a>

            <nav class="flex items-center gap-1 bg-slate-100/80 p-1 rounded-lg" aria-label="Primary">
                <a href="/"
                   class="flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium text-slate-500 hover:text-slate-800 hover:bg-white/60 transition-all">
                    <i data-lucide="globe" class="w-3.5 h-3.5"></i>
                    <span class="hidden sm:inline">Website Generator</span>
                </a>
                <a href="/blog" aria-current="page"
                   class="flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-semibold bg-white text-slate-900 shadow-sm">
                    <i data-lucide="newspaper" class="w-3.5 h-3.5"></i>
                    <span class="hidden sm:inline">Blog Autopost</span>
                </a>
            </nav>

            <a href="/settings" title="API Settings"
               class="flex items-center gap-1.5 text-slate-400 hover:text-slate-700 hover:bg-slate-100 transition-all px-3 py-2 rounded-lg text-sm font-medium flex-shrink-0">
                <i data-lucide="settings" class="w-4 h-4"></i>
                <span class="hidden lg:inline">Settings</span>
            </a>
        </div>
    </header>

    <main class="max-w-7xl mx-auto p-6 grid grid-cols-1 lg:grid-cols-12 gap-6">
        <div class="lg:col-span-12 flex justify-end -mb-2">
            <a href="/blog/drafts" class="inline-flex items-center gap-1.5 text-xs font-semibold text-slate-600 hover:text-ilogo-green transition-colors">
                <i data-lucide="folder-open" class="w-3.5 h-3.5"></i>
                Lihat Draft Tersimpan
            </a>
        </div>
        <form id="blogForm" class="lg:col-span-5 space-y-5">

            <!-- Card 1: Brand & Keyword -->
            <div class="bg-white border border-slate-200 rounded-xl p-5 space-y-4 shadow-sm">
                <div class="flex items-center space-x-2 pb-1 border-b border-slate-100">
                    <i data-lucide="tag" class="w-4 h-4 text-slate-500"></i>
                    <h3 class="text-xs font-bold text-slate-800 tracking-wide uppercase">Brand &amp; Keyword</h3>
                </div>

                <div class="space-y-1.5">
                    <label for="brand_name" class="text-xs font-semibold text-slate-700">Nama Brand: <span class="text-rose-500">*</span></label>
                    <input type="text" id="brand_name" name="brand_name" placeholder="Contoh: Zecurion" required class="w-full bg-slate-50 border border-slate-200 rounded-lg px-3 py-2 text-sm text-slate-900 placeholder-slate-400 focus:outline-none focus:border-ilogo-green focus:bg-white transition-all">
                </div>

                <div class="space-y-1.5">
                    <label for="main_keyword" class="text-xs font-semibold text-slate-700">Keyword Utama: <span class="text-rose-500">*</span></label>
                    <input type="text" id="main_keyword" name="main_keyword" placeholder="Contoh: Zecurion Indonesia" required class="w-full bg-slate-50 border border-slate-200 rounded-lg px-3 py-2 text-sm text-slate-900 placeholder-slate-400 focus:outline-none focus:border-ilogo-green focus:bg-white transition-all">
                    <p class="text-[10px] text-slate-400">Muncul di judul, meta description, intro, minimal 1 H2, dan penutup.</p>
                </div>

                <div class="space-y-1.5">
                    <label for="secondary_keywords" class="text-xs font-semibold text-slate-700">Keyword Tambahan (pisah koma):</label>
                    <input type="text" id="secondary_keywords" name="secondary_keywords" placeholder="Contoh: DLP Indonesia, data loss prevention enterprise" class="w-full bg-slate-50 border border-slate-200 rounded-lg px-3 py-2 text-sm text-slate-900 placeholder-slate-400 focus:outline-none focus:border-ilogo-green focus:bg-white transition-all">
                    <p class="text-[10px] text-slate-400">Masing-masing keyword akan muncul minimal 2× di artikel.</p>
                </div>
            </div>

            <!-- Card 2: Sumber Materi -->
            <div class="bg-white border border-slate-200 rounded-xl p-5 space-y-4 shadow-sm">
                <div class="flex items-center space-x-2 pb-1 border-b border-slate-100">
                    <i data-lucide="database" class="w-4 h-4 text-slate-500"></i>
                    <h3 class="text-xs font-bold text-slate-800 tracking-wide uppercase">Sumber Materi <span class="text-rose-500 normal-case font-normal ml-1">(minimal salah satu)</span></h3>
                </div>

                <div class="border border-amber-200 bg-amber-50/40 rounded-lg p-3 flex items-start gap-2 text-[11px] text-amber-800">
                    <i data-lucide="shield-alert" class="w-3.5 h-3.5 flex-shrink-0 mt-0.5"></i>
                    <div class="leading-relaxed">
                        <strong>Anti-Hallucination Policy.</strong>
                        Sistem TIDAK boleh mengarang produk/fitur brand yang tidak dikenalinya.
                        Isi minimal salah satu sumber di bawah — semakin kaya materi, semakin
                        akurat dan panjang artikelnya.
                    </div>
                </div>

                <div class="space-y-1.5">
                    <label for="homepage_url" class="text-xs font-semibold text-slate-700">Homepage URL Brand:</label>
                    <input type="url" id="homepage_url" name="homepage_url" placeholder="https://brand.com" class="w-full bg-slate-50 border border-slate-200 rounded-lg px-3 py-2 text-sm text-slate-900 placeholder-slate-400 focus:outline-none focus:border-ilogo-green focus:bg-white transition-all">
                    <p class="text-[10px] text-slate-400">Akan di-scrape via Playwright (retry 3×, deteksi Cloudflare).</p>
                </div>

                <div class="space-y-1.5">
                    <label for="reference_urls" class="text-xs font-semibold text-slate-700">URL Referensi Tambahan (1 per baris, opsional):</label>
                    <textarea id="reference_urls" name="reference_urls" rows="3" placeholder="https://brand.com/products&#10;https://brand.com/about&#10;https://brand.com/solutions/x" class="w-full bg-slate-50 border border-slate-200 rounded-lg px-3 py-2 text-sm text-slate-900 placeholder-slate-400 focus:outline-none focus:border-ilogo-green focus:bg-white transition-all resize-y"></textarea>
                    <p class="text-[10px] text-slate-400">Halaman produk, about, use case, whitepaper — apa saja yang memperkaya materi.</p>
                </div>

                <div class="space-y-1.5">
                    <label for="manual_content" class="text-xs font-semibold text-slate-700">Manual Content (opsional, paste bebas):</label>
                    <textarea id="manual_content" name="manual_content" rows="6" placeholder="Paste materi mentah di sini kalau situs brand di-block Cloudflare atau kalau Anda punya materi internal (press release, product brief, dsb.) yang lebih kaya dari situs publik." class="w-full bg-slate-50 border border-slate-200 rounded-lg px-3 py-2 text-xs font-mono text-slate-800 placeholder-slate-400 focus:outline-none focus:border-ilogo-green focus:bg-white transition-all resize-y"></textarea>
                </div>
            </div>

            <!-- Card 2b: Link Wajib (SEO) -->
            <div class="bg-white border border-slate-200 rounded-xl p-5 space-y-4 shadow-sm">
                <div class="flex items-center space-x-2 pb-1 border-b border-slate-100">
                    <i data-lucide="link" class="w-4 h-4 text-slate-500"></i>
                    <h3 class="text-xs font-bold text-slate-800 tracking-wide uppercase">Link Wajib (SEO)</h3>
                </div>

                <div class="border border-sky-200 bg-sky-50/40 rounded-lg p-3 flex items-start gap-2 text-[11px] text-sky-800">
                    <i data-lucide="info" class="w-3.5 h-3.5 flex-shrink-0 mt-0.5"></i>
                    <div class="leading-relaxed">
                        Tiap artikel otomatis mendapat 1 link internal (inbound — dipilih
                        AI dari halaman/post brand ini yang sudah live di WordPress) dan
                        1 link eksternal (outbound — dipilih AI dari daftar di bawah).
                        AI tidak diizinkan mengarang URL sendiri.
                    </div>
                </div>

                <div class="space-y-1.5">
                    <label for="external_links" class="text-xs font-semibold text-slate-700">Link Eksternal Referensi (1 per baris): <span class="text-rose-500">*</span></label>
                    <textarea id="external_links" name="external_links" rows="3" required placeholder="https://www.sumber-otoritatif.com/artikel&#10;https://standar-industri.org/panduan" class="w-full bg-slate-50 border border-slate-200 rounded-lg px-3 py-2 text-sm text-slate-900 placeholder-slate-400 focus:outline-none focus:border-ilogo-green focus:bg-white transition-all resize-y"></textarea>
                    <p class="text-[10px] text-slate-400">Minimal 1 URL — sumber otoritatif yang relevan dengan topik brand (standar industri, riset, statistik resmi, dsb). Boleh dipakai berulang di beberapa artikel kalau isinya cuma 1-2 URL.</p>
                </div>
            </div>

            <!-- Card 3: Konfigurasi Batch -->
            <div class="bg-white border border-slate-200 rounded-xl p-5 space-y-4 shadow-sm">
                <div class="flex items-center space-x-2 pb-1 border-b border-slate-100">
                    <i data-lucide="layers" class="w-4 h-4 text-slate-500"></i>
                    <h3 class="text-xs font-bold text-slate-800 tracking-wide uppercase">Konfigurasi Batch</h3>
                </div>

                <div class="grid grid-cols-2 gap-3">
                    <div class="space-y-1.5">
                        <label for="n_articles" class="text-xs font-semibold text-slate-700">Jumlah Artikel: <span class="text-rose-500">*</span></label>
                        <input type="number" id="n_articles" name="n_articles" min="1" max="15" required placeholder="mis. 3" class="w-full bg-slate-50 border border-slate-200 rounded-lg px-3 py-2 text-sm text-slate-900 placeholder-slate-400 focus:outline-none focus:border-ilogo-green focus:bg-white transition-all">
                        <p class="text-[10px] text-slate-400">Range 1-15. Tiap artikel ≈ 30-60 detik.</p>
                    </div>
                    <div class="space-y-1.5">
                        <label for="llm_chain" class="text-xs font-semibold text-slate-700">LLM Chain:</label>
                        <select id="llm_chain" name="llm_chain" class="w-full bg-slate-50 border border-slate-200 rounded-lg px-3 py-2 text-sm text-slate-900 focus:outline-none focus:border-ilogo-green focus:bg-white transition-all">
                            <option value="openai,groq" selected>OpenAI → Groq (failover)</option>
                            <option value="groq,openai">Groq → OpenAI (failover)</option>
                            <option value="openai">OpenAI only</option>
                            <option value="groq">Groq only</option>
                        </select>
                        <p class="text-[10px] text-slate-400">Prioritas provider LLM per artikel.</p>
                    </div>
                </div>
            </div>

            <!-- Card 4: Link Internal & Gambar (opsional) -->
            <div class="bg-white border border-slate-200 rounded-xl p-5 space-y-4 shadow-sm">
                <div class="flex items-center space-x-2 pb-1 border-b border-slate-100">
                    <i data-lucide="link-2" class="w-4 h-4 text-slate-500"></i>
                    <h3 class="text-xs font-bold text-slate-800 tracking-wide uppercase">Link Internal &amp; Gambar (opsional)</h3>
                </div>

                <div class="border border-sky-200 bg-sky-50/40 rounded-lg p-3 flex items-start gap-2 text-[11px] text-sky-800">
                    <i data-lucide="info" class="w-3.5 h-3.5 flex-shrink-0 mt-0.5"></i>
                    <div class="leading-relaxed">
                        Ini BUKAN untuk publish — cuma dipakai baca daftar halaman/post WordPress
                        yang sudah live (untuk link internal otomatis + deteksi halaman Kontak
                        untuk CTA box). Publish ke WordPress dilakukan manual nanti di halaman
                        <strong>Review Draft</strong> setelah artikel selesai digenerate.
                    </div>
                </div>

                <div class="space-y-1">
                    <label for="wp_url" class="text-[11px] font-semibold text-slate-600">WordPress Base URL:</label>
                    <input type="url" id="wp_url" name="wp_url" placeholder="https://brand.co.id" class="w-full bg-slate-50 border border-slate-200 rounded-lg px-3 py-1.5 text-xs focus:outline-none focus:border-ilogo-green focus:bg-white transition-all">
                </div>

                <div class="grid grid-cols-2 gap-3">
                    <div class="space-y-1">
                        <label for="wp_username" class="text-[11px] font-semibold text-slate-600">Username Admin:</label>
                        <input type="text" id="wp_username" name="wp_username" placeholder="admin_ilogo" class="w-full bg-slate-50 border border-slate-200 rounded-lg px-3 py-1.5 text-xs focus:outline-none focus:border-ilogo-green focus:bg-white transition-all">
                    </div>
                    <div class="space-y-1">
                        <label for="wp_app_password" class="text-[11px] font-semibold text-slate-600">Application Password:</label>
                        <input type="password" id="wp_app_password" name="wp_app_password" placeholder="xxxx xxxx xxxx xxxx xxxx" class="w-full bg-slate-50 border border-slate-200 rounded-lg px-3 py-1.5 text-xs focus:outline-none focus:border-ilogo-green focus:bg-white transition-all">
                    </div>
                </div>

                <div class="space-y-1">
                    <label for="include_featured_image" class="text-[11px] font-semibold text-slate-600">Featured Image Default (Unsplash):</label>
                    <select id="include_featured_image" name="include_featured_image" class="w-full bg-slate-50 border border-slate-200 rounded-lg px-3 py-1.5 text-xs focus:outline-none focus:border-ilogo-green focus:bg-white transition-all">
                        <option value="yes" selected>Ya, ambil otomatis</option>
                        <option value="no">Tidak — saya upload manual di halaman review</option>
                    </select>
                </div>
            </div>

            <!-- Submit -->
            <div class="flex gap-3">
                <button type="submit" id="submitBtn" class="flex-grow bg-slate-900 hover:bg-slate-800 text-white text-sm font-semibold py-3 px-4 rounded-xl shadow-md transition-all flex items-center justify-center gap-2">
                    <i data-lucide="send" class="w-4 h-4"></i>
                    <span id="submitBtnLabel">Generate Draft</span>
                </button>
            </div>
        </form>

        <!-- ================================================================ -->
        <!-- RIGHT COLUMN — Monitor + Article Results                          -->
        <!-- ================================================================ -->
        <div class="lg:col-span-7 space-y-5">

            <!-- Monitor Card -->
            <div class="bg-white border border-slate-200 rounded-xl p-5 shadow-sm flex flex-col overflow-hidden">
                <div class="flex items-center justify-between pb-3 border-b border-slate-100 flex-shrink-0">
                    <div class="flex items-center space-x-2">
                        <span class="relative flex h-2 w-2">
                            <span id="pulseStatus" class="animate-ping absolute inline-flex h-full w-full rounded-full bg-slate-400 opacity-75"></span>
                            <span id="dotStatus" class="relative inline-flex rounded-full h-2 w-2 bg-slate-400"></span>
                        </span>
                        <h2 class="text-xs font-bold text-slate-800 tracking-wide uppercase">Monitor Batch Generation</h2>
                    </div>
                </div>

                <div class="py-4 border-b border-slate-50 flex-shrink-0">
                    <div class="flex justify-between text-xs font-medium text-slate-500 mb-1.5">
                        <span id="progressMsg">Sistem Standby</span>
                        <span id="progressPct" class="font-mono font-semibold text-slate-700">0%</span>
                    </div>
                    <div class="w-full bg-slate-100 rounded-full h-2">
                        <div id="progressFill" class="bg-slate-400 h-2 rounded-full transition-all duration-500" style="width: 0%"></div>
                    </div>
                    <div class="flex flex-wrap gap-2 mt-3">
                        <div class="flex items-center space-x-1.5 bg-slate-100 px-2.5 py-1 rounded-md border border-slate-200">
                            <i data-lucide="file-text" class="w-3 h-3 text-slate-400"></i>
                            <span class="text-[10px] font-semibold text-slate-500 uppercase tracking-wider">Materi:</span>
                            <span id="matChars" class="text-[11px] font-mono font-bold text-slate-800">0</span>
                            <span class="text-[10px] text-slate-400">char</span>
                        </div>
                        <div class="flex items-center space-x-1.5 bg-slate-100 px-2.5 py-1 rounded-md border border-slate-200">
                            <i data-lucide="arrow-right-to-line" class="w-3 h-3 text-slate-400"></i>
                            <span class="text-[10px] font-semibold text-slate-500 uppercase tracking-wider">Input Tokens:</span>
                            <span id="uiPromptTokens" class="text-[11px] font-mono font-bold text-slate-800">0</span>
                        </div>
                        <div class="flex items-center space-x-1.5 bg-slate-100 px-2.5 py-1 rounded-md border border-slate-200">
                            <i data-lucide="arrow-left-from-line" class="w-3 h-3 text-slate-400"></i>
                            <span class="text-[10px] font-semibold text-slate-500 uppercase tracking-wider">Output Tokens:</span>
                            <span id="uiCompletionTokens" class="text-[11px] font-mono font-bold text-slate-800">0</span>
                        </div>
                        <div class="flex items-center space-x-1.5 bg-slate-100 px-2.5 py-1 rounded-md border border-slate-200" title="Estimasi biaya token berdasarkan harga OpenAI gpt-4.1-mini & kurs di halaman Settings.">
                            <i data-lucide="banknote" class="w-3 h-3 text-slate-400"></i>
                            <span class="text-[10px] font-semibold text-slate-500 uppercase tracking-wider">Est. Biaya:</span>
                            <span id="uiCost" class="text-[11px] font-mono font-bold text-slate-800">$0.00 (Rp0)</span>
                        </div>
                        <div class="flex items-center space-x-1.5 bg-slate-100 px-2.5 py-1 rounded-md border border-slate-200">
                            <i data-lucide="timer" class="w-3 h-3 text-slate-400"></i>
                            <span class="text-[10px] font-semibold text-slate-500 uppercase tracking-wider">Elapsed:</span>
                            <span id="uiElapsed" class="text-[11px] font-mono font-bold text-slate-800">—</span>
                        </div>
                        <div class="flex items-center space-x-1.5 bg-slate-100 px-2.5 py-1 rounded-md border border-slate-200" title="Estimasi berdasarkan kecepatan rata-rata. Dapat berubah karena rate limit LLM.">
                            <i data-lucide="clock" class="w-3 h-3 text-amber-400"></i>
                            <span class="text-[10px] font-semibold text-slate-500 uppercase tracking-wider">ETA ±:</span>
                            <span id="uiEta" class="text-[11px] font-mono font-bold text-amber-600">—</span>
                        </div>
                    </div>
                    <!-- Legacy hidden combined tokens span — preserved for existing JS handler compatibility -->
                    <span id="tokens" class="hidden">0 in / 0 out</span>
                </div>

                <div class="flex-grow overflow-y-auto pt-3 font-mono text-[11px] leading-relaxed text-slate-400 bg-slate-950 p-4 rounded-xl mt-3 shadow-inner h-[420px]" id="logs">
                    <div class="text-slate-500 italic">// Menunggu perintah eksekusi dari operator...</div>
                </div>
            </div>

            <!-- Articles Result Card (hidden initially) -->
            <div id="articlesCard" class="hidden bg-white border border-slate-200 rounded-xl p-5 shadow-sm space-y-3">
                <div class="flex items-center space-x-2 pb-2 border-b border-slate-100">
                    <i data-lucide="check-circle-2" class="w-4 h-4 text-emerald-600"></i>
                    <h3 class="text-xs font-bold text-slate-800 tracking-wide uppercase">Hasil Batch Artikel</h3>
                </div>
                <div id="articles" class="space-y-2"></div>
            </div>

        </div>
    </main>

<script>
// Init Lucide icons
if (window.lucide) { lucide.createIcons(); }

const ETA_MIN_PROGRESS = 20; // don't show ETA before this % (too little data)

function formatDuration(totalSeconds) {
    const s = Math.round(totalSeconds);
    if (s < 60) return s + 'd';
    const m = Math.floor(s / 60);
    const sec = s % 60;
    return sec > 0 ? m + 'm ' + sec + 'd' : m + 'm';
}

const form = document.getElementById('blogForm');
const submitBtn = document.getElementById('submitBtn');
const submitBtnLabel = document.getElementById('submitBtnLabel');
const pulseStatus = document.getElementById('pulseStatus');
const dotStatus = document.getElementById('dotStatus');
const progressFill = document.getElementById('progressFill');
const logsEl = document.getElementById('logs');
const articlesCard = document.getElementById('articlesCard');
const articlesEl = document.getElementById('articles');

function setStatusRunning() {
    pulseStatus.classList.remove('bg-slate-400');
    dotStatus.classList.remove('bg-slate-400');
    pulseStatus.classList.add('bg-ilogo-green');
    dotStatus.classList.add('bg-ilogo-green');
    progressFill.classList.remove('bg-slate-400');
    progressFill.classList.add('bg-ilogo-green');
}
function setStatusIdle() {
    pulseStatus.classList.remove('bg-ilogo-green', 'bg-rose-500');
    dotStatus.classList.remove('bg-ilogo-green', 'bg-rose-500');
    pulseStatus.classList.add('bg-slate-400');
    dotStatus.classList.add('bg-slate-400');
}
function setStatusDone() {
    pulseStatus.classList.remove('bg-slate-400', 'bg-ilogo-green');
    dotStatus.classList.remove('bg-slate-400', 'bg-ilogo-green');
    pulseStatus.classList.add('bg-emerald-500');
    dotStatus.classList.add('bg-emerald-500');
}

form.addEventListener('submit', async (e) => {
  e.preventDefault();

  // Client-side check: minimal salah satu sumber materi
  const fd = new FormData(form);
  const hasHome = (fd.get('homepage_url')||'').trim();
  const hasRefs = (fd.get('reference_urls')||'').trim();
  const hasManual = (fd.get('manual_content')||'').trim();
  if (!hasHome && !hasRefs && !hasManual) {
    alert('Isi minimal salah satu sumber materi: Homepage URL, URL Referensi, atau Manual Content.');
    return;
  }
  const hasExternalLinks = (fd.get('external_links')||'').trim();
  if (!hasExternalLinks) {
    alert('Isi minimal 1 Link Eksternal Referensi (dipakai sebagai outbound link tiap artikel).');
    return;
  }

  submitBtn.disabled = true;
  submitBtnLabel.textContent = 'Berjalan...';
  setStatusRunning();
  articlesCard.classList.add('hidden');
  articlesEl.innerHTML = '';
  logsEl.innerHTML = '<div class="text-slate-500 italic">// Memulai batch generation...</div>';

  const resp = await fetch('/blog/generate', { method: 'POST', body: fd });
  if (!resp.ok) {
    const j = await resp.json().catch(()=>({detail:'Unknown error'}));
    alert('Gagal start: ' + (j.detail || resp.status));
    submitBtn.disabled = false;
    submitBtnLabel.textContent = 'Generate Draft';
    setStatusIdle();
    return;
  }
  pollStatus();
});

async function pollStatus() {
  const progressMsg = document.getElementById('progressMsg');
  const progressPct = document.getElementById('progressPct');
  const tokensEl = document.getElementById('tokens');
  const matEl = document.getElementById('matChars');
  const promptTokEl = document.getElementById('uiPromptTokens');
  const complTokEl = document.getElementById('uiCompletionTokens');

  const iv = setInterval(async () => {
    let s;
    try { s = await (await fetch('/blog/status')).json(); }
    catch(e) { return; }

    // Render logs — tiap entri = <div> tersendiri supaya ada baris baru
    logsEl.innerHTML = s.logs.map(line => {
      const esc = line.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
      if (line.includes('[Blog Fatal]') || line.includes('[Blog Error]'))
        return `<div class="text-rose-400 py-0.5">${esc}</div>`;
      if (line.includes('[Blog Warning]'))
        return `<div class="text-amber-400 py-0.5">${esc}</div>`;
      if (line.includes('[Blog Deploy]'))
        return `<div class="text-emerald-400 py-0.5">${esc}</div>`;
      if (line.includes('[Blog Material]'))
        return `<div class="text-sky-400 py-0.5">${esc}</div>`;
      return `<div class="text-slate-400 py-0.5">${esc}</div>`;
    }).join('');
    logsEl.scrollTop = logsEl.scrollHeight;

    const pct = s.progress_total ? Math.round(100 * s.progress_current / s.progress_total) : 0;
    progressMsg.textContent = s.progress_message || 'Berjalan...';
    progressPct.textContent = pct + '%';
    progressFill.style.width = pct + '%';
    tokensEl.textContent = s.prompt_tokens + ' in / ' + s.completion_tokens + ' out';
    promptTokEl.textContent = s.prompt_tokens || 0;
    complTokEl.textContent = s.completion_tokens || 0;
    document.getElementById('uiCost').innerText =
        `$${(s.cost_usd || 0).toFixed(4)} (Rp${Math.round(s.cost_idr || 0).toLocaleString('id-ID')})`;
    matEl.textContent = s.material_chars || 0;

    if (s.elapsed_seconds != null) {
      document.getElementById('uiElapsed').innerText = formatDuration(s.elapsed_seconds);
    }
    const etaEl = document.getElementById('uiEta');
    if (s.is_running && pct >= ETA_MIN_PROGRESS && pct < 100 && s.elapsed_seconds > 0) {
      const etaSec = Math.round(s.elapsed_seconds * (100 - pct) / pct);
      etaEl.innerText = '~' + formatDuration(etaSec);
    } else if (!s.is_running) {
      etaEl.innerText = '—';
    }

    if (!s.is_running) {
      clearInterval(iv);
      submitBtn.disabled = false;
      submitBtnLabel.textContent = 'Generate Draft';

      const hasArticles = s.articles && s.articles.length;
      const hasError = !!s.error;

      if (hasArticles || hasError) {
        articlesCard.classList.remove('hidden');
      }

      if (hasError) {
        setStatusIdle();
        articlesEl.innerHTML = '<div class="border border-rose-200 bg-rose-50 rounded-lg p-3 text-xs text-rose-800"><strong>Error:</strong> ' + escapeHtml(s.error) + '</div>';
      } else if (hasArticles) {
        setStatusDone();
      } else {
        setStatusIdle();
      }

      if (hasArticles) {
        let cardsHtml = s.articles.map((a) => {
          const wc = a._word_count || 0;
          const wcClass = a._meets_min_words ? 'text-emerald-700 bg-emerald-50 border-emerald-200' : 'text-amber-700 bg-amber-50 border-amber-200';
          const anchorHtml = a._topic_material_anchor
            ? '<div class="text-[10px] text-slate-500 mt-1.5"><span class="font-semibold">Anchor materi:</span> ' + escapeHtml(a._topic_material_anchor) + '</div>' : '';
          const linkBadge = (ok, label) => '<span class="inline-flex items-center gap-1 text-[10px] font-semibold px-2 py-0.5 rounded-full border ' +
            (ok ? 'text-emerald-700 bg-emerald-50 border-emerald-200' : 'text-slate-400 bg-slate-50 border-slate-200') +
            '">' + (ok ? '✓' : '✗') + ' ' + label + '</span>';
          return '<div class="border border-slate-200 bg-slate-50/50 rounded-lg p-3">' +
                   '<div class="text-sm font-semibold text-slate-900 leading-snug">' + escapeHtml(a.title || 'Untitled') + '</div>' +
                   '<div class="flex flex-wrap items-center gap-2 mt-2">' +
                     '<span class="inline-flex items-center gap-1 text-[10px] font-mono font-bold ' + wcClass + ' border px-2 py-0.5 rounded-full">' + wc + ' kata</span>' +
                     linkBadge(a._has_internal_link, 'inbound') +
                     linkBadge(a._has_external_link, 'outbound') +
                     '<span class="text-[10px] text-slate-500">' + escapeHtml(a._topic_angle || '-') + '</span>' +
                     '<span class="text-[10px] text-slate-400">·</span>' +
                     '<span class="text-[10px] text-slate-500">' + escapeHtml((a.tags||[]).join(', ')) + '</span>' +
                   '</div>' +
                   anchorHtml +
                 '</div>';
        }).join('');
        if (s.batch_id) {
          cardsHtml += '<a href="/blog/review/' + encodeURIComponent(s.batch_id) + '" ' +
            'class="flex items-center justify-center gap-2 bg-ilogo-green hover:bg-green-700 text-white text-sm font-semibold py-3 px-4 rounded-xl shadow-md transition-all mt-2">' +
            '<i data-lucide="pencil-line" class="w-4 h-4"></i> Review &amp; Publish Draft Ini</a>';
        }
        articlesEl.insertAdjacentHTML('beforeend', cardsHtml);
      }

      // Re-init icons for any new badges
      if (window.lucide) { lucide.createIcons(); }
    }
  }, 1500);
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'})[c]);
}
</script>
</body>
</html>

"""


# ─────────────────────────────────────────────────────────────────────────────
# HTML — Review & Publish (WYSIWYG, per batch)
# ─────────────────────────────────────────────────────────────────────────────

_REVIEW_HTML = """<!DOCTYPE html>
<html lang="id">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>iAAWG — Review Draft Blog</title>
    <link rel="icon" type="image/png" href="https://img.icons8.com/?size=100&id=e5sopTWYpy6o&format=png&color=000000">
    <script src="https://cdn.tailwindcss.com"></script>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
    <script src="https://unpkg.com/lucide@latest"></script>
    <link href="https://cdn.jsdelivr.net/npm/quill@2.0.3/dist/quill.snow.css" rel="stylesheet">
    <script src="https://cdn.jsdelivr.net/npm/quill@2.0.3/dist/quill.js"></script>
    <script>
        tailwind.config = { theme: { extend: { colors: { ilogo: { green: '#1E7E34', orange: '#FF9E1B' } },
            fontFamily: { sans: ['Inter', 'sans-serif'] } } } }
    </script>
    <style>
        .ql-editor { min-height: 320px; font-size: 14px; line-height: 1.7; }
    </style>
</head>
<body class="bg-slate-50 text-slate-800 min-h-screen antialiased">

    <header class="border-b border-slate-200 bg-white sticky top-0 z-50 px-6 py-3 shadow-sm">
        <div class="max-w-5xl mx-auto flex items-center justify-between gap-3">
            <a href="/blog" class="flex items-center gap-2.5 flex-shrink-0 min-w-0 group" aria-label="Kembali ke Blog Autopost">
                <div class="bg-ilogo-green text-white p-2 rounded-lg flex-shrink-0 group-hover:bg-green-700 transition-colors">
                    <i data-lucide="arrow-left" class="w-5 h-5"></i>
                </div>
                <div class="min-w-0">
                    <div class="text-sm font-bold tracking-tight text-slate-950 leading-tight" id="pageBrand">Review Draft</div>
                    <div class="text-[10px] text-slate-500 leading-tight">Edit isi &amp; gambar sebelum publish ke WordPress</div>
                </div>
            </a>
            <a href="/blog/drafts" class="text-xs font-medium text-slate-500 hover:text-slate-800">Semua Draft</a>
        </div>
    </header>

    <main class="max-w-5xl mx-auto p-6 space-y-6">
        <div id="loadingMsg" class="text-sm text-slate-500">Memuat draft...</div>
        <div id="articlesWrap" class="space-y-6"></div>

        <!-- Panel Publish -->
        <div id="publishPanel" class="hidden bg-white border border-slate-200 rounded-xl p-5 shadow-sm space-y-4 sticky bottom-4">
            <div class="flex items-center space-x-2 pb-1 border-b border-slate-100">
                <i data-lucide="upload-cloud" class="w-4 h-4 text-slate-500"></i>
                <h3 class="text-xs font-bold text-slate-800 tracking-wide uppercase">Publish ke WordPress</h3>
            </div>
            <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
                <div class="space-y-1">
                    <label class="text-[11px] font-semibold text-slate-600">WordPress Base URL:</label>
                    <input type="url" id="pubWpUrl" placeholder="https://brand.co.id" class="w-full bg-slate-50 border border-slate-200 rounded-lg px-3 py-1.5 text-xs focus:outline-none focus:border-ilogo-green">
                </div>
                <div class="space-y-1">
                    <label class="text-[11px] font-semibold text-slate-600">Kategori WP:</label>
                    <input type="text" id="pubCategory" value="Insight" class="w-full bg-slate-50 border border-slate-200 rounded-lg px-3 py-1.5 text-xs focus:outline-none focus:border-ilogo-green">
                </div>
                <div class="space-y-1">
                    <label class="text-[11px] font-semibold text-slate-600">Username Admin:</label>
                    <input type="text" id="pubWpUser" placeholder="admin_ilogo" class="w-full bg-slate-50 border border-slate-200 rounded-lg px-3 py-1.5 text-xs focus:outline-none focus:border-ilogo-green">
                </div>
                <div class="space-y-1">
                    <label class="text-[11px] font-semibold text-slate-600">Application Password:</label>
                    <input type="password" id="pubWpPass" placeholder="xxxx xxxx xxxx xxxx xxxx" class="w-full bg-slate-50 border border-slate-200 rounded-lg px-3 py-1.5 text-xs focus:outline-none focus:border-ilogo-green">
                </div>
            </div>
            <label class="flex items-start gap-3 p-2.5 rounded-lg bg-sky-50/60 border border-sky-200 cursor-pointer select-none">
                <input type="checkbox" id="pubUseSchedule" checked class="mt-1 rounded border-sky-300 w-4 h-4 accent-sky-600">
                <div class="space-y-0.5">
                    <span class="text-xs font-semibold text-sky-950 block">Jadwalkan Publish Staggered</span>
                    <span class="text-[11px] text-sky-700 block">Uncheck untuk publish semua artikel terpilih sekaligus (immediate).</span>
                </div>
            </label>
            <div class="grid grid-cols-3 gap-3">
                <div class="space-y-1">
                    <label class="text-[11px] font-semibold text-slate-600">Mulai Tanggal:</label>
                    <input type="date" id="pubStartDate" class="w-full bg-slate-50 border border-slate-200 rounded-lg px-3 py-1.5 text-xs focus:outline-none focus:border-ilogo-green">
                </div>
                <div class="space-y-1">
                    <label class="text-[11px] font-semibold text-slate-600">Interval (hari):</label>
                    <input type="number" id="pubInterval" value="1" min="1" max="30" class="w-full bg-slate-50 border border-slate-200 rounded-lg px-3 py-1.5 text-xs focus:outline-none focus:border-ilogo-green">
                </div>
                <div class="space-y-1">
                    <label class="text-[11px] font-semibold text-slate-600">Jam Publish:</label>
                    <input type="number" id="pubHour" value="9" min="0" max="23" class="w-full bg-slate-50 border border-slate-200 rounded-lg px-3 py-1.5 text-xs focus:outline-none focus:border-ilogo-green">
                </div>
            </div>
            <button id="publishBtn" class="w-full bg-slate-900 hover:bg-slate-800 text-white text-sm font-semibold py-3 px-4 rounded-xl shadow-md transition-all flex items-center justify-center gap-2">
                <i data-lucide="send" class="w-4 h-4"></i>
                <span id="publishBtnLabel">Publish Artikel Terpilih</span>
            </button>
            <div id="publishResult" class="text-xs"></div>
        </div>
    </main>

<script>
const BATCH_ID = "__BATCH_ID__";
const quills = {};
let batchData = null;

function escapeHtml(s) {
  return String(s == null ? '' : s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'})[c]);
}

function ctaPreviewHtml(a) {
  if (!a.cta_url) return '';
  return '<div class="mt-3 p-3 rounded-lg border border-dashed border-slate-300 bg-slate-50">' +
    '<div class="text-[10px] font-semibold text-slate-400 uppercase tracking-wide mb-1.5">CTA otomatis — tidak bisa diedit di sini</div>' +
    '<div style="padding:14px 16px;background:#f4f6fb;border:1px solid #e2e6f0;border-left:4px solid #2454ff;border-radius:8px;">' +
      '<p style="margin:0 0 10px;font-size:14px;font-weight:600;color:#1a1a2e;">' + escapeHtml(a.cta_headline || 'Tertarik dengan solusi ini?') + '</p>' +
      '<span style="display:inline-block;padding:8px 16px;background:#2454ff;color:#fff;border-radius:5px;font-weight:600;font-size:13px;">' +
        escapeHtml(a.cta_button_text || 'Hubungi Kami') + ' &rarr;</span>' +
    '</div></div>';
}

function statusBadge(a) {
  if (a.status === 'published') {
    return '<span class="inline-flex items-center gap-1 text-[10px] font-semibold text-emerald-700 bg-emerald-50 border border-emerald-200 px-2 py-0.5 rounded-full">✓ Published' +
      (a.published_link ? ' — <a href="' + escapeHtml(a.published_link) + '" target="_blank" class="underline">lihat</a>' : '') + '</span>';
  }
  return '<span class="inline-flex items-center gap-1 text-[10px] font-semibold text-amber-700 bg-amber-50 border border-amber-200 px-2 py-0.5 rounded-full">Draft</span>';
}

function imageThumbHtml(a) {
  const fi = a.featured_image;
  if (!fi) return '<div class="text-[11px] text-slate-400 italic">Belum ada featured image.</div>';
  const src = fi.type === 'custom' ? ('/output/' + a._brand_slug + '/blog_drafts/' + BATCH_ID + '/images/' + encodeURIComponent(fi.filename)) : fi.url;
  return '<img src="' + src + '" class="w-full h-32 object-cover rounded-lg border border-slate-200" alt="featured">';
}

function renderArticle(a) {
  const locked = a.status === 'published';
  return '<div class="bg-white border border-slate-200 rounded-xl p-5 shadow-sm space-y-3" data-article-id="' + a.id + '">' +
    '<div class="flex items-start justify-between gap-3">' +
      '<label class="flex items-center gap-2">' +
        '<input type="checkbox" class="pubSelect w-4 h-4 accent-ilogo-green" ' + (locked ? 'disabled' : 'checked') + '>' +
        '<span class="text-sm font-bold text-slate-900">' + escapeHtml(a.title || 'Untitled') + '</span>' +
      '</label>' +
      statusBadge(a) +
    '</div>' +

    '<div class="grid grid-cols-1 md:grid-cols-3 gap-4">' +
      '<div class="md:col-span-2 space-y-3">' +
        '<div class="grid grid-cols-1 sm:grid-cols-2 gap-2">' +
          '<div><label class="text-[10px] font-semibold text-slate-500">Judul</label>' +
            '<input class="f-title w-full bg-slate-50 border border-slate-200 rounded-lg px-2 py-1.5 text-xs" value="' + escapeHtml(a.title) + '" ' + (locked?'disabled':'') + '></div>' +
          '<div><label class="text-[10px] font-semibold text-slate-500">SEO Title</label>' +
            '<input class="f-seo_title w-full bg-slate-50 border border-slate-200 rounded-lg px-2 py-1.5 text-xs" value="' + escapeHtml(a.seo_title) + '" ' + (locked?'disabled':'') + '></div>' +
          '<div><label class="text-[10px] font-semibold text-slate-500">Slug</label>' +
            '<input class="f-slug w-full bg-slate-50 border border-slate-200 rounded-lg px-2 py-1.5 text-xs" value="' + escapeHtml(a.slug) + '" ' + (locked?'disabled':'') + '></div>' +
          '<div><label class="text-[10px] font-semibold text-slate-500">Tags (pisah koma)</label>' +
            '<input class="f-tags w-full bg-slate-50 border border-slate-200 rounded-lg px-2 py-1.5 text-xs" value="' + escapeHtml((a.tags||[]).join(', ')) + '" ' + (locked?'disabled':'') + '></div>' +
        '</div>' +
        '<div><label class="text-[10px] font-semibold text-slate-500">Meta Description</label>' +
          '<textarea class="f-meta_description w-full bg-slate-50 border border-slate-200 rounded-lg px-2 py-1.5 text-xs" rows="2" ' + (locked?'disabled':'') + '>' + escapeHtml(a.meta_description) + '</textarea></div>' +
        '<div><label class="text-[10px] font-semibold text-slate-500 block mb-1">Isi Artikel</label>' +
          '<div class="editor-' + a.id + ' bg-white border border-slate-200 rounded-lg"></div></div>' +
        ctaPreviewHtml(a) +
      '</div>' +
      '<div class="space-y-2">' +
        '<label class="text-[10px] font-semibold text-slate-500 block">Featured Image</label>' +
        '<div class="thumb-' + a.id + '">' + imageThumbHtml(a) + '</div>' +
        (locked ? '' :
          '<label class="block text-[11px] font-semibold text-slate-600 bg-slate-50 border border-slate-200 rounded-lg px-3 py-2 text-center cursor-pointer hover:bg-slate-100">' +
            'Ganti Gambar<input type="file" accept="image/*" class="f-image hidden"></label>') +
      '</div>' +
    '</div>' +

    (locked ? '' :
      '<div class="flex items-center gap-2 pt-2 border-t border-slate-100">' +
        '<button class="saveBtn bg-ilogo-green hover:bg-green-700 text-white text-xs font-semibold py-2 px-4 rounded-lg">Simpan Perubahan</button>' +
        '<span class="saveStatus text-[11px] text-slate-400"></span>' +
      '</div>') +
  '</div>';
}

async function loadBatch() {
  const resp = await fetch('/blog/draft/' + encodeURIComponent(BATCH_ID));
  if (!resp.ok) {
    document.getElementById('loadingMsg').textContent = 'Draft tidak ditemukan.';
    return;
  }
  batchData = await resp.json();
  document.getElementById('pageBrand').textContent = 'Review Draft — ' + batchData.brand_name;
  document.getElementById('loadingMsg').classList.add('hidden');

  const wrap = document.getElementById('articlesWrap');
  batchData.articles.forEach(a => { a._brand_slug = batchData.brand_slug; });
  wrap.innerHTML = batchData.articles.map(renderArticle).join('');

  batchData.articles.forEach(a => {
    const el = wrap.querySelector('.editor-' + a.id);
    if (!el) return;
    const q = new Quill(el, {
      theme: 'snow',
      modules: { toolbar: [['bold','italic'], [{header:[2,3,false]}], ['link'], [{list:'ordered'},{list:'bullet'}]] },
    });
    q.root.innerHTML = a.content || '';
    if (a.status === 'published') q.enable(false);
    quills[a.id] = q;
  });

  wrap.querySelectorAll('[data-article-id]').forEach(card => {
    const articleId = card.getAttribute('data-article-id');
    const saveBtn = card.querySelector('.saveBtn');
    if (saveBtn) saveBtn.addEventListener('click', () => saveArticle(articleId, card));
    const fileInput = card.querySelector('.f-image');
    if (fileInput) fileInput.addEventListener('change', () => uploadImage(articleId, card, fileInput));
  });

  if (window.lucide) lucide.createIcons();
  document.getElementById('publishPanel').classList.remove('hidden');

  const t = new Date(); t.setDate(t.getDate()+1);
  document.getElementById('pubStartDate').value = t.toISOString().slice(0,10);
}

async function saveArticle(articleId, card) {
  const statusEl = card.querySelector('.saveStatus');
  statusEl.textContent = 'Menyimpan...';
  const payload = {
    title: card.querySelector('.f-title').value.trim(),
    seo_title: card.querySelector('.f-seo_title').value.trim(),
    slug: card.querySelector('.f-slug').value.trim(),
    tags: card.querySelector('.f-tags').value.split(',').map(t=>t.trim()).filter(Boolean),
    meta_description: card.querySelector('.f-meta_description').value.trim(),
    content: quills[articleId].root.innerHTML,
  };
  const resp = await fetch('/blog/draft/' + encodeURIComponent(BATCH_ID) + '/' + encodeURIComponent(articleId), {
    method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify(payload),
  });
  statusEl.textContent = resp.ok ? 'Tersimpan ✓' : 'Gagal menyimpan';
  setTimeout(() => { statusEl.textContent=''; }, 2500);
}

async function uploadImage(articleId, card, fileInput) {
  const file = fileInput.files[0];
  if (!file) return;
  const fd = new FormData();
  fd.append('file', file);
  const resp = await fetch('/blog/draft/' + encodeURIComponent(BATCH_ID) + '/' + encodeURIComponent(articleId) + '/image', {
    method: 'POST', body: fd,
  });
  if (resp.ok) {
    const j = await resp.json();
    card.querySelector('.thumb-' + articleId).innerHTML =
      '<img src="' + j.url + '" class="w-full h-32 object-cover rounded-lg border border-slate-200" alt="featured">';
  } else {
    alert('Upload gambar gagal.');
  }
}

document.getElementById('publishBtn').addEventListener('click', async () => {
  const wpUrl = document.getElementById('pubWpUrl').value.trim();
  const wpUser = document.getElementById('pubWpUser').value.trim();
  const wpPass = document.getElementById('pubWpPass').value.trim();
  if (!wpUrl || !wpUser || !wpPass) { alert('Isi WordPress Base URL, Username, dan Application Password.'); return; }

  const selectedIds = Array.from(document.querySelectorAll('.pubSelect:checked')).map(cb => cb.closest('[data-article-id]').getAttribute('data-article-id'));
  if (!selectedIds.length) { alert('Pilih minimal 1 artikel untuk dipublish.'); return; }

  const useSchedule = document.getElementById('pubUseSchedule').checked;
  const btn = document.getElementById('publishBtn');
  const label = document.getElementById('publishBtnLabel');
  const resultEl = document.getElementById('publishResult');
  btn.disabled = true;
  label.textContent = 'Publishing...';
  resultEl.textContent = '';

  const resp = await fetch('/blog/draft/' + encodeURIComponent(BATCH_ID) + '/publish', {
    method: 'POST', headers: {'Content-Type':'application/json'},
    body: JSON.stringify({
      wp_url: wpUrl, wp_username: wpUser, wp_app_password: wpPass,
      category_name: document.getElementById('pubCategory').value.trim() || 'Insight',
      use_schedule: useSchedule,
      start_date: useSchedule ? document.getElementById('pubStartDate').value : '',
      interval_days: parseInt(document.getElementById('pubInterval').value || '1', 10),
      publish_hour: parseInt(document.getElementById('pubHour').value || '9', 10),
      article_ids: selectedIds,
    }),
  });
  btn.disabled = false;
  label.textContent = 'Publish Artikel Terpilih';

  if (!resp.ok) {
    const j = await resp.json().catch(()=>({detail:'Unknown error'}));
    resultEl.innerHTML = '<span class="text-rose-600">Gagal: ' + escapeHtml(j.detail || resp.status) + '</span>';
    return;
  }
  const j = await resp.json();
  resultEl.innerHTML = '<span class="text-emerald-700">' + j.published + '/' + j.total + ' artikel berhasil dipublish.</span>';
  await loadBatch();
});

loadBatch();
</script>
</body>
</html>
"""


# ─────────────────────────────────────────────────────────────────────────────
# Registration
# ─────────────────────────────────────────────────────────────────────────────

def register_blog_routes(app: FastAPI, website_is_running_getter=None):
    """
    Daftarkan route blog ke instance FastAPI existing.

    Args:
        app: instance FastAPI dari web.py
        website_is_running_getter: callable → bool. Kalau None, tidak cek
            konflik dengan pipeline website. Kalau di-set, blog akan menolak
            start selama website pipeline masih jalan (mencegah quota LLM
            bentrok). Contoh: `lambda: is_running`.
    """

    @app.get("/blog", response_class=HTMLResponse)
    async def blog_form():
        return HTMLResponse(_FORM_HTML)

    @app.post("/blog/generate")
    async def blog_generate(
        background_tasks: BackgroundTasks,
        brand_name: str = Form(...),
        main_keyword: str = Form(...),
        secondary_keywords: str = Form(""),
        homepage_url: str = Form(""),
        reference_urls: str = Form(""),
        manual_content: str = Form(""),
        external_links: str = Form(...),
        n_articles: int = Form(...),
        llm_chain: str = Form("openai,groq"),
        wp_url: str = Form(""),
        wp_username: str = Form(""),
        wp_app_password: str = Form(""),
        include_featured_image: str = Form("yes"),
    ):
        if _blog_state["is_running"]:
            return JSONResponse(
                status_code=400,
                content={"detail": "Batch blog lain masih berjalan."},
            )
        if website_is_running_getter and website_is_running_getter():
            return JSONResponse(
                status_code=400,
                content={"detail": "Pipeline website sedang berjalan — tunggu selesai."},
            )

        # Range validation — server-side
        n_articles = int(n_articles)
        if n_articles < 1 or n_articles > 15:
            return JSONResponse(
                status_code=400,
                content={"detail": "Jumlah artikel harus antara 1 dan 15."},
            )

        # Sumber materi: minimal salah satu
        homepage_url = homepage_url.strip()
        reference_urls_list = [
            u.strip() for u in reference_urls.splitlines() if u.strip()
        ]
        manual_content = manual_content.strip()
        if not (homepage_url or reference_urls_list or manual_content):
            return JSONResponse(
                status_code=400,
                content={"detail": "Isi minimal salah satu sumber materi: "
                                   "Homepage URL, URL Referensi, atau Manual Content."},
            )

        # Link eksternal (outbound) — wajib minimal 1, tidak boleh dikarang AI.
        external_links_list = [
            u.strip() for u in external_links.splitlines() if u.strip()
        ]
        if not external_links_list:
            return JSONResponse(
                status_code=400,
                content={"detail": "Isi minimal 1 Link Eksternal Referensi — "
                                   "dipakai sebagai outbound link tiap artikel."},
            )

        include_featured_bool = (include_featured_image == "yes")
        secondary_list = [k.strip() for k in secondary_keywords.split(",") if k.strip()]

        _reset_state()
        _log(f"[Blog] Request diterima. brand={brand_name}, n_articles={n_articles}, "
             f"sumber={{home:{bool(homepage_url)}, refs:{len(reference_urls_list)}, "
             f"manual:{bool(manual_content)}}}, link_eksternal={len(external_links_list)}")

        background_tasks.add_task(
            _run_blog_pipeline,
            brand_name=brand_name.strip(),
            homepage_url=homepage_url,
            reference_urls=reference_urls_list,
            manual_content=manual_content,
            main_keyword=main_keyword.strip(),
            secondary_keywords=secondary_list,
            n_articles=n_articles,
            provider_chain_str=llm_chain,
            wp_url=wp_url.strip(),
            wp_username=wp_username.strip(),
            wp_app_password=wp_app_password.strip(),
            include_featured_image=include_featured_bool,
            external_links=external_links_list,
        )

        return {"status": "started"}

    @app.get("/blog/status")
    async def blog_status():
        elapsed_seconds = 0
        if _blog_state["started_at"]:
            end = (
                datetime.fromisoformat(_blog_state["finished_at"])
                if _blog_state["finished_at"]
                else datetime.now()
            )
            elapsed_seconds = int((end - datetime.fromisoformat(_blog_state["started_at"])).total_seconds())

        arts_lite = []
        for a in _blog_state["articles"]:
            arts_lite.append({
                "title": a.get("title", ""),
                "slug": a.get("slug", ""),
                "excerpt": a.get("excerpt", ""),
                "tags": a.get("tags", []),
                "_word_count": a.get("_word_count", 0),
                "_meets_min_words": a.get("_meets_min_words", False),
                "_has_internal_link": a.get("_has_internal_link", False),
                "_has_external_link": a.get("_has_external_link", False),
                "_topic_angle": a.get("_topic_angle", ""),
                "_topic_material_anchor": a.get("_topic_material_anchor", ""),
            })
        cost = calc_token_cost(_blog_state["prompt_tokens"], _blog_state["completion_tokens"])
        return {
            "is_running": _blog_state["is_running"],
            "progress_current": _blog_state["progress_current"],
            "progress_total": _blog_state["progress_total"],
            "progress_message": _blog_state["progress_message"],
            "prompt_tokens": _blog_state["prompt_tokens"],
            "completion_tokens": _blog_state["completion_tokens"],
            "cost_usd": cost["cost_usd"],
            "cost_idr": cost["cost_idr"],
            "material_chars": _blog_state["material_chars"],
            "logs": _blog_state["logs"][-200:],
            "articles": arts_lite,
            "batch_id": _blog_state["batch_id"],
            "error": _blog_state["error"],
            "started_at": _blog_state["started_at"],
            "finished_at": _blog_state["finished_at"],
            "elapsed_seconds": elapsed_seconds,
        }

    # ─────────────────────────────────────────────────────────────────────
    # Review & Publish — draft artikel tersimpan di disk (lihat
    # db/blog_drafts_store.py). Terpisah dari /blog/generate: generate cuma
    # bikin draft, publish ke WordPress selalu lewat sini setelah operator
    # review/edit.
    # ─────────────────────────────────────────────────────────────────────

    @app.get("/blog/drafts", response_class=HTMLResponse)
    async def blog_drafts_list():
        batches = drafts_store.list_batches()
        if not batches:
            rows_html = '<div class="text-sm text-slate-400 italic p-6 text-center">Belum ada draft. Generate artikel dulu di halaman Blog Autopost.</div>'
        else:
            rows = []
            for b in batches:
                pub_badge = (f'<span class="text-[10px] font-semibold text-emerald-700 bg-emerald-50 border border-emerald-200 px-2 py-0.5 rounded-full">{b["n_published"]}/{b["n_articles"]} published</span>'
                             if b["n_published"] else
                             f'<span class="text-[10px] font-semibold text-amber-700 bg-amber-50 border border-amber-200 px-2 py-0.5 rounded-full">{b["n_articles"]} draft</span>')
                rows.append(f'''
                <a href="/blog/review/{b["batch_id"]}" class="block bg-white border border-slate-200 rounded-xl p-4 shadow-sm hover:border-ilogo-green transition-colors">
                    <div class="flex items-center justify-between gap-3">
                        <div class="min-w-0">
                            <div class="text-sm font-semibold text-slate-900 truncate">{b["brand_name"]} — {b["main_keyword"]}</div>
                            <div class="text-[11px] text-slate-400 mt-0.5">{b["created_at"][:16].replace("T"," ")}</div>
                        </div>
                        {pub_badge}
                    </div>
                </a>''')
            rows_html = '<div class="space-y-3">' + "".join(rows) + '</div>'

        html = f"""<!DOCTYPE html>
<html lang="id"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>iAAWG — Draft Blog</title>
<script src="https://cdn.tailwindcss.com"></script>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
<script>tailwind.config={{theme:{{extend:{{colors:{{ilogo:{{green:'#1E7E34'}}}},fontFamily:{{sans:['Inter','sans-serif']}}}}}}}}</script>
</head><body class="bg-slate-50 text-slate-800 min-h-screen antialiased font-sans">
<header class="border-b border-slate-200 bg-white px-6 py-3 shadow-sm">
  <div class="max-w-3xl mx-auto flex items-center justify-between">
    <a href="/blog" class="text-sm font-bold text-slate-900">&larr; Blog Autopost</a>
    <span class="text-xs font-semibold text-slate-500 uppercase tracking-wide">Draft Tersimpan</span>
  </div>
</header>
<main class="max-w-3xl mx-auto p-6">{rows_html}</main>
</body></html>"""
        return HTMLResponse(html)

    @app.get("/blog/review/{batch_id}", response_class=HTMLResponse)
    async def blog_review_page(batch_id: str):
        brand = drafts_store.find_batch_brand(batch_id)
        if not brand:
            return HTMLResponse("<h1>Draft tidak ditemukan.</h1><a href='/blog/drafts'>Kembali</a>", status_code=404)
        return HTMLResponse(_REVIEW_HTML.replace("__BATCH_ID__", batch_id))

    @app.get("/blog/draft/{batch_id}")
    async def blog_draft_get(batch_id: str):
        brand = drafts_store.find_batch_brand(batch_id)
        if not brand:
            return JSONResponse(status_code=404, content={"detail": "Draft tidak ditemukan."})
        data = drafts_store.load_batch(brand, batch_id)
        if not data:
            return JSONResponse(status_code=404, content={"detail": "Draft tidak ditemukan."})
        data["brand_slug"] = drafts_store.slugify_brand(brand)
        return data

    # NOTE: rute `/blog/draft/{batch_id}/publish` HARUS didaftarkan sebelum
    # `/blog/draft/{batch_id}/{article_id}` — Starlette mencocokkan path
    # berdasarkan urutan registrasi, bukan spesifisitas, jadi kalau dibalik
    # request ke .../publish akan "ketangkap" sebagai article_id="publish".
    @app.post("/blog/draft/{batch_id}/publish")
    async def blog_draft_publish(batch_id: str, request: Request):
        brand = drafts_store.find_batch_brand(batch_id)
        if not brand:
            return JSONResponse(status_code=404, content={"detail": "Draft tidak ditemukan."})
        data = drafts_store.load_batch(brand, batch_id)
        if not data:
            return JSONResponse(status_code=404, content={"detail": "Draft tidak ditemukan."})

        body = await request.json()
        wp_url = (body.get("wp_url") or "").strip()
        wp_username = (body.get("wp_username") or "").strip()
        wp_app_password = (body.get("wp_app_password") or "").strip()
        category_name = (body.get("category_name") or "Insight").strip()
        use_schedule = bool(body.get("use_schedule"))
        interval_days = int(body.get("interval_days") or 1)
        publish_hour = int(body.get("publish_hour") or 9)
        article_ids = body.get("article_ids") or []

        if not (wp_url and wp_username and wp_app_password):
            return JSONResponse(status_code=400, content={"detail": "WordPress credential belum lengkap."})
        if not article_ids:
            return JSONResponse(status_code=400, content={"detail": "Pilih minimal 1 artikel untuk dipublish."})

        parsed_start: Optional[datetime] = None
        if use_schedule and body.get("start_date"):
            try:
                parsed_start = datetime.strptime(body["start_date"], "%Y-%m-%d")
            except Exception:
                return JSONResponse(status_code=400, content={"detail": "Format start_date tidak valid (YYYY-MM-DD)."})

        all_articles = {a["id"]: a for a in data.get("articles", [])}
        to_publish = [all_articles[aid] for aid in article_ids
                      if aid in all_articles and all_articles[aid].get("status") != "published"]
        if not to_publish:
            return JSONResponse(status_code=400, content={"detail": "Semua artikel terpilih sudah published."})

        try:
            client = WordPressClient(url=wp_url, username=wp_username, app_password=wp_app_password)
        except ValueError as e:
            return JSONResponse(status_code=400, content={"detail": f"WordPress credential invalid: {e}"})

        results = await publish_reviewed_articles(
            client=client,
            articles=to_publish,
            images_dir=drafts_store.images_dir(brand, batch_id),
            category_name=category_name,
            start_date=parsed_start,
            interval_days=interval_days,
            publish_hour=publish_hour,
            main_keyword=data.get("main_keyword", ""),
            log=_log,
        )

        ok = 0
        for r in results:
            wp = r.get("wp") or {}
            if wp.get("id"):
                ok += 1
                drafts_store.update_article(
                    brand, batch_id, r["id"],
                    status="published",
                    published_post_id=wp.get("id"),
                    published_link=wp.get("link"),
                )

        return {"status": "done", "published": ok, "total": len(to_publish)}

    @app.post("/blog/draft/{batch_id}/{article_id}")
    async def blog_draft_update_article(batch_id: str, article_id: str, request: Request):
        brand = drafts_store.find_batch_brand(batch_id)
        if not brand:
            return JSONResponse(status_code=404, content={"detail": "Draft tidak ditemukan."})
        payload = await request.json()
        allowed = {"title", "seo_title", "slug", "tags", "meta_description", "content", "excerpt"}
        fields = {k: v for k, v in payload.items() if k in allowed}
        updated = drafts_store.update_article(brand, batch_id, article_id, **fields)
        if not updated:
            return JSONResponse(status_code=404, content={"detail": "Artikel tidak ditemukan."})
        return {"status": "saved"}

    @app.post("/blog/draft/{batch_id}/{article_id}/image")
    async def blog_draft_upload_image(batch_id: str, article_id: str, file: UploadFile = File(...)):
        brand = drafts_store.find_batch_brand(batch_id)
        if not brand:
            return JSONResponse(status_code=404, content={"detail": "Draft tidak ditemukan."})

        ext = (file.filename or "").rsplit(".", 1)[-1].lower() if "." in (file.filename or "") else "jpg"
        if ext not in {"jpg", "jpeg", "png", "webp"}:
            ext = "jpg"
        safe_name = f"{article_id}-{uuid.uuid4().hex[:6]}.{ext}"

        img_dir = drafts_store.images_dir(brand, batch_id)
        img_dir.mkdir(parents=True, exist_ok=True)
        content = await file.read()
        (img_dir / safe_name).write_bytes(content)

        updated = drafts_store.update_article(
            brand, batch_id, article_id,
            featured_image={"type": "custom", "filename": safe_name},
        )
        if not updated:
            return JSONResponse(status_code=404, content={"detail": "Artikel tidak ditemukan."})

        brand_slug = drafts_store.slugify_brand(brand)
        url = f"/output/{brand_slug}/blog_drafts/{batch_id}/images/{safe_name}"
        return {"status": "saved", "url": url}


