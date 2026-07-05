# iLogo AI Auto Website Generator (iAAWG) — Phase 1 Foundation

iAAWG adalah sistem otomatisasi berbasis AI yang dirancang khusus untuk mempercepat pembuatan website subdomain brand di bawah naungan PT. iLogo Infralogy Indonesia. Sistem ini mengekstrak esensi informasi dari website resmi brand, memprosesnya menggunakan LLM, dan menghasilkan struktur konten terlokalisasi (Bahasa Indonesia) yang siap dideploy.

## Fitur Utama (Phase 1)
- **Engine Scraper Modern:** Menggunakan Playwright (Chromium Headless) untuk menangani arsitektur web modern yang membutuhkan Javascript Rendering.
- **Ekstraksi Teks Bersih:** Integrasi BeautifulSoup4 untuk menyaring elemen sampah (navigasi, footer, script) agar menghemat kuota token LLM.
- **Modular Provider Abstraction:** Fondasi kode siap pakai yang dapat dipertukarkan antar LLM provider (default: Groq API).
- **Rate Limit Guard:** Jeda waktu asinkron otomatis antar request halaman demi menjaga keamanan kuota API level pengembangan (Free Tier).
- **Auto-Footer Injection:** Penyisipan otomatis teks hak cipta standar iLogo pada setiap keluaran data halaman.

## Struktur Proyek saat ini
```text
iaawg/
├── config/
│   ├── settings.py
│   └── footer_template.txt
├── crawler/
│   ├── __init__.py
│   └── scraper.py
├── content/
│   ├── __init__.py
│   ├── generator.py
│   └── templates/
│       ├── __init__.py
│       └── prompts.py
├── output/
├── .env
├── .gitignore
├── main.py
├── requirements.txt
└── README.md

```

## Cara Instalasi & Penggunaan Lokal

1. **Clone repositori dan masuk ke direktori:**
```bash
cd iaawg

```


2. **Buat & aktifkan Virtual Environment:**
```bash
python -m venv venv
# Windows:
venv\Scripts\activate
# Linux/macOS:
source venv/bin/activate

```


3. **Install Dependensi & Browser Playwright:**
```bash
pip install -r requirements.txt
playwright install chromium

```


4. **Konfigurasi Environment:**
Buat file bernama `.env` di root direktori dan masukkan Groq API Key Anda:
```text
GROQ_API_KEY=gsk_your_api_key_here

```


5. **Jalankan Pipeline CLI:**
```bash
python main.py --brand zecurion --url zecurion.com

```