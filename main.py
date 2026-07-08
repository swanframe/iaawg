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

# Import modul Phase 3 — Visual & Design
from visual.color_extractor import ColorExtractor
from visual.banner_gen import get_image_provider
from visual.image_fetch import StockImageFetcher

MAX_PRODUCTS = 5  # Batas maksimum halaman produk individual yang akan di-deploy

def load_footer():
    footer_path = os.path.join("config", "footer_template.txt")
    if os.path.exists(footer_path):
        with open(footer_path, "r", encoding="utf-8") as f:
            return f.read().strip()
    return "© 2026 PT. iLogo Infralogy Indonesia. All Rights Reserved."

async def run_pipeline(brand: str, url: str, skip_generation: bool, custom_creds: dict = None, skip_deploy: bool = False, product_urls: list = None):
    """
    Eksekusi Pipeline Utama iAAWG.
    Menerima parameter opsional `custom_creds` dari Web UI dan `skip_deploy` untuk Local Draft Mode.
    Jika `product_urls` diberikan (list URL produk), maka sistem akan mengabaikan ekstraksi produk dari homepage
    dan hanya memproses produk dari URL tersebut.
    """
    print(f"\n[*] Memulai iAAWG Pipeline untuk Brand: {brand.upper()}")
    if skip_deploy:
        print("[*] MODE: LOCAL DRAFT ONLY (Tanpa Deploy ke WordPress)")
    if product_urls:
        print(f"[*] MODE: PRODUK DARI URL EKSPLISIT ({len(product_urls)} URL produk)")

    output_dir = os.path.join("output", brand.lower(), "content")
    visual_dir = os.path.join("output", brand.lower(), "visual")

    # Halaman statis utama (home, solusi, contact) — produk ditangani terpisah
    static_pages = ["home", "solusi", "contact"]
    all_pages    = ["home", "produk", "solusi", "contact"]  # untuk backward compatibility baca JSON

    generated_pages_data   = {}   # data halaman statis {page_type: data}
    generated_products_data = []  # list data tiap produk individual

    # =========================================================================
    # OPSI 1: FULL PIPELINE (CRAWL + GENERATE CONTENT LLM)
    # =========================================================================
    if not skip_generation:
        print(f"[*] URL Homepage Target: {url}")
        # 1. Crawling & Extraction untuk homepage (digunakan untuk halaman statis)
        print("[1/4] Mengunduh & mengekstrak konten website referensi (homepage)...")
        scraper = BaseScraper()
        raw_html = await scraper.scrape_url(url)
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
        print("[2/4] Menghubungkan ke LLM Provider (Groq API)...")
        try:
            llm = get_llm_provider()
        except Exception as e:
            print(f"[X] Gagal inisialisasi LLM: {e}")
            return

        # 3. Generate Konten untuk halaman statis (home, solusi, contact)
        print("[3/4] Menghasilkan konten halaman statis (home, solusi, contact)...")
        os.makedirs(output_dir, exist_ok=True)
        footer_text = load_footer()

        for index, page in enumerate(static_pages):
            if index > 0:
                print(f"[~] Menunggu 35 detik sebelum memproses halaman berikutnya untuk menjaga kuota token API...")
                await asyncio.sleep(35)

            print(f"    -> Memproses halaman: {page.upper()}...")
            prompt_template = PAGE_PROMPTS[page]
            formatted_prompt = prompt_template.format(raw_data=cleaned_text[:6000], brand_name=brand)

            try:
                raw_response, p_tokens, c_tokens = llm.generate_content(formatted_prompt, SYSTEM_INSTRUCTION)
                print(f"[TOKEN_USAGE] Prompt: {p_tokens} | Completion: {c_tokens}")

                if "rate_limit_exceeded" in raw_response.lower() or "429" in raw_response:
                    print("[!] Terdeteksi Rate Limit Token! Melakukan cooldown otomatis selama 45 detik...")
                    await asyncio.sleep(45)
                    raw_response, p_tokens, c_tokens = llm.generate_content(formatted_prompt, SYSTEM_INSTRUCTION)
                    print(f"[TOKEN_USAGE] Prompt: {p_tokens} | Completion: {c_tokens}")

            except Exception as e:
                if "429" in str(e) or "rate limit" in str(e).lower():
                    print("[!] Groq API memicu limit. Menunggu 45 detik sebelum mencoba ulang...")
                    await asyncio.sleep(45)
                    raw_response, p_tokens, c_tokens = llm.generate_content(formatted_prompt, SYSTEM_INSTRUCTION)
                    print(f"[TOKEN_USAGE] Prompt: {p_tokens} | Completion: {c_tokens}")
                else:
                    raw_response = f"{{'title': '{page.capitalize()}', 'error': '{str(e)}'}}"

            json_match = re.search(r"\{.*\}", raw_response, re.DOTALL)
            clean_json_str = json_match.group(0) if json_match else raw_response.strip()

            try:
                page_data = json.loads(clean_json_str)
            except Exception as e:
                print(f"    [!] Warning: Gagal otomatis parse JSON untuk {page}, menggunakan format teks mentah.")
                page_data = {
                    "title": page.capitalize(),
                    "hero_headline": f"Solutions for {brand}",
                    "hero_subheadline": f"Professional {page} services",
                    "seo_keywords": ["technology", brand.lower()],
                    "raw_output": raw_response
                }

            page_data["standard_footer"] = footer_text
            generated_pages_data[page] = page_data

            file_path = os.path.join(output_dir, f"{page}.json")
            with open(file_path, "w", encoding="utf-8") as out_file:
                json.dump(page_data, out_file, indent=4, ensure_ascii=False)

        # =============================================================
        # GENERATE PRODUK
        # =============================================================
        # Jika ada product_urls, proses setiap URL produk secara terpisah
        if product_urls:
            print("\n[*] Memproses URL produk yang diberikan secara eksplisit...")
            for idx, prod_url in enumerate(product_urls):
                print(f"    [~] Mengunduh halaman produk #{idx+1}: {prod_url}")
                await asyncio.sleep(5)  # jeda antar request

                prod_raw_html = await scraper.scrape_url(prod_url)
                prod_cleaned = ContentExtractor.clean_html(prod_raw_html)

                if not prod_cleaned or len(prod_cleaned) < 200:
                    print(f"    [!] Konten produk terlalu sedikit ({len(prod_cleaned)}), dilewati.")
                    continue

                prompt_prod = PRODUCT_INDIVIDUAL_PROMPT.format(raw_data=prod_cleaned[:6000])
                try:
                    raw_prod_response, p_t, c_t = llm.generate_content(prompt_prod, SYSTEM_INSTRUCTION)
                    print(f"[TOKEN_USAGE] Prompt: {p_t} | Completion: {c_t}")
                    json_match_prod = re.search(r"\{.*\}", raw_prod_response, re.DOTALL)
                    clean_json_prod = json_match_prod.group(0) if json_match_prod else raw_prod_response.strip()
                    prod_data = json.loads(clean_json_prod)
                    # Pastikan memiliki field yang diperlukan
                    if "name" not in prod_data:
                        prod_data["name"] = f"Produk {idx+1}"
                    if "slug" not in prod_data:
                        prod_data["slug"] = f"produk-{idx+1}"
                    if "seo_keywords" not in prod_data:
                        prod_data["seo_keywords"] = ["teknologi", brand.lower()]
                    prod_data["standard_footer"] = footer_text
                    generated_products_data.append(prod_data)
                    print(f"    [✓] Berhasil generate produk: {prod_data['name']}")
                except Exception as e:
                    print(f"    [!] Gagal generate produk dari URL {prod_url}: {e}")

            # Buat halaman induk "Produk" secara otomatis berdasarkan data produk yang dihasilkan
            if generated_products_data:
                produk_index_data = {
                    "title": "Produk & Solusi Kami",
                    "intro_page_title": "Produk & Solusi Kami",
                    "intro_page_description": f"Berikut adalah produk-produk unggulan dari {brand}.",
                    "products_list": generated_products_data,
                    "seo_keywords": ["produk", brand.lower()],
                    "standard_footer": footer_text
                }
                generated_pages_data["produk"] = produk_index_data
                # Simpan JSON halaman produk induk
                produk_file = os.path.join(output_dir, "produk.json")
                with open(produk_file, "w", encoding="utf-8") as f:
                    json.dump(produk_index_data, f, indent=4, ensure_ascii=False)
                print(f"[✓] Halaman induk produk dibuat dari {len(generated_products_data)} produk.")
            else:
                print("[!] Tidak ada produk berhasil digenerate dari URL yang diberikan.")
                # Tetap buat halaman produk kosong agar tidak error
                generated_pages_data["produk"] = {
                    "title": "Produk",
                    "intro_page_title": "Produk",
                    "intro_page_description": "",
                    "products_list": [],
                    "seo_keywords": ["produk", brand.lower()],
                    "standard_footer": footer_text
                }

        else:
            # Mode lama: generate halaman "produk" dari homepage
            print("\n[*] Menghasilkan konten halaman produk (induk) dari homepage...")
            # Panggil LLM untuk halaman "produk"
            prompt_produk = PAGE_PROMPTS["produk"].format(raw_data=cleaned_text[:6000], brand_name=brand)
            # ... (kode sama seperti sebelumnya untuk generate produk)
            # Kami salin dari kode asli
            try:
                raw_response, p_t, c_t = llm.generate_content(prompt_produk, SYSTEM_INSTRUCTION)
                print(f"[TOKEN_USAGE] Prompt: {p_t} | Completion: {c_t}")
                json_match = re.search(r"\{.*\}", raw_response, re.DOTALL)
                clean_json_str = json_match.group(0) if json_match else raw_response.strip()
                produk_data = json.loads(clean_json_str)
            except Exception as e:
                print(f"    [!] Gagal generate halaman produk: {e}")
                produk_data = {
                    "title": "Produk",
                    "intro_page_title": "Produk & Solusi Kami",
                    "intro_page_description": "",
                    "products_list": [],
                    "seo_keywords": ["produk", brand.lower()]
                }
            produk_data["standard_footer"] = footer_text
            generated_pages_data["produk"] = produk_data
            # Simpan JSON
            produk_file = os.path.join(output_dir, "produk.json")
            with open(produk_file, "w", encoding="utf-8") as f:
                json.dump(produk_data, f, indent=4, ensure_ascii=False)

            # Ambil products_list dari data produk
            raw_products = produk_data.get("products_list", [])
            if raw_products:
                limited_products = raw_products[:MAX_PRODUCTS]
                for prod in limited_products:
                    prod["standard_footer"] = footer_text
                    generated_products_data.append(prod)
                print(f"[✓] Ditemukan {len(generated_products_data)} produk utama dari data LLM (maks {MAX_PRODUCTS}).")
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

        # Baca semua halaman statis dan produk
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

        # Ambil products_list dari produk.json
        produk_data = generated_pages_data.get("produk", {})
        raw_products = produk_data.get("products_list", [])
        if raw_products:
            for prod in raw_products[:MAX_PRODUCTS]:
                prod["standard_footer"] = load_footer()
                generated_products_data.append(prod)
            print(f"[✓] Ditemukan {len(generated_products_data)} produk dari JSON lokal (maks {MAX_PRODUCTS}).")
        else:
            print("[!] Tidak ada produk dalam data JSON.")

    # =========================================================================
    # Phase 2 & 3 — Visual Generation & Optional WordPress Deploy
    # =========================================================================
    if skip_deploy:
        print("\n[4/4] Memulai Visual Generation & Penyimpanan Lokal (Tanpa Deploy WordPress)...")
    else:
        print("\n[4/4] Memulai sinkronisasi, Visual Generation & Auto-Deploy ke WordPress REST API...")

    os.makedirs(visual_dir, exist_ok=True)

    try:
        wp_client = None
        if not skip_deploy:
            if custom_creds:
                wp_client = WordPressClient(
                    url=custom_creds.get("wp_url"),
                    username=custom_creds.get("wp_username"),
                    app_password=custom_creds.get("wp_app_password")
                )
            else:
                wp_client = WordPressClient()

        img_provider = get_image_provider()
        stock_fetcher = StockImageFetcher()
        llm_helper = get_llm_provider()
    except ValueError as e:
        print(f"[X] Gagal inisialisasi Client / Provider: {e}")
        print("[!] Silakan lengkapi konfigurasi .env atau isi formulir WordPress Web UI Anda terlebih dahulu.")
        return

    # --- Ekstraksi Warna (Phase 3) ---
    dummy_logo_path = "output_logo_temp.jpg"
    if not os.path.exists(dummy_logo_path):
        with open(dummy_logo_path, "wb") as f:
            f.write(b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\x60\xa0\x1c\x00\x00\x04\x00\x01\x04\xae\xed\x0e\x00\x00\x00\x00IEND\xaeB`\x82')

    extracted_colors = ColorExtractor.extract_palette(dummy_logo_path)
    print(f"[✓] Color Palette Extracted untuk tema identitas brand: {extracted_colors}")

    # =========================================================================
    # A. Loop Visual & Deploy — Halaman Statis (home, solusi, contact)
    # =========================================================================
    for index, page_type in enumerate(static_pages):
        data = generated_pages_data[page_type]
        print(f"\n[*] Memproses Aset Visual untuk Halaman: {page_type.upper()}")

        if index > 0:
            print("[~] Memberikan jeda waktu buffer 5 detik untuk stabilitas request visual...")
            await asyncio.sleep(5)

        headline_desc    = data.get("hero_headline", data.get("title", f"Solutions for {brand}"))
        keywords         = data.get("seo_keywords", [])
        search_keyword   = keywords[0] if keywords else "technology"

        print("    [~] Mengonversi kata kunci visual ke Bahasa Inggris via LLM Mikro...")
        translate_prompt = f"Translate this topic or text into only 2 to 4 clean English generic technology keywords for stock photo search. Text: '{headline_desc} / {search_keyword}'. Output only the English keywords, nothing else."

        english_visual_keyword, p_tokens, c_tokens = llm_helper.generate_content(translate_prompt, "You are a precise translator. Output only English keywords.")
        print(f"    [TOKEN_USAGE] Prompt: {p_tokens} | Completion: {c_tokens}")

        english_visual_keyword = english_visual_keyword.strip().replace('"', '')
        if not english_visual_keyword or len(english_visual_keyword) > 60:
            english_visual_keyword = "cybersecurity technology"

        print(f"    [✓] Hasil Keyword Visual (English): '{english_visual_keyword}'")

        # Banner AI
        print(f"    -> Membuat banner AI menggunakan deskripsi: '{english_visual_keyword}'...")
        banner_bytes = await img_provider.generate_banner(prompt_desc=english_visual_keyword, brand_name=brand)

        banner_url = ""
        if banner_bytes:
            banner_local_path = os.path.join(visual_dir, f"{brand}_{page_type}_banner.jpg")
            with open(banner_local_path, "wb") as fb:
                fb.write(banner_bytes)

            if skip_deploy:
                banner_url = os.path.abspath(banner_local_path)
                print(f"    [✓] Banner AI berhasil disimpan lokal di: {banner_local_path}")
            else:
                banner_url = await wp_client.upload_media(f"{brand}_{page_type}_banner.jpg", banner_bytes)

        # Stock Photo
        print(f"    -> Mencari stock photo di Unsplash dengan kata kunci: '{english_visual_keyword}'...")
        stock_raw_url = await stock_fetcher.fetch_stock_url(english_visual_keyword)

        stock_url = ""
        if stock_raw_url:
            async with httpx.AsyncClient() as client:
                try:
                    res_img = await client.get(stock_raw_url)
                    if res_img.status_code == 200:
                        stock_local_path = os.path.join(visual_dir, f"{brand}_{page_type}_stock.jpg")
                        with open(stock_local_path, "wb") as fs:
                            fs.write(res_img.content)

                        if skip_deploy:
                            stock_url = os.path.abspath(stock_local_path)
                            print(f"    [✓] Stock Photo berhasil disimpan lokal di: {stock_local_path}")
                        else:
                            stock_url = await wp_client.upload_media(f"{brand}_{page_type}_stock.jpg", res_img.content)
                    else:
                        stock_url = stock_raw_url
                except Exception as e:
                    print(f"    [!] Gagal memproses stock photo: {e}")
                    stock_url = stock_raw_url

        # Kompilasi HTML halaman statis
        title, html_content, excerpt = PageBuilder.build_html_content(
            page_type=page_type,
            data=data,
            banner_url=banner_url,
            stock_image_url=stock_url
        )

        # Simpan preview HTML lokal
        html_local_path = os.path.join(output_dir, f"{page_type}_preview.html")
        with open(html_local_path, "w", encoding="utf-8") as fh:
            fh.write(f"<html><head><title>{title}</title><meta charset='utf-8'></head><body style='padding:5%; max-width:900px; margin:0 auto; font-family:sans-serif;'>{html_content}</body></html>")
        print(f"    [✓] Pratinjau HTML halaman berhasil disimpan lokal di: {html_local_path}")

        # Deploy ke WordPress (hanya jika skip_deploy=False)
        if not skip_deploy:
            slug = "index" if page_type == "home" else page_type
            print(f"    -> Mendeploy Halaman Page ({page_type}): '{title}'...")
            await wp_client.create_page(title=title, content=html_content, slug=slug)

    # =========================================================================
    # B. Loop Visual & Deploy — Halaman Produk Individual (dari generated_products_data)
    # =========================================================================
    if generated_products_data:
        print(f"\n[*] Memulai proses {len(generated_products_data)} halaman produk individual...")

        # Deploy halaman induk "Produk" terlebih dahulu (data ada di generated_pages_data["produk"])
        produk_index_data = generated_pages_data.get("produk", {})
        produk_index_data["standard_footer"] = load_footer()
        print(f"\n[*] Memproses Halaman Induk: PRODUK (index)")
        await asyncio.sleep(5)

        # Visual untuk halaman induk produk
        produk_kw   = produk_index_data.get("seo_keywords", ["technology"])[0]
        translate_p = f"Translate this topic into 2-4 clean English keywords for stock photo search: '{produk_kw}'. Output only the English keywords."
        en_kw_produk, pt, ct = llm_helper.generate_content(translate_p, "You are a precise translator. Output only English keywords.")
        print(f"    [TOKEN_USAGE] Prompt: {pt} | Completion: {ct}")
        en_kw_produk = en_kw_produk.strip().replace('"', '') or "software products technology"

        banner_bytes_idx = await img_provider.generate_banner(prompt_desc=en_kw_produk, brand_name=brand)
        banner_url_idx   = ""
        if banner_bytes_idx:
            bp = os.path.join(visual_dir, f"{brand}_produk_banner.jpg")
            with open(bp, "wb") as fb:
                fb.write(banner_bytes_idx)
            if skip_deploy:
                banner_url_idx = os.path.abspath(bp)
            else:
                banner_url_idx = await wp_client.upload_media(f"{brand}_produk_banner.jpg", banner_bytes_idx)

        stock_idx_url_raw = await stock_fetcher.fetch_stock_url(en_kw_produk)
        stock_url_idx     = ""
        if stock_idx_url_raw:
            async with httpx.AsyncClient() as cl:
                try:
                    ri = await cl.get(stock_idx_url_raw)
                    if ri.status_code == 200:
                        sp = os.path.join(visual_dir, f"{brand}_produk_stock.jpg")
                        with open(sp, "wb") as fs:
                            fs.write(ri.content)
                        if skip_deploy:
                            stock_url_idx = os.path.abspath(sp)
                        else:
                            stock_url_idx = await wp_client.upload_media(f"{brand}_produk_stock.jpg", ri.content)
                    else:
                        stock_url_idx = stock_idx_url_raw
                except Exception as e:
                    print(f"    [!] Gagal memproses stock photo produk index: {e}")
                    stock_url_idx = stock_idx_url_raw

        _, html_idx, _ = PageBuilder.build_html_content(
            page_type="produk",
            data=produk_index_data,
            banner_url=banner_url_idx,
            stock_image_url=stock_url_idx
        )
        html_idx_path = os.path.join(output_dir, "produk_preview.html")
        with open(html_idx_path, "w", encoding="utf-8") as fh:
            fh.write(f"<html><head><title>Produk</title><meta charset='utf-8'></head><body style='padding:5%; max-width:900px; margin:0 auto; font-family:sans-serif;'>{html_idx}</body></html>")
        print(f"    [✓] Pratinjau HTML halaman induk produk disimpan di: {html_idx_path}")

        if not skip_deploy:
            print(f"    -> Mendeploy Halaman Induk Produk: 'Produk'...")
            produk_parent = await wp_client.create_page(title="Produk", content=html_idx, slug="produk")
            produk_parent_id = produk_parent.get("id", 0)
        else:
            produk_parent_id = 0

        # Deploy setiap halaman produk individual
        for prod_index, prod_data in enumerate(generated_products_data):
            prod_name = prod_data.get("name", f"Produk {prod_index + 1}")
            prod_slug = prod_data.get("slug", f"produk-{prod_index + 1}")
            print(f"\n[*] Memproses Aset Visual untuk Produk: {prod_name}")

            await asyncio.sleep(5)

            # Keyword visual untuk produk ini
            prod_headline = prod_data.get("tagline", prod_name)
            prod_keywords = prod_data.get("seo_keywords", [])
            prod_kw       = prod_keywords[0] if prod_keywords else "technology product"

            translate_prod = f"Translate this product topic into 2-4 clean English keywords for stock photo search: '{prod_headline} / {prod_kw}'. Output only English keywords."
            en_kw_prod, pt2, ct2 = llm_helper.generate_content(translate_prod, "You are a precise translator. Output only English keywords.")
            print(f"    [TOKEN_USAGE] Prompt: {pt2} | Completion: {ct2}")
            en_kw_prod = en_kw_prod.strip().replace('"', '') or "technology software"
            print(f"    [✓] Keyword Visual Produk (English): '{en_kw_prod}'")

            # Banner AI produk
            print(f"    -> Membuat banner AI untuk produk: '{prod_name}'...")
            prod_banner_bytes = await img_provider.generate_banner(prompt_desc=en_kw_prod, brand_name=brand)
            prod_banner_url   = ""
            if prod_banner_bytes:
                prod_banner_path = os.path.join(visual_dir, f"{brand}_{prod_slug}_banner.jpg")
                with open(prod_banner_path, "wb") as fb:
                    fb.write(prod_banner_bytes)
                if skip_deploy:
                    prod_banner_url = os.path.abspath(prod_banner_path)
                    print(f"    [✓] Banner produk disimpan lokal di: {prod_banner_path}")
                else:
                    prod_banner_url = await wp_client.upload_media(f"{brand}_{prod_slug}_banner.jpg", prod_banner_bytes)

            # Stock photo produk
            print(f"    -> Mencari stock photo untuk produk: '{en_kw_prod}'...")
            prod_stock_raw = await stock_fetcher.fetch_stock_url(en_kw_prod)
            prod_stock_url = ""
            if prod_stock_raw:
                async with httpx.AsyncClient() as client:
                    try:
                        res_prod_img = await client.get(prod_stock_raw)
                        if res_prod_img.status_code == 200:
                            prod_stock_path = os.path.join(visual_dir, f"{brand}_{prod_slug}_stock.jpg")
                            with open(prod_stock_path, "wb") as fs:
                                fs.write(res_prod_img.content)
                            if skip_deploy:
                                prod_stock_url = os.path.abspath(prod_stock_path)
                                print(f"    [✓] Stock photo produk disimpan lokal di: {prod_stock_path}")
                            else:
                                prod_stock_url = await wp_client.upload_media(f"{brand}_{prod_slug}_stock.jpg", res_prod_img.content)
                        else:
                            prod_stock_url = prod_stock_raw
                    except Exception as e:
                        print(f"    [!] Gagal memproses stock photo produk: {e}")
                        prod_stock_url = prod_stock_raw

            # Build HTML halaman produk individual
            prod_nav_title, prod_html_content, prod_excerpt = PageBuilder.build_product_page_html(
                product_data=prod_data,
                banner_url=prod_banner_url,
                stock_image_url=prod_stock_url,
                footer_text=load_footer()
            )

            # Simpan preview HTML lokal
            prod_html_path = os.path.join(output_dir, f"produk_{prod_slug}_preview.html")
            with open(prod_html_path, "w", encoding="utf-8") as fh:
                fh.write(f"<html><head><title>{prod_nav_title}</title><meta charset='utf-8'></head><body style='padding:5%; max-width:900px; margin:0 auto; font-family:sans-serif;'>{prod_html_content}</body></html>")
            print(f"    [✓] Pratinjau HTML produk disimpan di: {prod_html_path}")

            # Simpan data JSON produk individual
            prod_json_path = os.path.join(output_dir, f"produk_{prod_slug}.json")
            with open(prod_json_path, "w", encoding="utf-8") as pjf:
                json.dump(prod_data, pjf, indent=4, ensure_ascii=False)

            # Deploy ke WordPress sebagai child page dari halaman "Produk"
            if not skip_deploy:
                print(f"    -> Mendeploy halaman produk: '{prod_nav_title}' (slug: {prod_slug})...")
                payload_extra = {}
                if produk_parent_id:
                    payload_extra["parent"] = produk_parent_id
                await wp_client.create_page(
                    title=prod_nav_title,
                    content=prod_html_content,
                    slug=prod_slug,
                    **payload_extra
                )

    print(f"\n[✓] Seluruh Pipeline iAAWG Berhasil Selesai! Output tersimpan di: output/{brand.lower()}/")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="iLogo AI Auto Website Generator (iAAWG) - CLI Mode")
    parser.add_argument("--brand", required=True, help="Nama brand IT (Contoh: zecurion)")
    parser.add_argument("--url", required=False, help="URL Website referensi brand (Wajib diisi jika tidak menggunakan --skip-generation)")
    parser.add_argument("--skip-generation", action="store_true", help="Lewati proses crawling dan LLM teks utama, gunakan file JSON lokal yang sudah ada")
    parser.add_argument("--skip-deploy", action="store_true", help="Hanya generate konten teks, gambar, dan HTML di lokal tanpa deploy ke WordPress")
    # Tambahan untuk CLI: bisa menerima daftar URL produk dipisahkan koma
    parser.add_argument("--product-urls", required=False, help="Daftar URL produk dipisahkan koma (contoh: url1,url2)")

    args = parser.parse_args()
    if not args.skip_generation and not args.url:
        parser.error("Argumen --url wajib disertakan kecuali jika Anda menggunakan opsi --skip-generation")

    product_urls_list = []
    if args.product_urls:
        product_urls_list = [u.strip() for u in args.product_urls.split(",") if u.strip()]

    asyncio.run(run_pipeline(args.brand, args.url, args.skip_generation, skip_deploy=args.skip_deploy, product_urls=product_urls_list))