# iLogo AI Auto Website Generator (iAAWG) — Phase 2 WordPress Integration

iAAWG adalah sistem otomatisasi berbasis AI yang dirancang khusus untuk mempercepat pembuatan website subdomain brand di bawah naungan PT. iLogo Infralogy Indonesia. Sistem ini mengekstrak esensi informasi dari website resmi brand, memprosesnya menggunakan LLM, menghasilkan struktur konten terlokalisasi (Bahasa Indonesia), dan langsung mendeploy ke CMS WordPress via REST API secara otomatis.

## Fitur Utama (Phase 2)
- **Engine Scraper Modern:** Menggunakan Playwright (Chromium Headless) untuk menangani arsitektur web modern yang membutuhkan Javascript Rendering.
- **Ekstraksi Teks Bersih:** Integrasi BeautifulSoup4 untuk menyaring elemen sampah (navigasi, footer, script) agar menghemat kuota token LLM.
- **Modular Provider Abstraction:** Fondasi kode siap pakai yang dapat dipertukarkan antar LLM provider (default: Groq API).
- **Rate Limit Guard:** Jeda waktu asinkron otomatis antar request halaman demi menjaga keamanan kuota API level pengembangan (Free Tier).
- **Auto-Footer Injection:** Penyisipan otomatis teks hak cipta standar iLogo pada setiap keluaran data halaman dan deployment WordPress.
- **WordPress REST API Auto-Deploy:** Integrasi tanpa hambatan menggunakan `httpx` dan sistem *Application Password* untuk membuat halaman (*Pages*) dan artikel (*Posts*) secara otomatis.
- **Dual Running Mode Option:** Pilihan fleksibel untuk menjalankan *full pipeline* atau melewati proses LLM dengan menggunakan data JSON lokal yang sudah diekstrak sebelumnya untuk efisiensi token.

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
├── wordpress/
│   ├── __init__.py
│   ├── client.py
│   └── page_builder.py
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
Buat atau perbarui file bernama `.env` di root direktori dan lengkapi konfigurasi berikut:

```text
GROQ_API_KEY=gsk_your_api_key_here

# WordPress REST API Config
WP_URL=[https://subdomain-anda.ilogo.co.id](https://subdomain-anda.ilogo.co.id)
WP_USERNAME=username_admin_anda
WP_APPLICATION_PASSWORD=xxxx xxxx xxxx xxxx xxxx

```

5. **Jalankan Pipeline CLI (2 Pilihan Opsi):**
**Opsi 1: Full Pipeline (Crawl + LLM Generate + Deploy WordPress)**
```bash
python main.py --brand zecurion --url zecurion.com

```


**Opsi 2: Skip LLM (Hanya Deploy ke WordPress menggunakan JSON lokal yang sudah ada)**
```bash
python main.py --brand zecurion --skip-llm

```