import os
import sys
import argparse
import asyncio
import json
import re
import httpx
from crawler.scraper import BaseScraper, ContentExtractor
from content.generator import get_llm_provider
from content.templates.prompts import SYSTEM_INSTRUCTION, PAGE_PROMPTS
from wordpress.client import WordPressClient
from wordpress.page_builder import PageBuilder

# Import modul Phase 3 — Visual & Design
from visual.color_extractor import ColorExtractor
from visual.banner_gen import get_image_provider
from visual.image_fetch import StockImageFetcher

def load_footer():
    footer_path = os.path.join("config", "footer_template.txt")
    if os.path.exists(footer_path):
        with open(footer_path, "r", encoding="utf-8") as f:
            return f.read().strip()
    return "© 2026 PT. iLogo Infralogy Indonesia. All Rights Reserved."

async def run_pipeline(brand: str, url: str, skip_generation: bool, custom_creds: dict = None, skip_deploy: bool = False):
    """
    Eksekusi Pipeline Utama iAAWG.
    Menerima parameter opsional `custom_creds` dari Web UI dan `skip_deploy` untuk Local Draft Mode.
    """
    print(f"\n[*] Memulai iAAWG Pipeline untuk Brand: {brand.upper()}")
    if skip_deploy:
        print("[*] MODE: LOCAL DRAFT ONLY (Tanpa Deploy ke WordPress)")
    
    output_dir = os.path.join("output", brand.lower(), "content")
    visual_dir = os.path.join("output", brand.lower(), "visual")
    pages = ["home", "produk", "solusi", "contact", "blog"]
    generated_pages_data = {}

    # =========================================================================
    # OPSI 1: FULL PIPELINE (CRAWL + GENERATE CONTENT LLM)
    # =========================================================================
    if not skip_generation:
        print(f"[*] URL Target: {url}")
        # 1. Crawling & Extraction
        print("[1/4] Mengunduh & mengekstrak konten website referensi...")
        scraper = BaseScraper()
        raw_html = await scraper.scrape_url(url)
        cleaned_text = ContentExtractor.clean_html(raw_html)
        
        if not cleaned_text:
            print("[!] Warning: Konten hasil ekstraksi kosong. Menggunakan data fallback minimal.")
            cleaned_text = f"Brand Name: {brand}. Official URL: {url}."
        else:
            print(f"[✓] Berhasil mengekstrak {len(cleaned_text)} karakter teks.")

        # 2. Inisialisasi LLM Provider
        print("[2/4] Menghubungkan ke LLM Provider (Groq API)...")
        try:
            llm = get_llm_provider()
        except Exception as e:
            print(f"[X] Gagal inisialisasi LLM: {e}")
            return

        # 3. Generate Konten tiap Halaman (DENGAN FITUR RETRY COOLDOWN DINAIMS)
        print("[3/4] Menghasilkan konten halaman website (Bahasa Indonesia)...")
        os.makedirs(output_dir, exist_ok=True)
        footer_text = load_footer()
        
        for index, page in enumerate(pages):
            # Menaikkan jeda standar ke 35 detik agar token ter-reset total per menitnya
            if index > 0:
                print(f"[~] Menunggu 35 detik sebelum memproses halaman berikutnya untuk menjaga kuota token API...")
                await asyncio.sleep(35)
                
            print(f"    -> Memproses halaman: {page.upper()}...")
            prompt_template = PAGE_PROMPTS[page]
            formatted_prompt = prompt_template.format(raw_data=cleaned_text[:6000], brand_name=brand)
            
            try:
                raw_response = llm.generate_content(formatted_prompt, SYSTEM_INSTRUCTION)
                
                # JIKA TERDETEKSI RATE LIMIT DI DALAM TEKS RESPONS, COOLDOWN LEBIH LAMA LALU COBA LAGI
                if "rate_limit_exceeded" in raw_response.lower() or "429" in raw_response:
                    print("[!] Terdeteksi Rate Limit Token! Melakukan cooldown otomatis selama 45 detik...")
                    await asyncio.sleep(45)
                    raw_response = llm.generate_content(formatted_prompt, SYSTEM_INSTRUCTION)

            except Exception as e:
                # Menangani jika library Groq memicu exception error HTTP 429 langsung
                if "429" in str(e) or "rate limit" in str(e).lower():
                    print("[!] Groq API memicu limit. Menunggu 45 detik sebelum mencoba ulang...")
                    await asyncio.sleep(45)
                    raw_response = llm.generate_content(formatted_prompt, SYSTEM_INSTRUCTION)
                else:
                    raw_response = f"{{'title': '{page.capitalize()}', 'error': '{str(e)}'}}"

            json_match = re.search(r"\{.*\}", raw_response, re.DOTALL)
            if json_match:
                clean_json_str = json_match.group(0)
            else:
                clean_json_str = raw_response.strip()
            
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
                
        print(f"[✓] Selesai! Konten teks lokal berhasil disimpan di folder: `{output_dir}`")

    # =========================================================================
    # OPSI 2: SKIP GENERATION (MEMANFAATKAN DATA JSON LOKAL YANG SUDAH ADA)
    # =========================================================================
    else:
        print(f"[*] [Opsi Skip Generation Aktif] Membaca data JSON lokal dari folder: `{output_dir}`")
        if not os.path.exists(output_dir):
            print(f"[X] Error: Folder output `{output_dir}` tidak ditemukan. Anda harus menjalankan full pipeline minimal sekali terlebih dahulu.")
            return

        for page in pages:
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

    # =========================================================================
    # Phase 2 & 3 — Visual Generation & Optional WordPress Deploy
    # =========================================================================
    if skip_deploy:
        print("\n[4/4] Memulai Visual Generation & Penyimpanan Lokal (Tanpa Deploy WordPress)...")
    else:
        print("\n[4/4] Memulai sinkronisasi, Visual Generation & Auto-Deploy ke WordPress REST API...")
        
    # PERBAIKAN: Pastikan folder visual selalu dibuat di mode apa pun!
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

    # --- Bagian Ekstraksi Warna (Phase 3) ---
    dummy_logo_path = "output_logo_temp.jpg"
    if not os.path.exists(dummy_logo_path):
        with open(dummy_logo_path, "wb") as f:
            f.write(b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\x60\xa0\x1c\x00\x00\x04\x00\x01\x04\xae\xed\x0e\x00\x00\x00\x00IEND\xaeB`\x82')

    extracted_colors = ColorExtractor.extract_palette(dummy_logo_path)
    print(f"[✓] Color Palette Extracted untuk tema identitas brand: {extracted_colors}")

    # --- Loop Pemrosesan Visual & Deployment ---
    for index, page_type in enumerate(pages):
        data = generated_pages_data[page_type]
        print(f"\n[*] Memproses Aset Visual untuk Halaman: {page_type.upper()}")
        
        if index > 0:
            print("[~] Memberikan jeda waktu buffer 5 detik untuk stabilitas request visual...")
            await asyncio.sleep(5)

        headline_desc = data.get("hero_headline", data.get("title", f"Solutions for {brand}"))
        keywords = data.get("seo_keywords", [])
        search_keyword = keywords[0] if keywords else "technology"

        print("    [~] Mengonversi kata kunci visual ke Bahasa Inggris via LLM Mikro...")
        translate_prompt = f"Translate this topic or text into only 2 to 4 clean English generic technology keywords for stock photo search. Text: '{headline_desc} / {search_keyword}'. Output only the English keywords, nothing else."
        english_visual_keyword = llm_helper.generate_content(translate_prompt, "You are a precise translator. Output only English keywords.")
        english_visual_keyword = english_visual_keyword.strip().replace('"', '')
        if not english_visual_keyword or len(english_visual_keyword) > 60:
            english_visual_keyword = "cybersecurity technology"
        
        print(f"    [✓] Hasil Keyword Visual (English): '{english_visual_keyword}'")

        # =========================================================================
        # PERBAIKAN 1: Banner AI Selalu Simpan ke Lokal, Baru Upload Jika Perlu
        # =========================================================================
        print(f"    -> Membuat banner AI menggunakan deskripsi: '{english_visual_keyword}'...")
        banner_bytes = await img_provider.generate_banner(prompt_desc=english_visual_keyword, brand_name=brand)
        
        banner_url = ""
        if banner_bytes:
            # Selalu tulis file fisik ke folder lokal output/
            banner_local_path = os.path.join(visual_dir, f"{brand}_{page_type}_banner.jpg")
            with open(banner_local_path, "wb") as fb:
                fb.write(banner_bytes)
            
            if skip_deploy:
                banner_url = os.path.abspath(banner_local_path)
                print(f"    [✓] Banner AI berhasil disimpan lokal di: {banner_local_path}")
            else:
                # Kirim data biner yang sama ke WordPress
                banner_url = await wp_client.upload_media(f"{brand}_{page_type}_banner.jpg", banner_bytes)

        # =========================================================================
        # PERBAIKAN 2: Stock Photo Selalu Simpan ke Lokal, Baru Upload Jika Perlu
        # =========================================================================
        print(f"    -> Mencari stock photo di Unsplash dengan kata kunci: '{english_visual_keyword}'...")
        stock_raw_url = await stock_fetcher.fetch_stock_url(english_visual_keyword)
        
        stock_url = ""
        if stock_raw_url:
            async with httpx.AsyncClient() as client:
                try:
                    res_img = await client.get(stock_raw_url)
                    if res_img.status_code == 200:
                        # Selalu tulis file fisik ke folder lokal output/
                        stock_local_path = os.path.join(visual_dir, f"{brand}_{page_type}_stock.jpg")
                        with open(stock_local_path, "wb") as fs:
                            fs.write(res_img.content)
                            
                        if skip_deploy:
                            stock_url = os.path.abspath(stock_local_path)
                            print(f"    [✓] Stock Photo berhasil disimpan lokal di: {stock_local_path}")
                        else:
                            # Kirim data biner yang sama ke WordPress
                            stock_url = await wp_client.upload_media(f"{brand}_{page_type}_stock.jpg", res_img.content)
                    else:
                        stock_url = stock_raw_url
                except Exception as e:
                    print(f"    [!] Gagal memproses stock photo: {e}")
                    stock_url = stock_raw_url

        # C. Kompilasi HTML dengan Layout Gambar
        title, html_content, excerpt = PageBuilder.build_html_content(
            page_type=page_type, 
            data=data, 
            banner_url=banner_url, 
            stock_image_url=stock_url
        )
        
        # =========================================================================
        # PERBAIKAN 3: File HTML Preview Individual Selalu Dibuat di Kedua Mode
        # =========================================================================
        html_local_path = os.path.join(output_dir, f"{page_type}_preview.html")
        with open(html_local_path, "w", encoding="utf-8") as fh:
            fh.write(f"<html><head><title>{title}</title><meta charset='utf-8'></head><body style='padding:5%; max-width:900px; margin:0 auto; font-family:sans-serif;'>{html_content}</body></html>")
        print(f"    [✓] Pratinjau HTML halaman berhasil disimpan lokal di: {html_local_path}")

        # D. Eksekusi Deploy Akhir (Hanya jika skip_deploy=False)
        if not skip_deploy:
            if page_type == "blog":
                print(f"    -> Mendeploy postingan Blog: '{title}'...")
                await wp_client.create_post(title=title, content=html_content, excerpt=excerpt)
            else:
                slug = "index" if page_type == "home" else page_type
                print(f"    -> Mendeploy Halaman Page ({page_type}): '{title}'...")
                await wp_client.create_page(title=title, content=html_content, slug=slug)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="iLogo AI Auto Website Generator (iAAWG) - CLI Mode")
    parser.add_argument("--brand", required=True, help="Nama brand IT (Contoh: zecurion)")
    parser.add_argument("--url", required=False, help="URL Website referensi brand (Wajib diisi jika tidak menggunakan --skip-generation)")
    parser.add_argument("--skip-generation", action="store_true", help="Lewati proses crawling dan LLM teks utama, gunakan file JSON lokal yang sudah ada")
    parser.add_argument("--skip-deploy", action="store_true", help="Hanya generate konten teks, gambar, dan HTML di lokal tanpa deploy ke WordPress")
    
    args = parser.parse_args()
    if not args.skip_generation and not args.url:
        parser.error("Argumen --url wajib disertakan kecuali jika Anda menggunakan opsi --skip-generation")
    
    asyncio.run(run_pipeline(args.brand, args.url, args.skip_generation, skip_deploy=args.skip_deploy))