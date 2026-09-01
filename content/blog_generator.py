# -*- coding: utf-8 -*-
"""
Blog Autopost Generator — orchestrator level.

Reuses:
  - `content.generator.FailoverLLMProvider` untuk auto-failover OpenAI ↔ Groq
  - `crawler.scraper.BaseScraper` + `ContentExtractor` untuk sumber materi

Flow:
    collect_brand_material(homepage, ref_urls, manual) → raw_data blob
    generate_blog_batch(...) menerima raw_data
      ├─ generate_topics(...)     → 1 LLM call, hasilkan N brief topik
      └─ untuk setiap topik:
          └─ generate_article(...) → 1 LLM call per artikel

Kenapa 1 artikel = 1 call:
  - Granular failover: kalau artikel ke-3 gagal parse, sisanya tetap aman.
  - Menghindari truncate: N × 1500 kata = potensi truncate di max_tokens.
  - Progress bar per-artikel lebih akurat.

Kenapa ada expand pass (generate_article):
  - LLM (terutama model cepat/kecil) sering pilih ujung bawah dari rentang
    panjang yang diminta di prompt walau sudah diberi angka minimum eksplisit
    — hasil observasi nyata: artikel mentok di ~700-900 kata padahal diminta
    1500. Prompt-only tuning tidak cukup reliable untuk kasus ini.
  - Solusinya: kalau hasil generate awal masih < MIN_ARTICLE_WORDS, panggil
    LLM lagi dengan ARTICLE_EXPAND_PROMPT untuk memperpanjang artikel yang
    sudah ada (bukan generate ulang dari nol), maksimal MAX_EXPAND_ATTEMPTS
    kali. Ini hanya menambah cost untuk artikel yang gagal capai minimum.
"""

import asyncio
import json
import re
from typing import Callable, Optional

from content.generator import FailoverLLMProvider
from content.templates.blog_prompts import (
    BLOG_SYSTEM_INSTRUCTION,
    TOPIC_GENERATION_PROMPT,
    ARTICLE_GENERATION_PROMPT,
    ARTICLE_EXPAND_PROMPT,
    LINK_FIX_PROMPT,
    SEO_FIX_PROMPT,
)


# ─────────────────────────────────────────────────────────────────────────────
# Konstanta
# ─────────────────────────────────────────────────────────────────────────────

MIN_ARTICLE_WORDS = 1500          # threshold minimum sesuai brief
MAX_PARSE_RETRIES = 3             # jumlah percobaan parse JSON per call
MAX_EXPAND_ATTEMPTS = 2           # percobaan perpanjang kalau masih < MIN_ARTICLE_WORDS
MAX_LINK_FIX_ATTEMPTS = 1         # percobaan sisip link kalau inbound/outbound belum ada
MAX_SEO_FIX_ATTEMPTS = 1          # percobaan perbaiki title/seo_title/meta_description/
                                   # intro/H2 kalau keyword utama belum ada di situ
SEO_FIX_ITEMS = {"title", "seo_title", "meta_description", "100 kata pertama", "heading H2"}
                                   # subset hasil _check_seo_requirements yang bisa
                                   # diperbaiki lewat SEO_FIX_PROMPT — "slug" sengaja
                                   # tidak masuk sini karena diperbaiki programatik
                                   # (deterministik, tidak perlu LLM, lihat _ensure_keyword_in_slug)
ARTICLE_MAX_TOKENS = 7000         # completion cap artikel/expand — target 1800-2200 kata
                                   # + tag HTML + overhead JSON butuh headroom lebih dari
                                   # default 5500 (dipakai topic generation & pipeline lain)
DEFAULT_MAX_CHARS_PER_SOURCE = 6000
MIN_MATERIAL_CHARS = 500          # threshold untuk anggap scrape berhasil


# ─────────────────────────────────────────────────────────────────────────────
# Sumber materi (scraper + manual paste)
# ─────────────────────────────────────────────────────────────────────────────

