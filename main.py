import os
import sys
import argparse
import asyncio
import json
import re  # Digunakan untuk ekstraksi JSON yang lebih tangguh dari LLM
from crawler.scraper import BaseScraper, ContentExtractor
from content.generator import get_llm_provider
from content.templates.prompts import SYSTEM_INSTRUCTION, PAGE_PROMPTS

def load_footer():
    """
    Memuat template footer standar dari config/footer_template.txt jika tersedia.
    """
    footer_path = os.path.join("config", "footer_template.txt")
    if os.path.exists(footer_path):
        with open(footer_path, "r", encoding="utf-8") as f:
            return f.read().strip()
    return "© 2026 PT. iLogo Infralogy Indonesia. All Rights Reserved."

async def run_pipeline(brand: str, url: str):
    print(f"\n[*] Memulai iAAWG Pipeline untuk Brand: {brand.upper()}")
    print(f"[*] URL Target: {url}")
    
    # 1. Crawling & Extraction
    print("[1/3] Mengunduh & mengekstrak konten website referensi...")
    scraper = BaseScraper()
    raw_html = await scraper.scrape_url(url)
    cleaned_text = ContentExtractor.clean_html(raw_html)
    
    if not cleaned_text:
        print("[!] Warning: Konten hasil ekstraksi kosong. Menggunakan data fallback minimal.")
        cleaned_text = f"Brand Name: {brand}. Official URL: {url}."
    else:
        print(f"[✓] Berhasil mengekstrak {len(cleaned_text)} karakter teks.")

    # 2. Inisialisasi LLM Provider
    print("[2/3] Menghubungkan ke LLM Provider (Groq API)...")
    try:
        llm = get_llm_provider()
    except Exception as e:
        print(f"[X] Gagal inisialisasi LLM: {e}")
        return

    # 3. Generate Konten tiap Halaman
    print("[3/3] Menghasilkan konten halaman website (Bahasa Indonesia)...")
    output_dir = os.path.join("output", brand.lower(), "content")
    os.makedirs(output_dir, exist_ok=True)
    
    footer_text = load_footer()
    pages = ["home", "produk", "solusi", "contact", "blog"]
    
    for index, page in enumerate(pages):
        # Jika bukan halaman pertama, beri jeda waktu agar tidak terkena rate limit kuota gratisan Groq
        if index > 0:
            delay = 12
            print(f"[~] Menunggu {delay} detik sebelum memproses halaman berikutnya untuk menjaga Rate Limit API...")
            await asyncio.sleep(delay)
            
        print(f"    -> Memproses halaman: {page.upper()}...")
        prompt_template = PAGE_PROMPTS[page]
        
        # Format prompt dengan data mentah website referensi (dibatasi 6000 karakter agar menghemat token)
        formatted_prompt = prompt_template.format(raw_data=cleaned_text[:6000], brand_name=brand)
        
        # Panggil LLM untuk menghasilkan konten
        raw_response = llm.generate_content(formatted_prompt, SYSTEM_INSTRUCTION)
        
        # Ekstraksi string JSON menggunakan Regex untuk membuang kalimat pengantar/basa-basi dari LLM
        json_match = re.search(r"\{.*\}", raw_response, re.DOTALL)
        if json_match:
            clean_json_str = json_match.group(0)
        else:
            clean_json_str = raw_response.strip()
        
        try:
            # Mengubah teks respons menjadi struktur objek dictionary Python
            page_data = json.loads(clean_json_str)
        except Exception as e:
            print(f"    [!] Warning: Gagal otomatis parse JSON untuk {page}, menggunakan format teks mentah.")
            # Fallback jika struktur string JSON yang dihasilkan AI benar-benar rusak berat
            page_data = {"raw_output": raw_response}
        
        # Menyisipkan Footer Standar iLogo secara Otomatis ke dalam struktur data
        page_data["standard_footer"] = footer_text
        
        # Simpan hasil akhir sebagai file JSON terstruktur di folder output
        file_path = os.path.join(output_dir, f"{page}.json")
        with open(file_path, "w", encoding="utf-8") as out_file:
            json.dump(page_data, out_file, indent=4, ensure_ascii=False)
            
    print(f"\n[✓] Selesai! Semua konten teks untuk {brand.upper()} berhasil disimpan di folder: `{output_dir}`")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="iLogo AI Auto Website Generator (iAAWG) - CLI Mode")
    parser.add_argument("--brand", required=True, help="Nama brand IT (Contoh: zecurion)")
    parser.add_argument("--url", required=True, help="URL Website referensi brand (Contoh: zecurion.com)")
    
    args = parser.parse_args()
    
    # Jalankan orkestrasi utama dalam event loop async
    asyncio.run(run_pipeline(args.brand, args.url))