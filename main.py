import os
import sys
import argparse
import asyncio
import json
import re
import httpx
from collections import defaultdict
from crawler.scraper import BaseScraper, ContentExtractor
from content.generator import get_llm_provider
from content.templates.prompts import SYSTEM_INSTRUCTION, PAGE_PROMPTS, PRODUCT_INDIVIDUAL_PROMPT, PRODUCT_CATALOG_PROMPT
from wordpress.client import WordPressClient
from wordpress.page_builder import PageBuilder
from config.settings import get_max_products

# Import modul Phase 3 — Visual & Design
from visual.color_extractor import ColorExtractor
from visual.banner_gen import get_image_provider
from visual.image_fetch import StockImageFetcher
from visual.preview_templates import select_template as _select_template

# Import Elementor builder functions
from wordpress.elementor_builder import (
    build_home,
    build_produk_index,
    build_solusi,
    build_contact,
    build_product_page,
    build_global_header,
    build_global_footer,
    build_catalog_overview,        # ← Catalog Mode
    build_catalog_category_page,   # ← Catalog Mode
)
from wordpress.smartslider_deploy import orchestrate_slider_deploy

# Provider names supported by the failover engine (used for JSON-parse retry)
_ALL_PROVIDERS = ["openai", "groq"]


def _generate_with_json_retry(
    prompt: str,
    system_instruction: str,
    provider_chain_str: str,
    label: str = "halaman",
    max_parse_retries: int = 3,
) -> tuple[dict, int, int]:
    """
    Memanggil LLM, lalu mencoba memparsing hasilnya sebagai JSON.
    Jika parsing gagal, secara otomatis memanggil ulang menggunakan
    provider cadangan berikutnya dalam rantai failover — hingga
    `max_parse_retries` kali.

    Mengembalikan (parsed_dict, total_prompt_tokens, total_completion_tokens).
    Jika seluruh percobaan gagal, mengembalikan ({}, 0, 0) sehingga
    pemanggil dapat menanganinya sebagai kegagalan eksplisit.
    """
    # Susun urutan provider untuk retry: mulai dari chain utama,
    # lalu tambahkan provider lain yang belum dicoba.
    chain = [p.strip().lower() for p in provider_chain_str.split(",") if p.strip()]
    extras = [p for p in _ALL_PROVIDERS if p not in chain]
    retry_providers = (chain + extras)[:max_parse_retries]

    total_p = total_c = 0

    for attempt, provider_name in enumerate(retry_providers, start=1):
        llm_attempt = get_llm_provider(provider_name)
        raw, p_t, c_t = llm_attempt.generate_content(prompt, system_instruction)
        total_p += p_t
        total_c += c_t
        print(f"[TOKEN_USAGE] Prompt: {p_t} | Completion: {c_t}")

        json_match = re.search(r"\{.*\}", raw, re.DOTALL)
        clean_str  = json_match.group(0) if json_match else raw.strip()

        try:
            data = json.loads(clean_str, strict=False)
            if attempt > 1:
                print(f"    [✓] JSON berhasil diparsing pada percobaan ke-{attempt} menggunakan {provider_name.upper()}.")
            return data, total_p, total_c
        except Exception:
            print(
                f"    [!] Gagal parse JSON untuk {label} "
                f"(percobaan {attempt}/{max_parse_retries}, provider: {provider_name.upper()}). "
                f"{'Mencoba provider cadangan berikutnya...' if attempt < len(retry_providers) else 'Seluruh provider habis.'}"
            )

    return {}, total_p, total_c