async def collect_brand_material(
    homepage_url: str = "",
    reference_urls: Optional[list[str]] = None,
    manual_content: str = "",
    max_chars_per_source: int = DEFAULT_MAX_CHARS_PER_SOURCE,
    log: Callable[[str], None] = print,
) -> str:
    """
    Agregat materi brand dari 3 sumber jadi satu blob raw_data:
      - Homepage brand (scrape, retry 3x)
      - Reference URLs (multiple, mis. halaman produk / about)
      - Manual content (paste operator — untuk kasus Cloudflare block atau
        materi internal yang lebih kaya dari situs publik)

    Semua sumber opsional. Kalau semua kosong / gagal, return "".
    Caller HARUS validate result — kalau kosong, jangan lanjut generate
    (LLM akan mengarang).
    """
    # Import di dalam fungsi supaya modul ini tidak selalu load Playwright
    # kalau caller tidak butuh scraping.
    from crawler.scraper import BaseScraper, ContentExtractor

    scraper = BaseScraper()
    chunks: list[str] = []

    # 1. Homepage
    if homepage_url and homepage_url.strip():
        homepage_url = homepage_url.strip()
        log(f"[Blog Material] Scrape homepage: {homepage_url}")
        got_homepage = False
        for attempt in range(1, 4):
            try:
                html = await scraper.scrape_url(homepage_url)
                text = ContentExtractor.clean_html(html)
                if ContentExtractor.is_bot_wall(text):
                    log(f"[Blog Material] Percobaan {attempt}/3: terdeteksi bot-wall")
                    continue
                if len(text) >= MIN_MATERIAL_CHARS:
                    chunks.append(f"=== HOMEPAGE ({homepage_url}) ===\n"
                                  f"{text[:max_chars_per_source]}")
                    log(f"[Blog Material] Homepage OK — {len(text)} char (dipotong "
                        f"ke {max_chars_per_source})")
                    got_homepage = True
                    break
                else:
                    log(f"[Blog Material] Percobaan {attempt}/3: teks hanya "
                        f"{len(text)} char (min {MIN_MATERIAL_CHARS})")
            except Exception as e:
                log(f"[Blog Material] Percobaan {attempt}/3 error: {e}")
        if not got_homepage:
            log(f"[Blog Material] Homepage GAGAL di-scrape setelah 3 percobaan — skip")

    # 2. Reference URLs
    for url in (reference_urls or []):
        url = (url or "").strip()
        if not url:
            continue
        log(f"[Blog Material] Scrape referensi: {url}")
        try:
            html = await scraper.scrape_url(url)
            text = ContentExtractor.clean_html(html)
            if ContentExtractor.is_bot_wall(text):
                log(f"[Blog Material] {url} terdeteksi bot-wall — skip")
                continue
            if len(text) >= 300:   # threshold lebih rendah untuk halaman spesifik
                chunks.append(f"=== REFERENSI ({url}) ===\n"
                              f"{text[:max_chars_per_source]}")
                log(f"[Blog Material] {url} OK — {len(text)} char")
            else:
                log(f"[Blog Material] {url} teks terlalu pendek "
                    f"({len(text)} char) — skip")
        except Exception as e:
            log(f"[Blog Material] Gagal scrape {url}: {e}")

    # 3. Manual content (jangan di-cut se-agresif — ini materi berkualitas)
    if manual_content and manual_content.strip():
        text = ContentExtractor.clean_manual_text(manual_content)
        if text:
            manual_cap = max_chars_per_source * 2
            chunks.append(f"=== MANUAL INPUT ===\n{text[:manual_cap]}")
            log(f"[Blog Material] Manual content: {len(text)} char (cap {manual_cap})")

    if not chunks:
        log("[Blog Material] KOSONG — tidak ada sumber yang berhasil.")
        return ""

    combined = "\n\n".join(chunks)
    log(f"[Blog Material] Total materi terkumpul: {len(combined)} char "
        f"dari {len(chunks)} sumber")
    return combined


# ─────────────────────────────────────────────────────────────────────────────
# Utility
# ─────────────────────────────────────────────────────────────────────────────

