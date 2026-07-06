# iLogo AI Auto Website Generator (iAAWG)

iAAWG adalah sistem otomatisasi berbasis AI yang dirancang khusus untuk mempercepat pembuatan website subdomain brand di bawah naungan PT. iLogo Infralogy Indonesia. Sistem ini mengekstrak esensi informasi dari website resmi brand, memprosesnya menggunakan LLM, menghasilkan struktur konten terlokalisasi (Bahasa Indonesia), memproses aset visual pendukung, dan langsung mendeploy hasilnya ke CMS WordPress via REST API secara otomatis.

## Fitur Utama
- **Interactive & Dynamic Web Interface:** Antarmuka berbasis web (FastAPI) yang bersih, dilengkapi **Live Dynamic Progress Bar (%)** dan konsol log asinkron untuk memantau transisi pembangunan halaman secara real-time.
- **Dynamic Multi-Tenant WordPress Deploy:** Pengguna umum dapat memasukkan URL WordPress target, username, dan application password langsung dari formulir Web UI tanpa perlu mengubah file konfigurasi sistem backend.
- **Engine Scraper Modern:** Menggunakan Playwright (Chromium Headless) untuk menangani arsitektur web modern yang membutuhkan Javascript Rendering.
- **Ekstraksi Teks Bersih:** Integrasi BeautifulSoup4 untuk menyaring elemen sampah (navigasi, footer, script) agar menghemat kuota token LLM.
- **Modular Provider Abstraction:** Fondasi kode siap pakai yang dapat dipertukarkan antar LLM provider (default: Groq API).
- **Dual Rate Limit Guard:** Jeda waktu asinkron otomatis antar request halaman (12 detik untuk teks konten) dan buffer stabilitas request visual (5 detik) demi menjaga keamanan kuota API level pengembangan.
- **Auto-Footer Injection:** Penyisipan otomatis teks hak cipta standar iLogo pada setiap keluaran data halaman dan deployment WordPress.
- **AI Visual Generation:** Integrasi generator gambar modular menggunakan `Pollinations.ai` untuk pembuatan aset *hero banner* secara dinamis.
- **Stock Photo Integration:** Pencarian dan pengambilan gambar stok orisinal secara otomatis menggunakan **Unsplash API Key** dengan mekanisme *graceful fallback* jika aset tidak ditemukan.
- **LLM-Micro Keyword Translator:** Memanfaatkan sub-proses LLM minimal untuk mengonversi ringkasan topik halaman Bahasa Indonesia menjadi 2-4 kata kunci Bahasa Inggris yang bersih agar hasil pencarian gambar dan spanduk AI lebih akurat dan profesional.
- **WordPress REST API Auto-Deploy:** Integrasi tanpa hambatan menggunakan `httpx` dan sistem *Application Password* untuk mengunggah aset media gambar sekaligus membuat halaman (*Pages*) dan artikel (*Posts*) secara otomatis.
- **Dual Running Mode Option:** Pilihan fleksibel untuk menjalankan *full pipeline* atau melewati proses pembuatan teks utama dengan menggunakan data JSON lokal demi efisiensi token, namun tetap mengeksekusi visualisasi dan deployment.

## Struktur Proyek
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
├── visual/
│   ├── __init__.py
│   ├── color_extractor.py
│   ├── banner_gen.py
│   └── image_fetch.py
├── wordpress/
│   ├── __init__.py
│   ├── client.py
│   └── page_builder.py
├── output/
├── .env
├── .gitignore
├── main.py
├── web.py            # Aplikasi Web UI (FastAPI)
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

4. **Konfigurasi Environment (.env)**
Buat atau perbarui file bernama `.env` di root direktori.



> 💡 **Catatan Kredensial:** Parameter API Key di bawah ini wajib diisi untuk kebutuhan backend. Khusus untuk konfigurasi WordPress, parameter di `.env` bertindak sebagai **Developer Fallback**. Jika pengguna akhir memasukkan kredensial langsung lewat Web UI, pengaturan WordPress di file `.env` akan di-bypass secara otomatis demi keamanan.
> 
> 

```text
GROQ_API_KEY=gsk_your_api_key_here
UNSPLASH_API_KEY=your_unsplash_access_key_here

# WordPress REST API Config (Developer Fallback / CLI Mode)
WP_URL=http://localhost/zecurion
WP_USERNAME=username_admin_anda
WP_APPLICATION_PASSWORD=xxxx xxxx xxxx xxxx xxxx

```

5. **Cara Menjalankan Sistem:**

### Opsi 1: Menggunakan Antarmuka Web UI (Sangat Direkomendasikan)

Jalankan server aplikasi lokal menggunakan perintah berikut:

```bash
uvicorn web:app

```

Buka peramban Anda dan akses tautan `http://127.0.0.1:8000`. Anda dapat mengisi data brand, URL target, memilih mode operasi, serta menentukan target situs WordPress tujuan langsung dari antarmuka grafis secara mudah.

> ⚠️ **PENTING (Khusus Pengguna Windows):** Jangan jalankan server dengan parameter `--reload` (misal: `uvicorn web:app --reload`). Fitur auto-reload pada Windows memaksa penggunaan *event loop* yang tidak mendukung pembuatan subproses eksternal, sehingga akan menyebabkan Playwright mengalami `NotImplementedError` saat membuka browser Chromium di background thread.
> 
> 

---

### Opsi 2: Menggunakan Terminal CLI Tradisional

Jika dijalankan melalui CLI, sistem akan otomatis membaca target deploy situs WordPress yang tertera pada file `.env`.

**A. Full Pipeline (Crawl + LLM Generate Text & Keywords + Deploy WordPress + Visual)**

```bash
python main.py --brand zecurion --url zecurion.com

```

**B. Skip Generation (Menggunakan JSON lokal yang sudah ada + Tetap Menjalankan Visual & Deploy WordPress)**

```bash
python main.py --brand zecurion --skip-generation

```