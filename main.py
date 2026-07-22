import os
import sys
import argparse
import asyncio
import json
import re
import httpx
from crawler.scraper import BaseScraper, ContentExtractor
from content.generator import get_llm_provider
from content.templates.prompts import SYSTEM_INSTRUCTION, PAGE_PROMPTS, PRODUCT_INDIVIDUAL_PROMPT
from wordpress.client import WordPressClient
from wordpress.page_builder import PageBuilder
from config.settings import get_max_products

# Import modul Phase 3 — Visual & Design
from visual.color_extractor import ColorExtractor
from visual.banner_gen import get_image_provider
from visual.image_fetch import StockImageFetcher

# Import Elementor builder functions
from wordpress.elementor_builder import (
    build_home,
    build_produk_index,
    build_solusi,
    build_contact,
    build_product_page,
    build_global_header,   # ← BARU: untuk header global ElementsKit
    build_global_footer,   # ← BARU: untuk footer global ElementsKit
)

# Provider names supported by the failover engine (used for JSON-parse retry)
_ALL_PROVIDERS = ["groq", "cerebras", "github"]


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


async def run_pipeline(brand: str, url: str, skip_generation: bool, custom_creds: dict = None, skip_deploy: bool = False, product_urls: list = None, llm_provider: str = None, primary_color: str = "#1E7E34", template_name: str = "prestige"):
    """
    Eksekusi Pipeline Utama iAAWG.
    Menerima parameter opsional `custom_creds` dari Web UI dan `skip_deploy` untuk Local Draft Mode.
    Jika `product_urls` diberikan (list URL produk), maka sistem akan mengabaikan ekstraksi produk dari homepage
    dan hanya memproses produk dari URL tersebut.
    `primary_color` adalah warna utama (HEX) yang diambil dari logo atau default iLogo.
    """
    print(f"\n[*] Memulai iAAWG Pipeline untuk Brand: {brand.upper()}")
    if skip_deploy:
        print("[*] MODE: LOCAL DRAFT ONLY (Tanpa Deploy ke WordPress)")
    if product_urls:
        print(f"[*] MODE: PRODUK DARI URL EKSPLISIT ({len(product_urls)} URL produk)")
    print(f"[*] Warna utama brand: {primary_color}")
    print(f"[*] Template Elementor: {template_name}")

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
        print(f"[*] URL Homepage Target: {url}")
        # 1. Crawling & Extraction untuk homepage (digunakan untuk halaman statis)
        print("[1/4] Mengunduh & mengekstrak konten website referensi (homepage)...")
        scraper      = BaseScraper()
        raw_html     = await scraper.scrape_url(url)
        cleaned_text = ContentExtractor.clean_html(raw_html)

        # Validasi ambang batas 500 karakter teks bersih
        MIN_CHARACTERS = 500
        if not cleaned_text or len(cleaned_text) < MIN_CHARACTERS:
            print(f"[X] Error: Konten hasil ekstraksi terlalu sedikit ({len(cleaned_text)} karakter).")
            print(f"[X] Gagal memenuhi batas minimum {MIN_CHARACTERS} karakter bersih. Pipeline dihentikan untuk mencegah halusinasi LLM.")
            return
        else:
            print(f"[✓] Berhasil mengekstrak {len(cleaned_text)} karakter teks bersih (Layak proses).")

        # 2. Inisialisasi LLM Provider
        print("[2/4] Menghubungkan ke LLM Provider Failover Engine...")
        try:
            llm = get_llm_provider(llm_provider)
        except Exception as e:
            print(f"[X] Gagal inisialisasi LLM: {e}")
            return

        # 3. Generate Konten untuk halaman statis (home, solusi, contact)
        print("[3/4] Menghasilkan konten halaman statis (home, solusi, contact)...")
        os.makedirs(output_dir, exist_ok=True)

        for index, page in enumerate(static_pages):
            if index > 0:
                print(f"[~] Menunggu 35 detik sebelum memproses halaman berikutnya untuk menjaga kuota token API...")
                await asyncio.sleep(35)

            print(f"    -> Memproses halaman: {page.upper()}...")
            formatted_prompt = PAGE_PROMPTS[page].format(raw_data=cleaned_text[:6000], brand_name=brand)

            page_data, p_tokens, c_tokens = _generate_with_json_retry(
                prompt=formatted_prompt,
                system_instruction=SYSTEM_INSTRUCTION,
                provider_chain_str=llm_provider or "groq",
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
        if product_urls:
            print("\n[*] Memproses URL produk yang diberikan secara eksplisit...")
            # Apply max_products cap to explicit URL list as well —
            # without this, entering 20 URLs would deploy 20 product pages.
            for idx, prod_url in enumerate(product_urls[:max_products]):
                print(f"    [~] Mengunduh halaman produk #{idx+1}: {prod_url}")
                await asyncio.sleep(5)  # jeda antar request

                prod_raw_html = await scraper.scrape_url(prod_url)
                prod_cleaned  = ContentExtractor.clean_html(prod_raw_html)

                if not prod_cleaned or len(prod_cleaned) < 200:
                    print(f"    [!] Konten produk terlalu sedikit ({len(prod_cleaned)}), dilewati.")
                    continue

                prompt_prod = PRODUCT_INDIVIDUAL_PROMPT.format(raw_data=prod_cleaned[:6000])
                prod_data, p_t, c_t = _generate_with_json_retry(
                    prompt=prompt_prod,
                    system_instruction=SYSTEM_INSTRUCTION,
                    provider_chain_str=llm_provider or "groq",
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
                provider_chain_str=llm_provider or "groq",
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
        for index, page_type in enumerate(static_pages):
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

        # B. Halaman induk produk + setiap produk individual
        if generated_products_data:
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

    # ── [1] Buat Nav Menu (container saja, item diisi setelah halaman terdeploy) ─
    # ElementsKit ekit-nav-menu widget membaca menu via SLUG (bukan numeric ID).
    # create_nav_menu() mengembalikan slug aktual — penting karena jika menu sudah
    # ada dari run sebelumnya, slug-nya mungkin berbeda dari yang kita kirim.
    nav_menu_slug = f"{brand.lower()}-nav"
    print("\n[*] Membuat WordPress Navigation Menu...")
    nav_menu_id, nav_menu_slug = await wp_client.create_nav_menu(
        name=f"{brand.capitalize()} Navigation",
        slug=nav_menu_slug,
    )

    # page_links menyimpan URL canonical halaman yang dikembalikan oleh WordPress
    # setelah create_page() — ini yang digunakan untuk mengisi item menu, bukan
    # slug yang kita buat sendiri (yang bisa saja berbeda atau salah).
    page_links    = {}   # {"home": "http://...", "solusi": "...", ...}
    product_links = []   # [{"name": "...", "link": "http://..."}]

    # ── [2A] Halaman statis (home, solusi, contact) ───────────────────────────
    for page_type in static_pages:
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
                                        primary_color=primary_color, template=template_name,
                                        contact_url=contact_url)
        elif page_type == "solusi":
            elementor_json = build_solusi(data, banner_url=banner_url, stock_url=stock_url,
                                          primary_color=primary_color, template=template_name,
                                          contact_url=contact_url)
        elif page_type == "contact":
            elementor_json = build_contact(data, primary_color=primary_color, template=template_name)
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

    # ── [2B] Halaman induk produk + produk individual ─────────────────────────
    if generated_products_data:
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
            primary_color=primary_color, template=template_name
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
            elementor_json_prod = build_product_page(
                product_data=prod_data, banner_url=prod_banner_url, stock_url=prod_stock_url,
                primary_color=primary_color, template=template_name, contact_url=contact_url
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

    # ── [3] Isi item nav menu dengan URL canonical dari respons WordPress ──────
    # Dilakukan SETELAH semua halaman terdeploy sehingga URL yang disimpan
    # di menu adalah URL aktual yang dikembalikan server, bukan asumsi slug.
    if nav_menu_id:
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

    print(f"\n[✓] Seluruh Pipeline iAAWG Berhasil Selesai! Output tersimpan di: output/{brand.lower()}/")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="iLogo AI Auto Website Generator (iAAWG) - CLI Mode")
    parser.add_argument("--brand",           required=True,  help="Nama brand IT (Contoh: zecurion)")
    parser.add_argument("--url",             required=False, help="URL Website referensi brand (Wajib diisi jika tidak menggunakan --skip-generation)")
    parser.add_argument("--skip-generation", action="store_true", help="Lewati proses crawling dan LLM teks utama, gunakan file JSON lokal yang sudah ada")
    parser.add_argument("--skip-deploy",     action="store_true", help="Hanya generate konten teks, gambar, dan HTML di lokal tanpa deploy ke WordPress")
    parser.add_argument("--product-urls",    required=False, help="Daftar URL produk dipisahkan koma (contoh: url1,url2)")
    parser.add_argument("--llm-provider",    required=False, default="groq", help="LLM Provider utama (groq / cerebras)")
    parser.add_argument("--primary-color",   required=False, default="#1E7E34", help="Warna utama brand (HEX) untuk theming, default iLogo green")
    parser.add_argument("--template",        required=False, default="prestige", help="Layout template Elementor: prestige | clarity | momentum")

    args = parser.parse_args()
    if not args.skip_generation and not args.url:
        parser.error("Argumen --url wajib disertakan kecuali jika Anda menggunakan opsi --skip-generation")

    product_urls_list = []
    if args.product_urls:
        product_urls_list = [u.strip() for u in args.product_urls.split(",") if u.strip()]

    asyncio.run(run_pipeline(
        args.brand,
        args.url,
        args.skip_generation,
        skip_deploy=args.skip_deploy,
        product_urls=product_urls_list,
        llm_provider=args.llm_provider,
        primary_color=args.primary_color,
        template_name=args.template
    ))