def _strip_json_fences(raw: str) -> str:
    """Buang ```json … ``` kalau LLM tetap membungkus meski dilarang."""
    if not raw:
        return ""
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```\s*$", "", raw)
    return raw.strip()


def _word_count_html(html: str) -> int:
    """Hitung kata setelah strip tag HTML — untuk validasi panjang artikel."""
    if not html:
        return 0
    plain = re.sub(r"<[^>]+>", " ", html)
    plain = re.sub(r"\s+", " ", plain).strip()
    return len(plain.split()) if plain else 0


def _format_internal_candidates(candidates: Optional[list[dict]]) -> str:
    """Render kandidat internal link (title+link dari WP REST API) jadi teks
    daftar untuk prompt. Kosong → instruksikan LLM untuk skip, bukan mengarang."""
    if not candidates:
        return "(tidak ada kandidat — lewati poin link internal)"
    lines = [f"- {c.get('title', '(tanpa judul)')}: {c['link']}"
             for c in candidates if c.get("link")]
    return "\n".join(lines) if lines else "(tidak ada kandidat — lewati poin link internal)"


def _format_external_links(urls: Optional[list[str]]) -> str:
    """Render whitelist URL eksternal (input operator) jadi teks daftar untuk prompt."""
    urls = [u for u in (urls or []) if u]
    if not urls:
        return "(tidak ada kandidat — lewati poin link eksternal)"
    return "\n".join(f"- {u}" for u in urls)


def _build_cta_block(headline: str, button_text: str, url: str) -> str:
    """
    Render box CTA sebagai HTML tetap (bukan hasil tulisan LLM) supaya selalu
    tampil konsisten & pasti ada — sama seperti CTA band di builder website
    (elementor_builder.py), yang juga memisahkan "layout" (kode) dari "teks"
    (LLM). Fallback ke teks generik kalau LLM tidak mengisi field CTA.
    """
    headline = (headline or "").strip() or "Tertarik dengan solusi ini?"
    button_text = (button_text or "").strip() or "Hubungi Kami"
    return (
        '<div style="margin:32px 0;padding:24px 28px;background:#f4f6fb;'
        'border:1px solid #e2e6f0;border-left:4px solid #2454ff;border-radius:8px;">'
        f'<p style="margin:0 0 14px;font-size:17px;font-weight:600;color:#1a1a2e;">'
        f'{headline}</p>'
        f'<a href="{url}" style="display:inline-block;padding:11px 22px;'
        'background:#2454ff;color:#ffffff;border-radius:5px;text-decoration:none;'
        f'font-weight:600;font-size:15px;">{button_text} &rarr;</a>'
        '</div>'
    )


def _extract_hrefs(html: str) -> list[str]:
    """Ambil semua isi atribut href="..." dari HTML artikel."""
    if not html:
        return []
    return re.findall(r'href="([^"]+)"', html)


def _slugify(text: str) -> str:
    """Versi ringan sanitasi slug — dipakai untuk cek/gabung, bukan slug final
    (slug final tetap disanitasi lagi oleh `_sanitize_slug` di blog_deploy.py)."""
    text = (text or "").strip().lower()
    text = re.sub(r"[^a-z0-9\s-]", "", text)
    text = re.sub(r"[\s_-]+", "-", text).strip("-")
    return text


def _ensure_keyword_in_slug(slug: str, main_keyword: str) -> str:
    """
    Paksa slug mengandung `main_keyword` — deterministik, tidak perlu LLM,
    karena ini murni transformasi string (beda dengan title/H2 yang perlu
    disisipkan natural ke kalimat). Kalau keyword sudah ada, slug dikembalikan
    apa adanya.
    """
    kw_slug = _slugify(main_keyword)
    if not kw_slug:
        return slug
    current_slug = _slugify(slug)
    if kw_slug in current_slug:
        return slug
    return f"{kw_slug}-{current_slug}"[:60].rstrip("-") if current_slug else kw_slug


def _check_seo_requirements(article: dict, main_keyword: str) -> tuple[bool, list[str]]:
    """
    Cek deterministik apakah `main_keyword` (dipakai sebagai focus keyphrase
    Yoast/AIOSEO) benar-benar muncul di semua tempat yang disyaratkan prompt:
    title, seo_title, slug, meta_description, ~100 kata pertama content, dan
    minimal 1 heading H2. Case-insensitive.

    Ini bukan validasi kreatif seperti link (yang butuh LLM memilih penempatan)
    — semua requirement di sini murni format/kepatuhan literal terhadap prompt,
    jadi cukup di-log sebagai warning kalau gagal, tanpa fix-up pass tambahan.
    """
    kw = (main_keyword or "").strip().lower()
    if not kw:
        return True, []

    missing: list[str] = []

    if kw not in (article.get("title", "") or "").lower():
        missing.append("title")
    if kw not in (article.get("seo_title", "") or "").lower():
        missing.append("seo_title")
    # Slug pakai tanda hubung, bukan spasi — bandingkan versi slugified
    # keduanya, jangan literal `kw` (mengandung spasi) vs slug (tidak).
    kw_slug = _slugify(main_keyword)
    if kw_slug and kw_slug not in _slugify(article.get("slug", "") or ""):
        missing.append("slug")
    if kw not in (article.get("meta_description", "") or "").lower():
        missing.append("meta_description")

    content = article.get("content", "") or ""
    plain = re.sub(r"<[^>]+>", " ", content)
    plain = re.sub(r"\s+", " ", plain).strip()
    first_100_words = " ".join(plain.split()[:100]).lower()
    if kw not in first_100_words:
        missing.append("100 kata pertama")

    h2_texts = " ".join(re.findall(r"<h2[^>]*>(.*?)</h2>", content, re.IGNORECASE | re.DOTALL)).lower()
    if kw not in h2_texts:
        missing.append("heading H2")

    return (not missing), missing


def _check_required_links(
    content: str,
    internal_candidates: Optional[list[dict]],
    external_links: Optional[list[str]],
) -> tuple[bool, bool]:
    """
    Cek apakah `content` sudah mengandung minimal 1 href ke kandidat internal
    dan 1 href ke kandidat eksternal. Kalau daftar kandidatnya sendiri kosong,
    syarat itu dianggap terpenuhi (tidak ada yang bisa disisipkan).
    """
    hrefs = _extract_hrefs(content)
    internal_urls = {c["link"] for c in (internal_candidates or []) if c.get("link")}
    external_urls = {u for u in (external_links or []) if u}

    has_internal = (not internal_urls) or any(h in internal_urls for h in hrefs)
    has_external = (not external_urls) or any(h in external_urls for h in hrefs)
    return has_internal, has_external


def _parse_json_with_retry(
    prompt: str,
    system_instruction: str,
    provider_chain_str: str,
    label: str,
    log: Callable[[str], None],
    max_parse_retries: int = MAX_PARSE_RETRIES,
    max_tokens: int = 5500,
) -> tuple[dict, int, int]:
    """
    Panggil LLM lalu parse JSON. Retry `max_parse_retries` kali.
    Failover antar provider di-handle di dalam FailoverLLMProvider per-call.
    """
    llm = FailoverLLMProvider(provider_chain_str)
    total_p = total_c = 0
    last_error = None

    for attempt in range(1, max_parse_retries + 1):
        log(f"[Blog] {label} — percobaan {attempt}/{max_parse_retries}")
        raw, p_t, c_t = llm.generate_content(prompt, system_instruction, max_tokens=max_tokens)
        total_p += p_t
        total_c += c_t

        if not raw:
            last_error = "Response LLM kosong."
            continue

        cleaned = _strip_json_fences(raw)
        try:
            data = json.loads(cleaned)
            return data, total_p, total_c
        except json.JSONDecodeError as e:
            last_error = f"JSON parse error: {e}"
            log(f"[Blog Warning] {last_error} — retry.")

    log(f"[Blog Error] Gagal parse {label} setelah {max_parse_retries} percobaan. "
        f"Terakhir: {last_error}")
    return {}, total_p, total_c


# ─────────────────────────────────────────────────────────────────────────────
# Public API — generation
# ─────────────────────────────────────────────────────────────────────────────

def generate_topics(
    brand_name: str,
    brand_material: str,
    main_keyword: str,
    secondary_keywords: list[str],
    n_topics: int,
    provider_chain_str: str,
    log: Callable[[str], None] = print,
) -> tuple[list[dict], int, int]:
    """
    Generate N ide topik berdasarkan materi brand.
    Return: (topics, prompt_tokens, completion_tokens).
    """
    prompt = TOPIC_GENERATION_PROMPT.format(
        brand_name=brand_name,
        raw_data=brand_material or "(tidak ada materi referensi)",
        main_keyword=main_keyword,
        secondary_keywords=(", ".join(secondary_keywords)
                            if secondary_keywords else "(tidak ada)"),
        n_topics=n_topics,
    )

    data, p_t, c_t = _parse_json_with_retry(
        prompt=prompt,
        system_instruction=BLOG_SYSTEM_INSTRUCTION,
        provider_chain_str=provider_chain_str,
        label="Generate daftar topik",
        log=log,
    )

    topics = data.get("topics", []) if isinstance(data, dict) else []
    return topics[:n_topics], p_t, c_t


def generate_article(
    brand_name: str,
    brand_material: str,
    topic: dict,
    main_keyword: str,
    secondary_keywords: list[str],
    provider_chain_str: str,
    log: Callable[[str], None] = print,
    min_words: int = MIN_ARTICLE_WORDS,
    max_expand_attempts: int = MAX_EXPAND_ATTEMPTS,
    internal_link_candidates: Optional[list[dict]] = None,
    external_links: Optional[list[str]] = None,
    cta_url: str = "",
) -> tuple[dict, int, int]:
    """
    Generate satu artikel full berbasis materi + brief topik. Kalau hasil
    awal masih < min_words, otomatis coba perpanjang lewat ARTICLE_EXPAND_PROMPT
    (lihat catatan "Kenapa ada expand pass" di docstring modul).

    `internal_link_candidates` (list of {"title","link"}, dari
    WordPressClient.list_pages()/list_posts()) dan `external_links` (list URL
    input operator) WAJIB berisi URL nyata — LLM hanya memilih, tidak boleh
    mengarang. Kalau salah satu/keduanya tidak tersisip di percobaan pertama,
    dilakukan 1x fix-up pass lewat LINK_FIX_PROMPT (lihat blok setelah expand
    pass di bawah).

    `cta_url` (biasanya halaman Kontak brand, auto-detect dari WordPress) —
    kalau diisi, box CTA di-append ke akhir "content" (lihat _build_cta_block).
    Kosong → CTA di-skip, artikel tetap valid tanpa CTA.
    """
    material_for_article = brand_material[:8000] if brand_material else "(tidak ada materi referensi)"
    internal_candidates_text = _format_internal_candidates(internal_link_candidates)
    external_links_text = _format_external_links(external_links)

    prompt = ARTICLE_GENERATION_PROMPT.format(
        brand_name=brand_name,
        raw_data=material_for_article,
        title=topic.get("title", ""),
        angle=topic.get("angle", "informational"),
        summary=topic.get("summary", ""),
        main_keyword=main_keyword,
        secondary_keywords=(", ".join(secondary_keywords)
                            if secondary_keywords else "(tidak ada)"),
        internal_link_candidates=internal_candidates_text,
        external_links=external_links_text,
    )

    article, p_t, c_t = _parse_json_with_retry(
        prompt=prompt,
        system_instruction=BLOG_SYSTEM_INSTRUCTION,
        provider_chain_str=provider_chain_str,
        label=f"Tulis artikel '{topic.get('title', '')[:40]}'",
        log=log,
        max_tokens=ARTICLE_MAX_TOKENS,
    )

    if not isinstance(article, dict) or not article.get("content"):
        return {}, p_t, c_t

    # Simpan sekali dari hasil generate awal — expand/link-fix pass di bawah
    # tidak diminta mempertahankan field ini di schema output-nya, jadi kita
    # pegang salinan lokal supaya CTA tetap kontekstual meski article dict
    # ditimpa penuh oleh hasil expand/fix.
    cta_headline = article.get("cta_headline", "")
    cta_button_text = article.get("cta_button_text", "")
    seo_title = article.get("seo_title", "")

    wc = _word_count_html(article["content"])
    title_short = article.get("title", topic.get("title", ""))[:40]

    expand_attempt = 0
    while wc < min_words and expand_attempt < max_expand_attempts:
        expand_attempt += 1
        log(f"[Blog] '{title_short}' baru {wc} kata (minimum {min_words}) — "
            f"perpanjang, percobaan {expand_attempt}/{max_expand_attempts}")

        expand_prompt = ARTICLE_EXPAND_PROMPT.format(
            brand_name=brand_name,
            main_keyword=main_keyword,
            current_words=wc,
            min_words=min_words,
            ideal_words=min_words + 400,
            current_article_json=json.dumps(article, ensure_ascii=False),
            raw_data=material_for_article,
        )

        expanded, ep_t, ec_t = _parse_json_with_retry(
            prompt=expand_prompt,
            system_instruction=BLOG_SYSTEM_INSTRUCTION,
            provider_chain_str=provider_chain_str,
            label=f"Perpanjang artikel '{title_short}'",
            log=log,
            max_tokens=ARTICLE_MAX_TOKENS,
        )
        p_t += ep_t
        c_t += ec_t

        if not isinstance(expanded, dict) or not expanded.get("content"):
            log(f"[Blog Warning] Perpanjangan '{title_short}' gagal (respon invalid) "
                f"— hentikan percobaan, pakai versi sebelumnya.")
            break

        new_wc = _word_count_html(expanded["content"])
        if new_wc <= wc:
            log(f"[Blog Warning] Perpanjangan '{title_short}' tidak menambah panjang "
                f"({new_wc} vs {wc} kata) — hentikan percobaan, pakai versi sebelumnya.")
            break

        article = expanded
        wc = new_wc

    if wc < min_words:
        log(f"[Blog Warning] '{title_short}' hanya {wc} kata "
            f"(minimum {min_words}) setelah {expand_attempt} kali percobaan "
            f"perpanjang. Artikel tetap disimpan — pertimbangkan tambah materi "
            f"referensi.")
    else:
        log(f"[Blog] '{title_short}' — {wc} kata ✓")

    # ── Pastikan link internal/eksternal wajib tersisip (kalau kandidatnya ada) ──
    has_internal, has_external = _check_required_links(
        article["content"], internal_link_candidates, external_links
    )
    fix_attempt = 0
    while (not has_internal or not has_external) and fix_attempt < MAX_LINK_FIX_ATTEMPTS:
        fix_attempt += 1
        missing_parts = []
        if not has_internal:
            missing_parts.append("link internal (inbound) ke salah satu kandidat internal")
        if not has_external:
            missing_parts.append("link eksternal (outbound) ke salah satu kandidat eksternal")
        missing_description = " dan ".join(missing_parts)
        log(f"[Blog] '{title_short}' belum punya {missing_description} — "
            f"sisip link, percobaan {fix_attempt}/{MAX_LINK_FIX_ATTEMPTS}")

        fix_prompt = LINK_FIX_PROMPT.format(
            brand_name=brand_name,
            missing_description=missing_description,
            current_article_json=json.dumps(article, ensure_ascii=False),
            internal_link_candidates=internal_candidates_text,
            external_links=external_links_text,
        )

        fixed, fp_t, fc_t = _parse_json_with_retry(
            prompt=fix_prompt,
            system_instruction=BLOG_SYSTEM_INSTRUCTION,
            provider_chain_str=provider_chain_str,
            label=f"Sisip link '{title_short}'",
            log=log,
            max_tokens=ARTICLE_MAX_TOKENS,
        )
        p_t += fp_t
        c_t += fc_t

        if not isinstance(fixed, dict) or not fixed.get("content"):
            log(f"[Blog Warning] Sisip link '{title_short}' gagal (respon invalid) "
                f"— hentikan percobaan, pakai versi sebelumnya.")
            break

        article = fixed
        wc = _word_count_html(article["content"])
        has_internal, has_external = _check_required_links(
            article["content"], internal_link_candidates, external_links
        )

    if internal_link_candidates and not has_internal:
        log(f"[Blog Warning] '{title_short}' tetap tanpa link internal setelah fix-up.")
    if external_links and not has_external:
        log(f"[Blog Warning] '{title_short}' tetap tanpa link eksternal setelah fix-up.")

    # ── seo_title fallback — expand/link-fix pass bisa menghapus field ini
    # meski sudah diminta dipertahankan di schema output-nya (lihat catatan
    # cta_headline/cta_button_text di atas, pola sama) ──
    if not article.get("seo_title") and seo_title:
        article["seo_title"] = seo_title
    if not article.get("seo_title"):
        article["seo_title"] = article.get("title", topic.get("title", ""))[:60]

    # ── Pastikan keyword utama (focus keyphrase) wajib ada di title/seo_title/
    # meta_description/intro/H2 — kalau prompt gagal dipatuhi, 1x percobaan
    # perbaikan lewat SEO_FIX_PROMPT (pola sama seperti link fix-up di atas,
    # dan HARUS dilakukan sebelum CTA box ditambahkan supaya LLM tidak
    # menyentuh HTML CTA yang di-render programmatic) ──
    seo_ok, seo_missing = _check_seo_requirements(article, main_keyword)
    seo_fix_attempt = 0
    while (any(m in SEO_FIX_ITEMS for m in seo_missing)
           and seo_fix_attempt < MAX_SEO_FIX_ATTEMPTS):
        seo_fix_attempt += 1
        fix_targets = [m for m in seo_missing if m in SEO_FIX_ITEMS]
        missing_seo_description = ", ".join(fix_targets)
        log(f"[Blog] '{title_short}' keyword utama '{main_keyword}' belum ada di "
            f"{missing_seo_description} — perbaiki, percobaan "
            f"{seo_fix_attempt}/{MAX_SEO_FIX_ATTEMPTS}")

        seo_fix_prompt = SEO_FIX_PROMPT.format(
            brand_name=brand_name,
            main_keyword=main_keyword,
            missing_description=missing_seo_description,
            current_article_json=json.dumps(article, ensure_ascii=False),
        )

        seo_fixed, sp_t, sc_t = _parse_json_with_retry(
            prompt=seo_fix_prompt,
            system_instruction=BLOG_SYSTEM_INSTRUCTION,
            provider_chain_str=provider_chain_str,
            label=f"Perbaiki keyword '{title_short}'",
            log=log,
            max_tokens=ARTICLE_MAX_TOKENS,
        )
        p_t += sp_t
        c_t += sc_t

        if not isinstance(seo_fixed, dict) or not seo_fixed.get("content"):
            log(f"[Blog Warning] Perbaikan keyword '{title_short}' gagal (respon invalid) "
                f"— hentikan percobaan, pakai versi sebelumnya.")
            break

        article = seo_fixed
        wc = _word_count_html(article["content"])
        if not article.get("seo_title"):
            article["seo_title"] = seo_title or article.get("title", "")[:60]
        seo_ok, seo_missing = _check_seo_requirements(article, main_keyword)

    # ── CTA box — TIDAK di-append di sini. `content` harus tetap bersih dari
    # HTML styling supaya bisa diedit di WYSIWYG editor (halaman review blog
    # autopost) tanpa mengacak style CTA box. cta_headline/cta_button_text/
    # cta_url disimpan di field terpisah dan baru dirender jadi HTML
    # (_build_cta_block) saat deploy — lihat wordpress/blog_deploy.py. ──
    article["cta_headline"] = cta_headline
    article["cta_button_text"] = cta_button_text
    article["cta_url"] = cta_url

    # ── Slug — diperbaiki programatik (deterministik, tidak perlu LLM) ──
    article["slug"] = _ensure_keyword_in_slug(article.get("slug", ""), main_keyword)

    # ── Log akhir kepatuhan keyword utama, setelah semua perbaikan di atas ──
    seo_ok, seo_missing = _check_seo_requirements(article, main_keyword)
    article["_meets_seo_requirements"] = seo_ok
    if not seo_ok:
        log(f"[Blog Warning] '{title_short}' — keyword utama '{main_keyword}' "
            f"tetap tidak ditemukan di: {', '.join(seo_missing)} setelah perbaikan.")

    article["_has_cta"] = bool(cta_url)
    article["_word_count"] = wc
    article["_meets_min_words"] = wc >= min_words
    article["_has_internal_link"] = has_internal
    article["_has_external_link"] = has_external

    return article, p_t, c_t


def generate_blog_batch(
    brand_name: str,
    brand_material: str,
    main_keyword: str,
    secondary_keywords: list[str],
    n_articles: int,
    provider_chain_str: str,
    log: Callable[[str], None] = print,
    on_progress: Optional[Callable[[int, int, str], None]] = None,
    internal_link_candidates: Optional[list[dict]] = None,
    external_links: Optional[list[str]] = None,
    cta_url: str = "",
) -> tuple[list[dict], dict]:
    """
    End-to-end: generate topik → generate tiap artikel.

    Args:
        brand_name        : Contoh "Zecurion", "Cisco", "SAP".
        brand_material    : Raw text hasil `collect_brand_material(...)`.
                            Wajib diisi — kalau kosong, LLM akan mengarang.
        main_keyword      : "[Brand] Indonesia" atau keyword utama lain.
        secondary_keywords: List keyword tambahan.
        n_articles        : Jumlah artikel yang mau dibuat (ditentukan user).
        provider_chain_str: Format "openai,groq" (sama seperti pipeline website).
        log               : Callback log.
        on_progress       : Callback (step_current, step_total, message).
        internal_link_candidates : List {"title","link"} URL milik brand
                            sendiri (halaman statis + post lama), dari
                            WordPressClient.list_pages()/list_posts(). Sama
                            untuk semua artikel dalam batch ini.
        external_links    : List URL eksternal terpercaya input operator
                            (minimal 1 direkomendasikan). Sama untuk semua
                            artikel dalam batch ini — boleh terpakai lebih
                            dari sekali kalau isinya cuma 1-2 URL.
        cta_url            : URL halaman Kontak brand (auto-detect dari
                            WordPress pages). Sama untuk semua artikel dalam
                            batch ini. Kosong → semua artikel tanpa CTA box.

    Returns:
        (articles, token_stats)
    """
    stats = {"prompt_tokens": 0, "completion_tokens": 0}

    if not brand_material or not brand_material.strip():
        log("[Blog Warning] Materi brand KOSONG. LLM akan menulis dari knowledge "
            "training saja — hasil bisa generik atau mengandung fabrikasi. "
            "Sangat disarankan mengisi homepage URL, reference URLs, atau paste "
            "manual content sebelum generate.")

    if not internal_link_candidates:
        log("[Blog Warning] Kandidat link internal KOSONG (tidak ada halaman/post "
            "yang berhasil diambil dari WordPress) — artikel batch ini tidak akan "
            "punya link internal (inbound).")
    if not external_links:
        log("[Blog Warning] Link eksternal KOSONG — artikel batch ini tidak akan "
            "punya link eksternal (outbound). Isi minimal 1 URL referensi terpercaya.")
    if not cta_url:
        log("[Blog Warning] Halaman Kontak tidak ditemukan di WordPress — artikel "
            "batch ini tidak akan punya CTA box.")

    log(f"[Blog] Batch dimulai — brand='{brand_name}', target={n_articles} artikel, "
        f"keyword utama='{main_keyword}', materi={len(brand_material)} char, "
        f"kandidat_internal={len(internal_link_candidates or [])}, "
        f"link_eksternal={len(external_links or [])}.")

    # Step 1: topik
    if on_progress:
        on_progress(0, n_articles + 1, "Generate daftar topik")

    topics, p_t, c_t = generate_topics(
        brand_name=brand_name,
        brand_material=brand_material,
        main_keyword=main_keyword,
        secondary_keywords=secondary_keywords,
        n_topics=n_articles,
        provider_chain_str=provider_chain_str,
        log=log,
    )
    stats["prompt_tokens"] += p_t
    stats["completion_tokens"] += c_t

    if not topics:
        log("[Blog Fatal] Gagal generate topik. Batch dibatalkan.")
        return [], stats

    log(f"[Blog] {len(topics)} topik tersedia. Mulai menulis artikel satu per satu.")

    # Step 2: artikel
    articles: list[dict] = []
    for idx, topic in enumerate(topics, start=1):
        if on_progress:
            on_progress(
                idx, n_articles + 1,
                f"Tulis artikel {idx}/{len(topics)}: {topic.get('title', '')[:40]}"
            )

        article, p_t, c_t = generate_article(
            brand_name=brand_name,
            brand_material=brand_material,
            topic=topic,
            main_keyword=main_keyword,
            secondary_keywords=secondary_keywords,
            provider_chain_str=provider_chain_str,
            log=log,
            internal_link_candidates=internal_link_candidates,
            external_links=external_links,
            cta_url=cta_url,
        )
        stats["prompt_tokens"] += p_t
        stats["completion_tokens"] += c_t

        if article:
            article["_topic_angle"] = topic.get("angle", "")
            article["_topic_target_keyword"] = topic.get("target_keyword", "")
            article["_topic_material_anchor"] = topic.get("material_anchor", "")
            articles.append(article)

    log(f"[Blog] Batch selesai. {len(articles)}/{n_articles} artikel siap deploy.")
    return articles, stats
