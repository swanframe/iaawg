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
)


# ─────────────────────────────────────────────────────────────────────────────
# Konstanta
# ─────────────────────────────────────────────────────────────────────────────

MIN_ARTICLE_WORDS = 1500          # threshold minimum sesuai brief
MAX_PARSE_RETRIES = 3             # jumlah percobaan parse JSON per call
DEFAULT_MAX_CHARS_PER_SOURCE = 4000
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


def _parse_json_with_retry(
    prompt: str,
    system_instruction: str,
    provider_chain_str: str,
    label: str,
    log: Callable[[str], None],
    max_parse_retries: int = MAX_PARSE_RETRIES,
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
        raw, p_t, c_t = llm.generate_content(prompt, system_instruction)
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
) -> tuple[dict, int, int]:
    """
    Generate satu artikel full berbasis materi + brief topik.
    """
    prompt = ARTICLE_GENERATION_PROMPT.format(
        brand_name=brand_name,
        raw_data=brand_material or "(tidak ada materi referensi)",
        title=topic.get("title", ""),
        angle=topic.get("angle", "informational"),
        summary=topic.get("summary", ""),
        main_keyword=main_keyword,
        secondary_keywords=(", ".join(secondary_keywords)
                            if secondary_keywords else "(tidak ada)"),
    )

    article, p_t, c_t = _parse_json_with_retry(
        prompt=prompt,
        system_instruction=BLOG_SYSTEM_INSTRUCTION,
        provider_chain_str=provider_chain_str,
        label=f"Tulis artikel '{topic.get('title', '')[:40]}'",
        log=log,
    )

    if not isinstance(article, dict) or not article.get("content"):
        return {}, p_t, c_t

    wc = _word_count_html(article["content"])
    article["_word_count"] = wc
    article["_meets_min_words"] = wc >= min_words

    if wc < min_words:
        log(f"[Blog Warning] '{article.get('title', '')[:40]}' hanya {wc} kata "
            f"(minimum {min_words}). Artikel tetap disimpan — pertimbangkan "
            f"regenerate atau tambah materi referensi.")
    else:
        log(f"[Blog] '{article.get('title', '')[:40]}' — {wc} kata ✓")

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

    Returns:
        (articles, token_stats)
    """
    stats = {"prompt_tokens": 0, "completion_tokens": 0}

    if not brand_material or not brand_material.strip():
        log("[Blog Warning] Materi brand KOSONG. LLM akan menulis dari knowledge "
            "training saja — hasil bisa generik atau mengandung fabrikasi. "
            "Sangat disarankan mengisi homepage URL, reference URLs, atau paste "
            "manual content sebelum generate.")

    log(f"[Blog] Batch dimulai — brand='{brand_name}', target={n_articles} artikel, "
        f"keyword utama='{main_keyword}', materi={len(brand_material)} char.")

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