async def run_pipeline(
    brand: str,
    url: str,
    skip_generation: bool,
    custom_creds: dict = None,
    skip_deploy: bool = False,
    product_urls: list = None,
    llm_provider: str = None,
    primary_color: str = "#1E7E34",
    template_name: str = "prestige",
    product_mode: str = "individual",
    catalog_groups: list = None,   # [{"category": "Router", "urls": [...]}]
    homepage_manual_content: str = "",              # ← bypass scraper untuk homepage
    product_manual_contents: dict = None,           # ← {url: raw_text} bypass scraper per-URL
    append_mode: bool = False,                      # ← Append Mode: tambah produk ke site existing
):
    """
    Eksekusi Pipeline Utama iAAWG.
    Menerima parameter opsional `custom_creds` dari Web UI dan `skip_deploy` untuk Local Draft Mode.
    Jika `product_urls` diberikan (list URL produk), maka sistem akan mengabaikan ekstraksi produk dari homepage
    dan hanya memproses produk dari URL tersebut (Individual Mode).
    Jika `catalog_groups` diberikan, setiap group berisi category name + URL list (Catalog Mode).
    `primary_color` adalah warna utama (HEX) yang diambil dari logo atau default iLogo.

    ── Manual Content Override (bypass scraper) ─────────────────────────────
    `homepage_manual_content` (str, opsional):
        Teks mentah homepage yang di-paste operator via Web UI. Jika diisi,
        sistem TIDAK akan melakukan scraping ke `url` — teks ini langsung
        dipakai sebagai sumber halaman statis (home/solusi/contact/produk-fallback).
        Berguna ketika target diblokir Cloudflare atau WAF lainnya.

    `product_manual_contents` (dict[str, str], opsional):
        Mapping {url: raw_text} — untuk setiap URL produk yang memiliki entry
        di dict ini, scraper akan dilewati dan teks operator langsung dipakai.
        URL yang tidak ada di dict tetap di-scrape seperti biasa. Berlaku
        untuk Individual Mode maupun Catalog Mode (grup katalog).

    ── Append Mode ──────────────────────────────────────────────────────────
    `append_mode` (bool, default False):
        Jika True, pipeline HANYA memproses URL produk baru dan menambahkannya
        ke site yang sudah ada. Yang di-skip:
          - Scraping / manual content untuk homepage
          - Generate & deploy halaman Home / Solusi / Contact
          - Contact Form 7 (asumsi sudah dibuat pada deploy awal)
          - Halaman induk /produk/ (asumsi sudah ada)
          - ElementsKit Global Header & Footer (agar tidak duplikat)
          - Smart Slider 3 (agar tidak duplikat)
        Yang TETAP jalan:
          - Generate konten LLM per produk baru
          - Generate visual per produk baru
          - Upload media dan create_page per produk baru
          - Update nav menu (append child baru di bawah item "Produk" existing;
            item lama tetap utuh)
        Syarat: `product_urls` wajib berisi minimal 1 URL. Catalog Mode belum
        didukung di Append Mode karena melibatkan halaman kategori (yang bisa
        duplikat dengan yang sudah ada) — gunakan Individual Mode.
    """
    # ── Validasi Append Mode: fail-fast dengan pesan yang jelas ──────────────
    if append_mode:
        if product_mode == "catalog":
            print("[X] Append Mode belum mendukung Catalog Mode. Gunakan Individual Mode (URL produk).")
            return
        if not product_urls:
            print("[X] Append Mode wajib menyertakan minimal 1 URL produk baru.")
            return
        if skip_deploy:
            print("[X] Append Mode tidak kompatibel dengan Local Draft Only — tujuannya justru meng-update site production.")
            return
        # Append Mode implicitly requires generation (produk baru = konten baru).
        # skip_generation di sini tidak ada gunanya, tapi tidak dilarang keras
        # kalau operator benar-benar sudah punya JSON lokal produk.
    # Normalisasi dict manual content agar lookup by-URL konsisten
    # (trim + strip trailing slash) — mengikuti pola URL scrape_url().
    product_manual_contents = product_manual_contents or {}
    homepage_manual_content = (homepage_manual_content or "").strip()

    def _norm_url_key(u: str) -> str:
        return (u or "").strip().rstrip("/").lower()

    _manual_lookup = {
        _norm_url_key(k): (v or "") for k, v in product_manual_contents.items()
        if k and (v or "").strip()
    }

    def _get_manual_for_url(u: str) -> str:
        """Return manual content untuk URL, atau string kosong jika tidak ada."""
        return _manual_lookup.get(_norm_url_key(u), "")
    print(f"\n[*] Memulai iAAWG Pipeline untuk Brand: {brand.upper()}")
    if skip_deploy:
        print("[*] MODE: LOCAL DRAFT ONLY (Tanpa Deploy ke WordPress)")
    if catalog_groups and product_mode == "catalog":
        total_urls = sum(len(g.get("urls", [])) for g in catalog_groups)
        print(f"[*] MODE: KATALOG — {len(catalog_groups)} kategori, {total_urls} URL produk, deploy per kategori")
    elif product_urls:
        print(f"[*] MODE: PRODUK INDIVIDUAL — {len(product_urls)} URL produk")
    print(f"[*] Warna utama brand: {primary_color}")
    print(f"[*] Template Elementor: {template_name}")
    if homepage_manual_content:
        print(f"[*] MANUAL CONTENT: homepage di-bypass scraper ({len(homepage_manual_content)} karakter mentah)")
    if _manual_lookup:
        print(f"[*] MANUAL CONTENT: {len(_manual_lookup)} URL produk di-bypass scraper")

    # Read the operator-configured product limit once per pipeline run.
    # This reads from DB → .env → default (5), with a hard cap of 10.
    max_products = get_max_products()
    print(f"[*] Batas maksimum produk: {max_products}")

    output_dir = os.path.join("output", brand.lower(), "content")
    visual_dir = os.path.join("output", brand.lower(), "visual")

    # Halaman statis utama (home, solusi, contact) — produk ditangani terpisah
    static_pages = ["home", "solusi", "contact"]
    all_pages    = ["home", "produk", "solusi", "contact"]  # untuk backward compatibility baca JSON

    generated_pages_data    = {}   # data halaman statis {page_type: data}
    generated_products_data = []   # list data tiap produk individual

    # =========================================================================
    # OPSI 1: FULL PIPELINE (CRAWL + GENERATE CONTENT LLM)
    # =========================================================================
    if not skip_generation:
        # Scraper diinisialisasi sekali untuk homepage + semua produk. Instance
        # yang sama dipakai kembali di path katalog / individual untuk efisiensi.
        scraper = BaseScraper()

        # Semua branch di bawah butuh output_dir siap — bikin sekali di sini
        # daripada mengulang os.makedirs di setiap branch/guard.
        os.makedirs(output_dir, exist_ok=True)

        # ── APPEND MODE: skip homepage sama sekali ──────────────────────────
        # Homepage sudah pernah di-generate di deploy sebelumnya. Kita hanya
        # butuh cleaned_text sebagai placeholder minimal supaya tidak crash
        # di path selanjutnya (walau isinya tidak akan dipakai untuk generate
        # halaman statis, karena blok itu di-skip saat append_mode).
        # Kita juga preload home.json dari cache lokal jika ada — dibutuhkan
        # untuk cta_button_text saat build_product_page().
        if append_mode:
            print("[1/4] APPEND MODE — melewati scraping homepage (produk baru saja yang diproses).")
            cleaned_text = "APPEND MODE — homepage tidak diproses ulang."
            _home_json_path = os.path.join(output_dir, "home.json")
            if os.path.exists(_home_json_path):
                try:
                    with open(_home_json_path, "r", encoding="utf-8") as _f:
                        generated_pages_data["home"] = json.load(_f)
                    print(f"    [✓] Cache home.json ditemukan — cta_button_text akan diambil dari sana.")
                except Exception as _e:
                    print(f"    [!] Gagal membaca cache home.json: {_e} — akan pakai default cta_button_text.")
                    generated_pages_data["home"] = {"cta_button_text": "Hubungi Kami"}
            else:
                print("    [!] Cache home.json tidak ada — cta_button_text akan pakai default 'Hubungi Kami'.")
                generated_pages_data["home"] = {"cta_button_text": "Hubungi Kami"}

            # Defense-in-depth: cache mungkin ada tapi key-nya kosong/hilang karena
            # generate LLM waktu itu partial atau file di-edit manual. Tanpa guard
            # ini, deploy produk akan crash di raise ValueError.
            if not generated_pages_data["home"].get("cta_button_text"):
                generated_pages_data["home"]["cta_button_text"] = "Hubungi Kami"
                print("    [!] cta_button_text kosong di cache — fallback ke 'Hubungi Kami'.")

        # ── HOMEPAGE: Manual Content Override atau Scraping ──────────────────
        elif homepage_manual_content:
            print("[1/4] MODE MANUAL — menggunakan konten homepage yang di-paste operator (bypass scraper)...")
            cleaned_text = ContentExtractor.clean_manual_text(homepage_manual_content)
            source_label = "MANUAL_CONTENT"
            print(f"    [✓] Konten manual dibersihkan: {len(cleaned_text)} karakter siap proses.")
        else:
            print(f"[*] URL Homepage Target: {url}")
            print("[1/4] Mengunduh & mengekstrak konten website referensi (homepage)...")
            raw_html     = await scraper.scrape_url(url)
            cleaned_text = ContentExtractor.clean_html(raw_html)
            source_label = url

        # Semua guard di bawah ini menyangkut konten homepage — dilewati saat
        # append_mode karena homepage memang tidak diproses ulang.
        if not append_mode:
            # ── GUARD 1: Simpan teks (manual atau scraping) untuk audit & debugging ──
            # File ini memungkinkan Anda melihat persis teks apa yang dikirim ke LLM.
            debug_path = os.path.join(output_dir, "scraped_debug.txt")
            with open(debug_path, "w", encoding="utf-8") as dbg:
                dbg.write(f"SOURCE: {source_label}\n{'=' * 60}\n{cleaned_text}")
            print(f"    [📄] Teks referensi disimpan di: {debug_path}")

            # ── GUARD 2: Tolak halaman Cloudflare/bot-wall sebelum masuk LLM ─────
            # Guard ini HANYA berlaku untuk hasil scraping. Manual content di-trust
            # karena operator sudah secara eksplisit menyediakan konten asli.
            if not homepage_manual_content and ContentExtractor.is_bot_wall(cleaned_text):
                print("[❌] Terdeteksi halaman Cloudflare challenge / bot-wall.")
                print("[!]  Pipeline dihentikan. Cek file scraped_debug.txt untuk konfirmasi.")
                print("[!]  Saran: gunakan fitur Manual Content di Web UI untuk mem-paste konten homepage secara manual.")
                return

            # Validasi ambang batas 500 karakter teks bersih (berlaku untuk kedua sumber)
            MIN_CHARACTERS = 500
            if not cleaned_text or len(cleaned_text) < MIN_CHARACTERS:
                print(f"[X] Error: Konten referensi terlalu sedikit ({len(cleaned_text)} karakter).")
                print(f"[X] Gagal memenuhi batas minimum {MIN_CHARACTERS} karakter bersih. Pipeline dihentikan untuk mencegah halusinasi LLM.")
                if homepage_manual_content:
                    print("[!] Silakan tempel konten homepage yang lebih lengkap pada kolom Manual Content.")
                return
            else:
                print(f"[✓] Berhasil menyiapkan {len(cleaned_text)} karakter teks bersih (Layak proses).")

        # 2. Inisialisasi LLM Provider
        print("[2/4] Menghubungkan ke LLM Provider Failover Engine...")
        try:
            llm = get_llm_provider(llm_provider)
        except Exception as e:
            print(f"[X] Gagal inisialisasi LLM: {e}")
            return

        # 3. Generate Konten untuk halaman statis (home, solusi, contact)
        # Dilewati saat append_mode — halaman statis sudah pernah dideploy
        # sebelumnya dan tidak diproses ulang di mode ini.
        if append_mode:
            print("[3/4] APPEND MODE — melewati generate halaman statis (home, solusi, contact).")
        else:
            print("[3/4] Menghasilkan konten halaman statis (home, solusi, contact)...")

            for index, page in enumerate(static_pages):
                print(f"    -> Memproses halaman: {page.upper()}...")
                formatted_prompt = PAGE_PROMPTS[page].format(raw_data=cleaned_text[:6000], brand_name=brand)

                page_data, p_tokens, c_tokens = _generate_with_json_retry(
                    prompt=formatted_prompt,
                    system_instruction=SYSTEM_INSTRUCTION,
                    provider_chain_str=llm_provider or "openai",
                    label=page,
                )

                if not page_data:
                    print(f"    [X] Seluruh provider gagal menghasilkan JSON valid untuk halaman {page.upper()}. Halaman dilewati.")
                    continue

                page_data["_brand_name"]   = brand  # used by Elementor footer section
                generated_pages_data[page] = page_data

                file_path = os.path.join(output_dir, f"{page}.json")
                with open(file_path, "w", encoding="utf-8") as out_file:
                    json.dump(page_data, out_file, indent=4, ensure_ascii=False)

        # =============================================================
        # GENERATE PRODUK
        # =============================================================

        # ── PATH A: Catalog Mode — kategori dari operator input ──────────────
        if catalog_groups and product_mode == "catalog":
            print(f"\n[*] Memproses {len(catalog_groups)} kategori produk (Catalog Mode — kategori dari input operator)...")
            url_counter = 0

            for group in catalog_groups:
                cat_name = (group.get("category") or "Produk").strip() or "Produk"
                urls = group.get("urls", [])
                print(f"\n    [*] Kategori: '{cat_name}' ({len(urls)} URL)")

                for prod_url in urls:
                    if url_counter >= max_products:
                        print(f"    [!] Batas maksimum produk ({max_products}) tercapai. Sisa URL dilewati.")
                        break

                    # ── Sumber konten: manual paste (bypass scraper) atau scraping ──
                    manual_txt = _get_manual_for_url(prod_url)
                    if manual_txt:
                        print(f"    [~] MANUAL — memakai konten yang di-paste operator untuk: {prod_url}")
                        prod_cleaned = ContentExtractor.clean_manual_text(manual_txt)
                    else:
                        print(f"    [~] Mengunduh halaman produk: {prod_url}")
                        await asyncio.sleep(5)
                        prod_raw_html = await scraper.scrape_url(prod_url)
                        prod_cleaned  = ContentExtractor.clean_html(prod_raw_html)

                    if not prod_cleaned or len(prod_cleaned) < 200:
                        print(f"    [!] Konten produk terlalu sedikit ({len(prod_cleaned)} karakter), dilewati.")
                        continue

                    # ← Catalog Mode menggunakan prompt ringkas
                    prompt_prod = PRODUCT_CATALOG_PROMPT.format(raw_data=prod_cleaned[:6000])
                    prod_data, p_t, c_t = _generate_with_json_retry(
                        prompt=prompt_prod,
                        system_instruction=SYSTEM_INSTRUCTION,
                        provider_chain_str=llm_provider or "openai",
                        label=f"produk ({cat_name})",
                    )

                    if not prod_data:
                        print(f"    [X] Seluruh provider gagal menghasilkan JSON valid untuk {prod_url}. Dilewati.")
                        continue

                    url_counter += 1

                    # Pastikan field wajib terisi
                    if "name" not in prod_data:
                        prod_data["name"] = f"Produk {url_counter}"
                    if "slug" not in prod_data:
                        prod_data["slug"] = f"produk-{url_counter}"
                    if "seo_keywords" not in prod_data:
                        prod_data["seo_keywords"] = ["teknologi", brand.lower()]

                    # Kategori dari operator — tidak perlu ekstraksi dari URL
                    prod_data["category"]    = cat_name
                    prod_data["_brand_name"] = brand

                    generated_products_data.append(prod_data)
                    print(f"    [✓] Berhasil generate produk: {prod_data['name']} [{cat_name}]")

            if generated_products_data:
                produk_index_data = {
                    "title":                  "Produk & Solusi Kami",
                    "intro_page_title":       "Produk & Solusi Kami",
                    "intro_page_description": f"Berikut adalah produk-produk unggulan dari {brand}.",
                    "products_list":          generated_products_data,
                    "seo_keywords":           ["produk", brand.lower()],
                    "_brand_name":            brand,
                }
                generated_pages_data["produk"] = produk_index_data
                produk_file = os.path.join(output_dir, "produk.json")
                with open(produk_file, "w", encoding="utf-8") as f:
                    json.dump(produk_index_data, f, indent=4, ensure_ascii=False)
                print(f"[✓] Halaman induk produk dibuat dari {len(generated_products_data)} produk ({url_counter} berhasil diproses).")
            else:
                print("[!] Tidak ada produk berhasil digenerate dari grup katalog yang diberikan.")
                generated_pages_data["produk"] = {
                    "title":                  "Produk",
                    "intro_page_title":       "Produk",
                    "intro_page_description": "",
                    "products_list":          [],
                    "seo_keywords":           ["produk", brand.lower()],
                    "_brand_name":            brand,
                }

        # ── PATH B: Individual Mode — URL produk eksplisit ───────────────────
        elif product_urls:
            print("\n[*] Memproses URL produk yang diberikan secara eksplisit (Individual Mode)...")
            # Apply max_products cap to explicit URL list as well —
            # without this, entering 20 URLs would deploy 20 product pages.
            for idx, prod_url in enumerate(product_urls[:max_products]):
                # ── Sumber konten: manual paste (bypass scraper) atau scraping ──
                manual_txt = _get_manual_for_url(prod_url)
                if manual_txt:
                    print(f"    [~] MANUAL — memakai konten yang di-paste operator untuk produk #{idx+1}: {prod_url}")
                    prod_cleaned = ContentExtractor.clean_manual_text(manual_txt)
                else:
                    print(f"    [~] Mengunduh halaman produk #{idx+1}: {prod_url}")
                    await asyncio.sleep(5)  # jeda antar request scraper
                    prod_raw_html = await scraper.scrape_url(prod_url)
                    prod_cleaned  = ContentExtractor.clean_html(prod_raw_html)

                if not prod_cleaned or len(prod_cleaned) < 200:
                    print(f"    [!] Konten produk terlalu sedikit ({len(prod_cleaned)}), dilewati.")
                    continue

                prompt_prod = PRODUCT_INDIVIDUAL_PROMPT.format(raw_data=prod_cleaned[:6000])
                prod_data, p_t, c_t = _generate_with_json_retry(
                    prompt=prompt_prod,
                    system_instruction=SYSTEM_INSTRUCTION,
                    provider_chain_str=llm_provider or "openai",
                    label=f"produk #{idx+1}",
                )

                if not prod_data:
                    print(f"    [X] Seluruh provider gagal menghasilkan JSON valid untuk produk dari {prod_url}. Dilewati.")
                    continue

                if "name" not in prod_data:
                    prod_data["name"] = f"Produk {idx+1}"
                if "slug" not in prod_data:
                    prod_data["slug"] = f"produk-{idx+1}"
                if "seo_keywords" not in prod_data:
                    prod_data["seo_keywords"] = ["teknologi", brand.lower()]
                prod_data["_brand_name"] = brand

                generated_products_data.append(prod_data)
                print(f"    [✓] Berhasil generate produk: {prod_data['name']}")

            if generated_products_data:
                produk_index_data = {
                    "title":                  "Produk & Solusi Kami",
                    "intro_page_title":       "Produk & Solusi Kami",
                    "intro_page_description": f"Berikut adalah produk-produk unggulan dari {brand}.",
                    "products_list":          generated_products_data,
                    "seo_keywords":           ["produk", brand.lower()],
                    "_brand_name":            brand,
                }
                generated_pages_data["produk"] = produk_index_data
                produk_file = os.path.join(output_dir, "produk.json")
                with open(produk_file, "w", encoding="utf-8") as f:
                    json.dump(produk_index_data, f, indent=4, ensure_ascii=False)
                print(f"[✓] Halaman induk produk dibuat dari {len(generated_products_data)} produk.")
            else:
                print("[!] Tidak ada produk berhasil digenerate dari URL yang diberikan.")
                generated_pages_data["produk"] = {
                    "title":                  "Produk",
                    "intro_page_title":       "Produk",
                    "intro_page_description": "",
                    "products_list":          [],
                    "seo_keywords":           ["produk", brand.lower()],
                    "_brand_name":            brand,
                }

        # ── PATH C: Tidak ada URL produk — generate dari homepage ────────────
        else:
            # Mode lama: generate halaman "produk" dari homepage
            print("\n[*] Menghasilkan konten halaman produk (induk) dari homepage...")
            prompt_produk = PAGE_PROMPTS["produk"].format(
                raw_data=cleaned_text[:6000],
                brand_name=brand,
                max_products=max_products,
            )
            produk_data, p_t, c_t = _generate_with_json_retry(
                prompt=prompt_produk,
                system_instruction=SYSTEM_INSTRUCTION,
                provider_chain_str=llm_provider or "openai",
                label="produk (induk)",
            )

            if not produk_data:
                print("    [X] Seluruh provider gagal menghasilkan JSON valid untuk halaman produk. Menggunakan data kosong.")
                produk_data = {
                    "title":                  "Produk",
                    "intro_page_title":       "Produk & Solusi Kami",
                    "intro_page_description": "",
                    "products_list":          [],
                    "seo_keywords":           ["produk", brand.lower()]
                }
            produk_data["_brand_name"]     = brand
            generated_pages_data["produk"] = produk_data
            produk_file = os.path.join(output_dir, "produk.json")
            with open(produk_file, "w", encoding="utf-8") as f:
                json.dump(produk_data, f, indent=4, ensure_ascii=False)

            raw_products = produk_data.get("products_list", [])
            if raw_products:
                limited_products = raw_products[:max_products]
                for prod in limited_products:
                    prod["_brand_name"] = brand
                    generated_products_data.append(prod)
                print(f"[✓] Ditemukan {len(generated_products_data)} produk utama dari data LLM (maks {max_products}).")
            else:
                print("[!] Warning: Tidak ada products_list yang ditemukan di data produk. Halaman produk individual tidak akan di-deploy.")

        print(f"[✓] Selesai! Konten teks lokal berhasil disimpan di folder: `{output_dir}`")

    # =========================================================================
    # OPSI 2: SKIP GENERATION (MEMANFAATKAN DATA JSON LOKAL YANG SUDAH ADA)
    # =========================================================================
    else:
        print(f"[*] [Opsi Skip Generation Aktif] Membaca data JSON lokal dari folder: `{output_dir}`")
        if not os.path.exists(output_dir):
            print(f"[X] Error: Folder output `{output_dir}` tidak ditemukan. Anda harus menjalankan full pipeline minimal sekali terlebih dahulu.")
            return

        for page in all_pages:
            file_path = os.path.join(output_dir, f"{page}.json")
            if not os.path.exists(file_path):
                print(f"[X] Error: File pendukung `{page}.json` tidak ditemukan di folder output.")
                return
            with open(file_path, "r", encoding="utf-8") as f:
                try:
                    generated_pages_data[page] = json.load(f)
                    print(f"    [✓] Berhasil memuat: {page}.json")
                except Exception as e:
                    print(f"[X] Gagal membaca berkas JSON `{page}.json`: {e}")
                    return

        produk_data  = generated_pages_data.get("produk", {})
        raw_products = produk_data.get("products_list", [])
        if raw_products:
            for prod in raw_products[:max_products]:
                prod["_brand_name"] = brand
                generated_products_data.append(prod)
            print(f"[✓] Ditemukan {len(generated_products_data)} produk dari JSON lokal (maks {max_products}).")
        else:
            print("[!] Tidak ada produk dalam data JSON.")

    # =========================================================================
    # Phase 2 — Visual Generation (Person A: skip_deploy=True)
    # Hanya dijalankan saat BUKAN skip_generation.
    # Person A menghasilkan semua gambar dan menyimpannya ke folder visual/.
    # =========================================================================
    if not skip_generation:
        print("\n[4/4] Memulai Visual Generation & Penyimpanan Lokal...")
        os.makedirs(visual_dir, exist_ok=True)

        try:
            img_provider  = get_image_provider()
            stock_fetcher = StockImageFetcher()
            llm_helper    = get_llm_provider(llm_provider)
        except ValueError as e:
            print(f"[X] Gagal inisialisasi Visual Provider: {e}")
            return

        # A. Halaman statis (home, solusi, contact)
        # Dilewati saat append_mode — banner & stock photo untuk halaman
        # statis sudah pernah di-upload di deploy sebelumnya.
        if append_mode:
            print("\n[*] APPEND MODE — melewati visual untuk halaman statis (home, solusi, contact).")
            static_iter = []
        else:
            static_iter = list(enumerate(static_pages))
        for index, page_type in static_iter:
            data = generated_pages_data.get(page_type, {})
            if not data:
                continue
            print(f"\n[*] Memproses Visual untuk Halaman: {page_type.upper()}")
            if index > 0:
                await asyncio.sleep(5)

            headline_desc  = data.get("hero_headline", data.get("title", f"Solutions for {brand}"))
            search_keyword = (data.get("seo_keywords", []) or ["technology"])[0]

            print("    [~] Mengonversi kata kunci visual ke Bahasa Inggris via LLM Mikro...")
            translate_prompt = (
                f"Translate this topic or text into only 2 to 4 clean English generic technology "
                f"keywords for stock photo search. Text: '{headline_desc} / {search_keyword}'. "
                f"Output only the English keywords, nothing else."
            )
            english_visual_keyword, p_tokens, c_tokens = llm_helper.generate_content(
                translate_prompt, "You are a precise translator. Output only English keywords."
            )
            print(f"    [TOKEN_USAGE] Prompt: {p_tokens} | Completion: {c_tokens}")
            english_visual_keyword = english_visual_keyword.strip().replace('"', '') or "cybersecurity technology"
            if len(english_visual_keyword) > 60:
                english_visual_keyword = "cybersecurity technology"
            print(f"    [✓] Keyword Visual (English): '{english_visual_keyword}'")

            print("    -> Membuat banner AI...")
            banner_bytes = await img_provider.generate_banner(prompt_desc=english_visual_keyword, brand_name=brand)
            if banner_bytes:
                banner_path = os.path.join(visual_dir, f"{brand}_{page_type}_banner.jpg")
                with open(banner_path, "wb") as fb:
                    fb.write(banner_bytes)
                print(f"    [✓] Banner disimpan: {banner_path}")

            print("    -> Mencari stock photo Unsplash...")
            stock_raw_url = await stock_fetcher.fetch_stock_url(english_visual_keyword)
            if stock_raw_url:
                async with httpx.AsyncClient() as client:
                    try:
                        res_img = await client.get(stock_raw_url)
                        if res_img.status_code == 200:
                            stock_path = os.path.join(visual_dir, f"{brand}_{page_type}_stock.jpg")
                            with open(stock_path, "wb") as fs:
                                fs.write(res_img.content)
                            print(f"    [✓] Stock photo disimpan: {stock_path}")
                    except Exception as e:
                        print(f"    [!] Gagal memproses stock photo: {e}")

        # B. Halaman induk produk (di-skip di append_mode) + setiap produk individual
        if generated_products_data:
            if append_mode:
                print("\n[*] APPEND MODE — melewati visual untuk halaman induk PRODUK.")
            else:
                print(f"\n[*] Memproses Visual untuk Halaman Induk: PRODUK")
                await asyncio.sleep(5)
                produk_kw = (generated_pages_data.get("produk", {}).get("seo_keywords", []) or ["technology"])[0]
                translate_p = (
                    f"Translate this topic into 2-4 clean English keywords for stock photo search: "
                    f"'{produk_kw}'. Output only the English keywords."
                )
                en_kw_produk, pt, ct = llm_helper.generate_content(
                    translate_p, "You are a precise translator. Output only English keywords."
                )
                print(f"    [TOKEN_USAGE] Prompt: {pt} | Completion: {ct}")
                en_kw_produk = en_kw_produk.strip().replace('"', '') or "software products technology"

                banner_bytes_idx = await img_provider.generate_banner(prompt_desc=en_kw_produk, brand_name=brand)
                if banner_bytes_idx:
                    with open(os.path.join(visual_dir, f"{brand}_produk_banner.jpg"), "wb") as fb:
                        fb.write(banner_bytes_idx)
                    print("    [✓] Banner produk index disimpan.")

                stock_idx_url_raw = await stock_fetcher.fetch_stock_url(en_kw_produk)
                if stock_idx_url_raw:
                    async with httpx.AsyncClient() as cl:
                        try:
                            ri = await cl.get(stock_idx_url_raw)
                            if ri.status_code == 200:
                                with open(os.path.join(visual_dir, f"{brand}_produk_stock.jpg"), "wb") as fs:
                                    fs.write(ri.content)
                                print("    [✓] Stock photo produk index disimpan.")
                        except Exception as e:
                            print(f"    [!] Gagal memproses stock photo produk index: {e}")

            # Loop visual per-produk tetap jalan (baik append_mode maupun full)
            for prod_index, prod_data in enumerate(generated_products_data):
                prod_name = prod_data.get("name", f"Produk {prod_index + 1}")
                prod_slug = prod_data.get("slug", f"produk-{prod_index + 1}")
                print(f"\n[*] Memproses Visual untuk Produk: {prod_name}")
                await asyncio.sleep(5)

                prod_headline = prod_data.get("tagline", prod_name)
                prod_kw       = (prod_data.get("seo_keywords", []) or ["technology product"])[0]
                translate_prod = (
                    f"Translate this product topic into 2-4 clean English keywords for stock photo search: "
                    f"'{prod_headline} / {prod_kw}'. Output only English keywords."
                )
                en_kw_prod, pt2, ct2 = llm_helper.generate_content(
                    translate_prod, "You are a precise translator. Output only English keywords."
                )
                print(f"    [TOKEN_USAGE] Prompt: {pt2} | Completion: {ct2}")
                en_kw_prod = en_kw_prod.strip().replace('"', '') or "technology software"
                print(f"    [✓] Keyword Visual Produk (English): '{en_kw_prod}'")

                prod_banner_bytes = await img_provider.generate_banner(prompt_desc=en_kw_prod, brand_name=brand)
                if prod_banner_bytes:
                    with open(os.path.join(visual_dir, f"{brand}_{prod_slug}_banner.jpg"), "wb") as fb:
                        fb.write(prod_banner_bytes)
                    print("    [✓] Banner produk disimpan.")

                prod_stock_raw = await stock_fetcher.fetch_stock_url(en_kw_prod)
                if prod_stock_raw:
                    async with httpx.AsyncClient() as client:
                        try:
                            res_prod_img = await client.get(prod_stock_raw)
                            if res_prod_img.status_code == 200:
                                with open(os.path.join(visual_dir, f"{brand}_{prod_slug}_stock.jpg"), "wb") as fs:
                                    fs.write(res_prod_img.content)
                                print("    [✓] Stock photo produk disimpan.")
                        except Exception as e:
                            print(f"    [!] Gagal memproses stock photo produk: {e}")

        print(f"\n[✓] Semua aset visual berhasil disimpan di: {visual_dir}")

        if skip_deploy:
            print("[*] MODE Local Only — selesai. Tidak ada yang di-deploy ke WordPress.")
            print(f"[✓] Seluruh Pipeline iAAWG (Local Only) Selesai! Output: output/{brand.lower()}/")
            return

    # =========================================================================
    # Phase 3 — Deploy ke WordPress (Person B: skip_generation=True)
    # Membaca semua file lokal yang sudah disiapkan Person A,
    # lalu mengupload ke WordPress. Tidak ada LLM / Pollinations / Unsplash.
    # =========================================================================
    # ── Resolve template "auto" sebelum deploy ────────────────────────────────
    _VALID_TEMPLATES = {"prestige", "clarity", "momentum"}
    if template_name not in _VALID_TEMPLATES:
        resolved_template = _select_template({
            "home":    generated_pages_data.get("home", {}),
            "produk":  generated_pages_data.get("produk", {}),
            "solusi":  generated_pages_data.get("solusi", {}),
            "contact": generated_pages_data.get("contact", {}),
        }, brand)
        print(f"[*] Template otomatis dipilih untuk deploy: '{resolved_template}'")
    else:
        resolved_template = template_name
    # ─────────────────────────────────────────────────────────────────────────

    print("\n[4/4] Memulai Deploy ke WordPress...")

    try:
        if custom_creds:
            wp_client = WordPressClient(
                url=custom_creds.get("wp_url"),
                username=custom_creds.get("wp_username"),
                app_password=custom_creds.get("wp_app_password")
            )
        else:
            wp_client = WordPressClient()
    except ValueError as e:
        print(f"[X] Gagal inisialisasi WordPress Client: {e}")
        print("[!] Silakan lengkapi konfigurasi .env atau isi formulir WordPress Web UI Anda.")
        return

    def _read_image(path: str) -> bytes:
        """Baca file gambar lokal. Kembalikan bytes kosong jika tidak ada."""
        if os.path.exists(path):
            with open(path, "rb") as f:
                return f.read()
        print(f"    [!] File gambar tidak ditemukan, dilewati: {path}")
        return b""

    # URL kontak diprediksi dari base_url + slug kontak yang selalu tetap.
    # Digunakan sebagai link tombol CTA di semua halaman (home, solusi)
    # sebelum halaman contact selesai dideploy.
    contact_url = f"{wp_client.base_url}/contact/"

    # ── [CF7] Buat Contact Form 7 — ID dipakai saat build_contact ────────────
    # CF7 harus sudah terinstall di WordPress target. Jika gagal (plugin tidak
    # aktif / error jaringan), cf7_form_id akan kosong dan shortcode otomatis
    # fallback ke pencarian by-title: [contact-form-7 title="Hubungi Kami"].
    # Dilewati di append_mode — halaman contact tidak diproses ulang.
    if append_mode:
        print("\n[*] APPEND MODE — melewati pembuatan Contact Form 7.")
        cf7_form_id = ""
    else:
        print("\n[*] Membuat Contact Form 7...")
        cf7_form_id = await wp_client.create_cf7_form(brand)

    # ── [1] Buat / Reuse Nav Menu ────────────────────────────────────────────
    # ElementsKit ekit-nav-menu widget membaca menu via SLUG (bukan numeric ID).
    # create_nav_menu() idempoten: kalau menu dengan nama sama sudah ada,
    # dia akan reuse. Jadi aman dipanggil baik di full pipeline maupun append.
    nav_menu_slug = f"{brand.lower()}-nav"
    print("\n[*] Menyiapkan WordPress Navigation Menu...")
    nav_menu_id, nav_menu_slug = await wp_client.create_nav_menu(
        name=f"{brand.capitalize()} Navigation",
        slug=nav_menu_slug,
    )

    # page_links menyimpan URL canonical halaman yang dikembalikan oleh WordPress
    # setelah create_page() — ini yang digunakan untuk mengisi item menu, bukan
    # slug yang kita buat sendiri (yang bisa saja berbeda atau salah).
    page_links    = {}   # {"home": "http://...", "solusi": "...", ...}
    product_links = []   # [{"name": "...", "link": "http://..."}]

    # ── [Smart Slider 3] Deploy hero slider sebelum halaman home ─────────────
    # Membaca 3 banner AI yang sudah di-generate iAAWG (home/solusi/produk),
    # bungkus ke template .ss3, upload via bridge plugin.
    # Hasil: shortcode [smartslider3 slider="X"] yang akan menggantikan
    # hero image di halaman home. Kalau gagal, home fallback ke hero image biasa.
    # Dilewati di append_mode — slider sudah ada dari deploy sebelumnya,
    # jalan lagi hanya akan menciptakan slider duplikat.
    hero_slider_shortcode = ""
    if append_mode:
        print("[SmartSlider] APPEND MODE — melewati deploy slider (sudah ada dari deploy sebelumnya).")
    else:
        ss3_template_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "assets", "sliders", "hero-template.ss3"
        )
        if os.path.isfile(ss3_template_path):
            hero_slider_shortcode = await orchestrate_slider_deploy(
                template_path=ss3_template_path,
                wp_client=wp_client,
                brand=brand,
                visual_dir=visual_dir,
            )
        else:
            print(f"[SmartSlider] Template tidak ditemukan: {ss3_template_path} — dilewati.")

    # ── [2A] Halaman statis (home, solusi, contact) ───────────────────────────
    # Dilewati di append_mode — halaman statis sudah pernah dideploy.
    # Deploy ulang akan menciptakan halaman duplikat (contact-2, solusi-2, dst).
    if append_mode:
        print("\n[*] APPEND MODE — melewati deploy halaman statis (home, solusi, contact).")
        static_deploy_iter = []
    else:
        static_deploy_iter = list(static_pages)
    for page_type in static_deploy_iter:
        data = generated_pages_data.get(page_type, {})
        if not data:
            print(f"    [!] Data untuk halaman {page_type.upper()} tidak ditemukan, dilewati.")
            continue
        print(f"\n[*] Mendeploy Halaman: {page_type.upper()}")

        banner_bytes = _read_image(os.path.join(visual_dir, f"{brand}_{page_type}_banner.jpg"))
        stock_bytes  = _read_image(os.path.join(visual_dir, f"{brand}_{page_type}_stock.jpg"))
        banner_url   = await wp_client.upload_media(f"{brand}_{page_type}_banner.jpg", banner_bytes) if banner_bytes else ""
        stock_url    = await wp_client.upload_media(f"{brand}_{page_type}_stock.jpg",  stock_bytes)  if stock_bytes  else ""

        title, html_content, _ = PageBuilder.build_html_content(
            page_type=page_type, data=data,
            banner_url=banner_url, stock_image_url=stock_url,
            primary_color=primary_color
        )
        slug = "index" if page_type == "home" else page_type
        if page_type == "home":
            elementor_json = build_home(data, banner_url=banner_url, stock_url=stock_url,
                                        primary_color=primary_color, template=resolved_template,
                                        contact_url=contact_url,
                                        slider_shortcode=hero_slider_shortcode)
        elif page_type == "solusi":
            elementor_json = build_solusi(data, banner_url=banner_url, stock_url=stock_url,
                                          primary_color=primary_color, template=resolved_template,
                                          contact_url=contact_url)
        elif page_type == "contact":
            elementor_json = build_contact(data, primary_color=primary_color, template=resolved_template,
                                           cf7_form_id=cf7_form_id)
        else:
            elementor_json = None

        print(f"    -> Mendeploy: '{title}' (Elementor)...")
        result = await wp_client.create_page(title=title, content=html_content,
                                             slug=slug, elementor_json=elementor_json)
        # Simpan URL canonical yang dikembalikan WordPress (bukan asumsi dari slug)
        page_links[page_type] = result.get("link", "")

        # Otomatis set halaman statis sebagai front page WordPress
        if page_type == "home":
            home_page_id = result.get("id")
            if home_page_id:
                await wp_client.set_reading_settings(page_id=home_page_id)
            else:
                print("    [!] ID halaman home tidak ditemukan — front page tidak diatur otomatis.")

    # ── [2A-bis] Halaman Blog — posts archive (page_for_posts) ───────────────
    # Halaman kosong yang di-set sebagai WordPress "Posts Page" bawaan tema —
    # otomatis menampilkan daftar post dari pipeline Blog Autopost, tanpa
    # perlu widget Elementor khusus. Dilewati di append_mode (idempotent,
    # halaman blog sudah ada dari deploy sebelumnya).
    if append_mode:
        print("\n[*] APPEND MODE — melewati deploy halaman Blog (sudah ada).")
    else:
        print("\n[*] Mendeploy Halaman: BLOG")
        blog_result = await wp_client.create_page(
            title="Blog", content="", slug="blog", elementor_json=None
        )
        blog_page_id = blog_result.get("id")
        if blog_page_id:
            page_links["blog"] = blog_result.get("link", "")
            await wp_client.set_blog_page(page_id=blog_page_id)
        else:
            print("    [!] Gagal membuat halaman Blog — item menu Blog akan dilewati.")

    # ── [2B] Halaman produk — Individual Mode atau Catalog Mode ──────────────
    if generated_products_data:

        def _cat_slug(name: str) -> str:
            return re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')

        # ── CATALOG MODE ──────────────────────────────────────────────────────
        if product_mode == "catalog":

            # Kelompokkan produk berdasarkan field "category"
            catalog_groups_deploy = defaultdict(list)
            for prod in generated_products_data:
                cat = (prod.get("category") or "").strip() or "Produk"
                catalog_groups_deploy[cat].append(prod)
            catalog_groups_deploy = dict(catalog_groups_deploy)

            print(f"\n[*] CATALOG MODE: {len(catalog_groups_deploy)} kategori — "
                  f"{list(catalog_groups_deploy.keys())}")

            # Deploy halaman overview /produk/
            print("\n[*] Mendeploy Halaman Katalog Overview: PRODUK")
            produk_index_data = generated_pages_data.get("produk", {})
            produk_index_data["_brand_name"]     = brand
            produk_index_data["catalog_groups"]  = catalog_groups_deploy
            produk_index_data["product_mode"]    = "catalog"

            banner_bytes_idx = _read_image(os.path.join(visual_dir, f"{brand}_produk_banner.jpg"))
            stock_bytes_idx  = _read_image(os.path.join(visual_dir, f"{brand}_produk_stock.jpg"))
            banner_url_idx   = await wp_client.upload_media(f"{brand}_produk_banner.jpg", banner_bytes_idx) if banner_bytes_idx else ""
            stock_url_idx    = await wp_client.upload_media(f"{brand}_produk_stock.jpg",  stock_bytes_idx)  if stock_bytes_idx  else ""

            elementor_json_overview = build_catalog_overview(
                catalog_groups=catalog_groups_deploy,
                brand=brand,
                banner_url=banner_url_idx,
                stock_url=stock_url_idx,
                primary_color=primary_color,
                template=resolved_template,
            )
            _, html_idx, _ = PageBuilder.build_html_content(
                page_type="produk", data=produk_index_data,
                banner_url=banner_url_idx, stock_image_url=stock_url_idx,
                primary_color=primary_color
            )
            produk_parent    = await wp_client.create_page(
                title="Produk", content=html_idx, slug="produk",
                elementor_json=elementor_json_overview
            )
            produk_parent_id = produk_parent.get("id", 0)
            page_links["produk"] = produk_parent.get("link", "")
            print("    [✓] Halaman overview katalog berhasil dideploy.")

            # Deploy 1 halaman per kategori
            for cat_name, cat_products in catalog_groups_deploy.items():
                cat_slug = _cat_slug(cat_name)
                print(f"\n[*] Mendeploy Katalog: {cat_name} ({len(cat_products)} produk)")

                # Upload visual per produk dalam kategori ini
                cat_prod_visuals = []
                for prod in cat_products:
                    prod_slug = prod.get("slug", "produk")
                    b  = _read_image(os.path.join(visual_dir, f"{brand}_{prod_slug}_banner.jpg"))
                    s  = _read_image(os.path.join(visual_dir, f"{brand}_{prod_slug}_stock.jpg"))
                    bu = await wp_client.upload_media(f"{brand}_{prod_slug}_banner.jpg", b) if b else ""
                    su = await wp_client.upload_media(f"{brand}_{prod_slug}_stock.jpg",  s) if s else ""
                    cat_prod_visuals.append({"banner_url": bu, "stock_url": su})

                elementor_json_cat = build_catalog_category_page(
                    category_name=cat_name,
                    products=cat_products,
                    product_visuals=cat_prod_visuals,
                    primary_color=primary_color,
                    template=resolved_template,
                    contact_url=contact_url,
                    brand_name=brand,
                )
                cat_html = (
                    f"<h2>{cat_name}</h2>"
                    f"<p>Katalog produk {cat_name} dari {brand.capitalize()} Indonesia.</p>"
                )
                payload_extra = {"parent": produk_parent_id} if produk_parent_id else {}
                cat_result = await wp_client.create_page(
                    title=cat_name, content=cat_html, slug=cat_slug,
                    elementor_json=elementor_json_cat, **payload_extra
                )
                product_links.append({
                    "name": cat_name,
                    "link": cat_result.get("link", ""),
                })
                print(f"    [✓] Katalog '{cat_name}' berhasil dideploy.")

        # ── INDIVIDUAL MODE (behavior yang sudah ada, tidak berubah) ──────────
        else:
            if append_mode:
                # Halaman induk /produk/ diasumsikan sudah ada dari deploy sebelumnya.
                # Tidak deploy ulang (agar tidak duplikat), tapi tetap perlu
                # parent_id-nya supaya halaman produk baru bisa jadi child.
                print("\n[*] APPEND MODE — melewati deploy halaman induk PRODUK (mencari parent existing)...")
                produk_parent_id = 0
                try:
                    async with httpx.AsyncClient(timeout=15.0) as _c:
                        _r = await _c.get(
                            f"{wp_client.base_url}/wp-json/wp/v2/pages",
                            params={"slug": "produk", "per_page": 5},
                            headers=wp_client.headers,
                        )
                        if _r.status_code == 200:
                            _js = _r.json()
                            if isinstance(_js, list) and _js:
                                produk_parent_id = int(_js[0].get("id") or 0)
                                print(f"    [✓] Halaman induk PRODUK ditemukan (ID: {produk_parent_id}).")
                                if len(_js) > 1:
                                    # Slug WordPress dijamin unik per-post-type, jadi kalau REST
                                    # mengembalikan >1 hasil untuk slug 'produk', kemungkinan
                                    # ada halaman "Produk" yang ter-trash (masih match by-slug
                                    # tapi tidak visible di frontend) atau match fuzzy —
                                    # kasih tahu operator untuk cek manual.
                                    _other_ids = [str(p.get("id")) for p in _js[1:]]
                                    print(f"    [!] Terdeteksi {len(_js)} halaman match slug 'produk'. "
                                          f"Memakai ID pertama ({produk_parent_id}); ID lain: {', '.join(_other_ids)}. "
                                          "Cek wp-admin → Pages untuk verifikasi.")
                            else:
                                print("    [!] Halaman induk PRODUK tidak ditemukan — produk baru akan dideploy tanpa parent.")
                        else:
                            print(f"    [!] Gagal cek halaman induk PRODUK: HTTP {_r.status_code}")
                except Exception as _e:
                    print(f"    [!] Error saat mencari halaman induk PRODUK: {_e}")
            else:
                print("\n[*] Mendeploy Halaman Induk: PRODUK")
                produk_index_data = generated_pages_data.get("produk", {})
                produk_index_data["_brand_name"] = brand

                banner_bytes_idx = _read_image(os.path.join(visual_dir, f"{brand}_produk_banner.jpg"))
                stock_bytes_idx  = _read_image(os.path.join(visual_dir, f"{brand}_produk_stock.jpg"))
                banner_url_idx   = await wp_client.upload_media(f"{brand}_produk_banner.jpg", banner_bytes_idx) if banner_bytes_idx else ""
                stock_url_idx    = await wp_client.upload_media(f"{brand}_produk_stock.jpg",  stock_bytes_idx)  if stock_bytes_idx  else ""

                _, html_idx, _ = PageBuilder.build_html_content(
                    page_type="produk", data=produk_index_data,
                    banner_url=banner_url_idx, stock_image_url=stock_url_idx,
                    primary_color=primary_color
                )
                elementor_json_idx = build_produk_index(
                    produk_index_data, banner_url=banner_url_idx, stock_url=stock_url_idx,
                    primary_color=primary_color, template=resolved_template
                )
                produk_parent    = await wp_client.create_page(
                    title="Produk", content=html_idx, slug="produk", elementor_json=elementor_json_idx
                )
                produk_parent_id = produk_parent.get("id", 0)
                page_links["produk"] = produk_parent.get("link", "")

            for prod_index, prod_data in enumerate(generated_products_data):
                prod_name = prod_data.get("name", f"Produk {prod_index + 1}")
                prod_slug = prod_data.get("slug", f"produk-{prod_index + 1}")
                print(f"\n[*] Mendeploy Produk: {prod_name}")

                prod_banner_bytes = _read_image(os.path.join(visual_dir, f"{brand}_{prod_slug}_banner.jpg"))
                prod_stock_bytes  = _read_image(os.path.join(visual_dir, f"{brand}_{prod_slug}_stock.jpg"))
                prod_banner_url   = await wp_client.upload_media(f"{brand}_{prod_slug}_banner.jpg", prod_banner_bytes) if prod_banner_bytes else ""
                prod_stock_url    = await wp_client.upload_media(f"{brand}_{prod_slug}_stock.jpg",  prod_stock_bytes)  if prod_stock_bytes  else ""

                prod_nav_title, prod_html_content, _ = PageBuilder.build_product_page_html(
                    product_data=prod_data, banner_url=prod_banner_url,
                    stock_image_url=prod_stock_url, primary_color=primary_color
                )
                cta_button_text = generated_pages_data.get("home", {}).get("cta_button_text", "")
                if not cta_button_text:
                    raise ValueError("cta_button_text tidak ditemukan di data home — periksa hasil generate LLM.")

                elementor_json_prod = build_product_page(
                    product_data=prod_data, banner_url=prod_banner_url, stock_url=prod_stock_url,
                    primary_color=primary_color, template=resolved_template, contact_url=contact_url,
                    cta_button_text=cta_button_text
                )
                payload_extra = {"parent": produk_parent_id} if produk_parent_id else {}
                print(f"    -> Mendeploy: '{prod_nav_title}' (slug: {prod_slug}, Elementor)...")
                prod_result = await wp_client.create_page(
                    title=prod_nav_title, content=prod_html_content,
                    slug=prod_slug, elementor_json=elementor_json_prod, **payload_extra
                )
                product_links.append({
                    "name": prod_nav_title,
                    "link": prod_result.get("link", ""),
                })

    # ── [3] Isi / Update item nav menu ──────────────────────────────────────
    # - Full pipeline: hapus semua item lama, rebuild dari nol.
    # - Append mode:   pertahankan semua item lama, cuma tambah child produk
    #                  baru di bawah item "Produk" existing.
    if nav_menu_id:
        if append_mode:
            print("\n[*] APPEND MODE — meng-update nav menu (append child produk baru)...")
            await wp_client.append_product_menu_items(
                menu_id=nav_menu_id,
                product_links=product_links,
                parent_title="Produk",
            )
        else:
            await wp_client.create_menu_items(
                menu_id=nav_menu_id,
                page_links=page_links,
                product_links=product_links,
            )
            print(f"[✓] Nav menu selesai diisi (slug: {nav_menu_slug})")
    else:
        print("[!] Nav menu tidak tersedia — header deploy tanpa dropdown produk.")

    # ── [4] Global Header & Footer — dideploy TERAKHIR ───────────────────────
    # Dideploy paling akhir agar menu sudah terisi lengkap saat template dibuat.
    # Menggunakan ElementsKit Free CPT (elementskit_template).
    # Satu template berlaku untuk seluruh halaman secara otomatis.
    # Dilewati di append_mode — template sudah ada, deploy lagi = duplikat.
    if append_mode:
        print("\n[*] APPEND MODE — melewati deploy Global Header & Footer (sudah ada).")
    else:
        print("\n[*] Mendeploy Global Header & Footer via ElementsKit...")
        await wp_client.create_elementskit_template(
            hf_type="header",
            title=f"{brand.capitalize()} – Global Header",
            elementor_json=build_global_header(
                brand_name=brand,
                primary_color=primary_color,
                base_url=wp_client.base_url,
                menu_slug=nav_menu_slug,
            ),
        )
        await wp_client.create_elementskit_template(
            hf_type="footer",
            title=f"{brand.capitalize()} – Global Footer",
            elementor_json=build_global_footer(brand_name=brand),
        )
        print("[✓] Global Header & Footer berhasil dideploy.\n")

    if append_mode:
        print(f"\n[✓] APPEND MODE selesai — {len(generated_products_data)} produk baru ditambahkan ke output/{brand.lower()}/")
    else:
        print(f"\n[✓] Seluruh Pipeline iAAWG Berhasil Selesai! Output tersimpan di: output/{brand.lower()}/")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="iLogo AI Auto Website Generator (iAAWG) - CLI Mode")
    parser.add_argument("--brand",           required=True,  help="Nama brand IT (Contoh: zecurion)")
    parser.add_argument("--url",             required=False, help="URL Website referensi brand (Wajib diisi jika tidak menggunakan --skip-generation)")
    parser.add_argument("--skip-generation", action="store_true", help="Lewati proses crawling dan LLM teks utama, gunakan file JSON lokal yang sudah ada")
    parser.add_argument("--skip-deploy",     action="store_true", help="Hanya generate konten teks, gambar, dan HTML di lokal tanpa deploy ke WordPress")
    parser.add_argument("--product-urls",    required=False, help="Daftar URL produk dipisahkan koma (contoh: url1,url2)")
    parser.add_argument("--llm-provider",    required=False, default="openai", help="LLM Provider utama (openai / groq)")
    parser.add_argument("--primary-color",   required=False, default="#1E7E34", help="Warna utama brand (HEX) untuk theming, default iLogo green")
    parser.add_argument("--template",        required=False, default="prestige", help="Layout template Elementor: prestige | clarity | momentum")
    parser.add_argument("--append-mode",     action="store_true",
                        help="Append Mode — hanya tambah produk baru ke site yang sudah ada. Wajib pakai --product-urls. Skip generate/deploy halaman statis, CF7, header/footer, slider.")

    # ── Manual Content Override (bypass scraper) ────────────────────────────
    parser.add_argument("--homepage-content-file", required=False,
                        help="Path ke file .txt/.html berisi konten mentah homepage. Jika diisi, scraper untuk homepage dilewati.")
    parser.add_argument("--product-content-map",   required=False,
                        help="Path ke file JSON berisi mapping {url: content_file_path} untuk bypass scraper per-URL produk.")

    args = parser.parse_args()
    if not args.skip_generation and not args.url and not args.homepage_content_file:
        parser.error("Argumen --url wajib disertakan kecuali jika Anda menggunakan --skip-generation atau --homepage-content-file")

    product_urls_list = []
    if args.product_urls:
        product_urls_list = [u.strip() for u in args.product_urls.split(",") if u.strip()]

    # Load manual content dari file bila tersedia
    homepage_manual_content = ""
    if args.homepage_content_file:
        with open(args.homepage_content_file, "r", encoding="utf-8") as fh:
            homepage_manual_content = fh.read()
        print(f"[CLI] Homepage manual content dimuat dari: {args.homepage_content_file} ({len(homepage_manual_content)} char)")

    product_manual_contents = {}
    if args.product_content_map:
        with open(args.product_content_map, "r", encoding="utf-8") as fh:
            raw_map = json.load(fh)
        for prod_url, path in raw_map.items():
            with open(path, "r", encoding="utf-8") as fpc:
                product_manual_contents[prod_url] = fpc.read()
        print(f"[CLI] Manual content dimuat untuk {len(product_manual_contents)} URL produk")

    asyncio.run(run_pipeline(
        args.brand,
        args.url or "",
        args.skip_generation,
        skip_deploy=args.skip_deploy,
        product_urls=product_urls_list,
        llm_provider=args.llm_provider,
        primary_color=args.primary_color,
        template_name=args.template,
        homepage_manual_content=homepage_manual_content,
        product_manual_contents=product_manual_contents,
        append_mode=args.append_mode,
        # catalog_groups not available in CLI mode — use Web UI for catalog mode
    ))
