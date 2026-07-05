import os
import sys
import argparse
import asyncio
import json
import re
from crawler.scraper import BaseScraper, ContentExtractor
from content.generator import get_llm_provider
from content.templates.prompts import SYSTEM_INSTRUCTION, PAGE_PROMPTS
from wordpress.client import WordPressClient
from wordpress.page_builder import PageBuilder

def load_footer():
    footer_path = os.path.join("config", "footer_template.txt")
    if os.path.exists(footer_path):
        with open(footer_path, "r", encoding="utf-8") as f:
            return f.read().strip()
    return "© 2026 PT. iLogo Infralogy Indonesia. All Rights Reserved."

async def run_pipeline(brand: str, url: str, skip_llm: bool):
    print(f"\n[*] Memulai iAAWG Pipeline untuk Brand: {brand.upper()}")
    
    output_dir = os.path.join("output", brand.lower(), "content")
    pages = ["home", "produk", "solusi", "contact", "blog"]
    generated_pages_data = {}

    # =========================================================================
    # OPSI 1: FULL PIPELINE (CRAWL + GENERATE LLM)
    # =========================================================================
    if not skip_llm:
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

        # 3. Generate Konten tiap Halaman
        print("[3/4] Menghasilkan konten halaman website (Bahasa Indonesia)...")
        os.makedirs(output_dir, exist_ok=True)
        footer_text = load_footer()
        
        for index, page in enumerate(pages):
            if index > 0:
                delay = 12
                print(f"[~] Menunggu {delay} detik sebelum memproses halaman berikutnya untuk menjaga Rate Limit API...")
                await asyncio.sleep(delay)
                
            print(f"    -> Memproses halaman: {page.upper()}...")
            prompt_template = PAGE_PROMPTS[page]
            
            formatted_prompt = prompt_template.format(raw_data=cleaned_text[:6000], brand_name=brand)
            raw_response = llm.generate_content(formatted_prompt, SYSTEM_INSTRUCTION)
            
            json_match = re.search(r"\{.*\}", raw_response, re.DOTALL)
            if json_match:
                clean_json_str = json_match.group(0)
            else:
                clean_json_str = raw_response.strip()
            
            try:
                page_data = json.loads(clean_json_str)
            except Exception as e:
                print(f"    [!] Warning: Gagal otomatis parse JSON untuk {page}, menggunakan format teks mentah.")
                page_data = {"raw_output": raw_response}
            
            page_data["standard_footer"] = footer_text
            generated_pages_data[page] = page_data
            
            file_path = os.path.join(output_dir, f"{page}.json")
            with open(file_path, "w", encoding="utf-8") as out_file:
                json.dump(page_data, out_file, indent=4, ensure_ascii=False)
                
        print(f"[✓] Selesai! Konten teks lokal berhasil disimpan di folder: `{output_dir}`")

    # =========================================================================
    # OPSI 2: SKIP LLM (MEMANFAATKAN DATA JSON LOKAL YANG SUDAH ADA)
    # =========================================================================
    else:
        print(f"[*] [Opsi Skip LLM Aktif] Membaca data JSON lokal dari folder: `{output_dir}`")
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
    # Phase 2 — WordPress Integration (Auto-Deploy)
    # =========================================================================
    print("\n[4/4] Memulai sinkronisasi & Auto-Deploy ke WordPress REST API...")
    try:
        wp_client = WordPressClient()
    except ValueError as e:
        print(f"[X] Gagal inisialisasi WordPress Client: {e}")
        print("[!] Silakan lengkapi konfigurasi .env Anda terlebih dahulu untuk mengaktifkan Phase 2.")
        return

    for page_type, data in generated_pages_data.items():
        title, html_content, excerpt = PageBuilder.build_html_content(page_type, data)
        
        if page_type == "blog":
            print(f"    -> Mengunggah artikel Blog: '{title}'...")
            await wp_client.create_post(title=title, content=html_content, excerpt=excerpt)
        else:
            slug = "index" if page_type == "home" else page_type
            print(f"    -> Mengunggah Halaman Page ({page_type}): '{title}'...")
            await wp_client.create_page(title=title, content=html_content, slug=slug)
            
    print(f"\n[✓] SELURUH PIPELINE PHASE 2 BERHASIL! Silakan cek dashboard admin WordPress Anda.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="iLogo AI Auto Website Generator (iAAWG) - CLI Mode")
    parser.add_argument("--brand", required=True, help="Nama brand IT (Contoh: zecurion)")
    parser.add_argument("--url", required=False, help="URL Website referensi brand (Wajib diisi jika tidak menggunakan --skip-llm)")
    parser.add_argument("--skip-llm", action="store_true", help="Lewati proses crawling dan LLM, gunakan file JSON lokal yang sudah ada")
    
    args = parser.parse_args()
    
    # Validasi argumen URL jika tidak memilih opsi skip-llm
    if not args.skip_llm and not args.url:
        parser.error("Argumen --url wajib disertakan kecuali jika Anda menggunakan opsi --skip-llm")
    
    asyncio.run(run_pipeline(args.brand, args.url, args.skip_llm))