# iLogo AI Auto Website Generator (iAAWG)

iAAWG adalah sistem otomatisasi berbasis AI yang dirancang khusus untuk mempercepat pembuatan website subdomain brand di bawah naungan PT. iLogo Infralogy Indonesia. Sistem ini mengekstrak esensi informasi dari website resmi brand, memprosesnya menggunakan LLM, menghasilkan struktur konten terlokalisasi (Bahasa Indonesia), memproses aset visual pendukung, serta menyediakan opsi draf lokal atau langsung mendeploy hasilnya ke CMS WordPress via REST API secara otomatis.

## Fitur Utama
- **Interactive & Dynamic Web Interface:** Antarmuka berbasis web (FastAPI) yang bersih, dilengkapi **Live Dynamic Progress Bar (%)**, **Real-Time Token Usage Counter (Input & Output)** untuk memantau konsumsi kuota LLM secara instan, konsol log asinkron untuk memantau proses secara real-time, serta tombol **"Buka Pratinjau Lokal"** yang aktif otomatis setelah pembuatan selesai.
- **Dynamic Multi-Tenant WordPress Deploy:** Pengguna umum dapat memasukkan URL WordPress target, username, dan application password langsung dari formulir Web UI tanpa perlu mengubah file konfigurasi sistem backend.
- **Engine Scraper Modern:** Menggunakan Playwright (Chromium Headless) untuk menangani arsitektur web modern yang membutuhkan Javascript Rendering.
- **Ekstraksi Teks Bersih:** Integrasi BeautifulSoup4 untuk menyaring elemen sampah (navigasi, footer, script) agar menghemat kuota token LLM.
- **Modular Provider Abstraction:** Fondasi kode siap pakai yang dapat dipertukarkan antar LLM provider (default: Groq API).
- **Dual Rate Limit Guard:** Jeda waktu asinkron otomatis antar request halaman (35 detik untuk teks konten) guna mengantisipasi token limit (TPM) pada Groq API Free Tier saat memproses teks referensi besar, serta buffer stabilitas request visual (5 detik) demi menjaga keamanan kuota API.
- **Auto-Footer Injection:** Penyisipan otomatis teks hak cipta standar iLogo pada setiap keluaran data halaman dan deployment WordPress.
- **AI Visual Generation:** Integrasi generator gambar modular menggunakan `Pollinations.ai` untuk pembuatan aset *hero banner* secara dinamis.
- **Stock Photo Integration:** Pencarian dan pengambilan gambar stok orisinal secara otomatis menggunakan **Unsplash API Key** dengan mekanisme *graceful fallback* jika aset tidak ditemukan.
- **LLM-Micro Keyword Translator:** Memanfaatkan sub-proses LLM minimal untuk mengonversi ringkasan topik halaman Bahasa Indonesia menjadi 2-4 kata kunci Bahasa Inggris yang bersih agar hasil pencarian gambar dan spanduk AI lebih akurat dan profesional.
- **Local Draft Mode & Integrated Preview:** Opsi untuk menjalankan pipeline visual dan teks secara penuh di komputer lokal tanpa melakukan publikasi ke WordPress. Hasil akhir berupa file teks JSON, gambar `.jpg`, serta sebuah berkas **`preview_lokal.html` terintegrasi berbasis Tailwind CSS** yang disusun rapi di dalam folder brand masing-masing agar bisa langsung ditinjau oleh operator melalui browser.
- **WordPress REST API Auto-Deploy:** Integrasi tanpa hambatan menggunakan `httpx` dan sistem *Application Password* untuk mengunggah aset media gambar sekaligus membuat halaman (*Pages*) dan artikel (*Posts*) secara otomatis.
- **Multi-Running Mode Flexibility:** Pilihan fleksibel untuk mengombinasikan berbagai parameter operasi (seperti melewati proses pembuatan teks utama dengan data JSON lokal atau melewati proses deploy) demi efisiensi token dan keamanan data.

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
├── output/           # Folder penyimpanan data hasil generate per brand
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

Buka peramban Anda dan akses tautan `http://127.0.0.1:8000`. Anda dapat mengisi data brand, URL target, memilih mode operasi, serta menentukan target situs WordPress tujuan.

Jika Anda mencentang opsi **Local Draft Mode**, formulir isian kredensial WordPress akan otomatis dinonaktifkan. Setelah seluruh pipeline selesai berjalan, sebuah tombol hijau bertuliskan **"Buka Pratinjau Lokal"** akan muncul di panel kanan yang dapat diklik untuk membuka simulasi landing page berdesain Tailwind CSS langsung di tab baru browser Anda.

> ⚠️ **PENTING (Khusus Pengguna Windows):** Jangan jalankan server dengan parameter `--reload` (misal: `uvicorn web:app --reload`). Fitur auto-reload pada Windows memaksa penggunaan *event loop* yang tidak mendukung pembuatan subproses eksternal, sehingga akan menyebabkan Playwright mengalami `NotImplementedError` saat membuka browser Chromium di background thread.

---

### Opsi 2: Menggunakan Terminal CLI Tradisional

Sistem menyediakan beberapa parameter fleksibel untuk disesuaikan dengan skenario pengerjaan:

**A. Full Pipeline (Crawl + LLM Generate Text & Keywords + Visual + Deploy WordPress)**
*Membaca target deploy situs WordPress yang tertera pada file `.env`.*

```bash
python main.py --brand zecurion --url zecurion.com

```

**B. Skip Generation (Menggunakan JSON lokal yang sudah ada + Tetap Menjalankan Visual & Deploy WordPress)**

```bash
python main.py --brand zecurion --skip-generation

```

**C. Local Draft Mode (Crawl + LLM Generate Text & Keywords + Visual lokal, TANPA Deploy WordPress)**

```bash
python main.py --brand zecurion --url zecurion.com --skip-deploy

```

**D. Fast Offline Preview (Menggunakan JSON lokal + Visual lokal, TANPA LLM Text & TANPA Deploy WordPress)**
*Skenario terbaik untuk merender ulang visual dan tata letak HTML lokal secara instan tanpa menguras kuota token teks Groq.*

```bash
python main.py --brand zecurion --skip-generation --skip-deploy

```