# iLogo AI Auto Website Generator (iAAWG)

iAAWG adalah sistem otomatisasi berbasis AI yang dirancang khusus untuk mempercepat pembuatan website subdomain brand di bawah naungan PT. iLogo Infralogy Indonesia. Sistem ini mengekstrak esensi informasi dari website resmi brand, memprosesnya menggunakan LLM, menghasilkan struktur konten terlokalisasi (Bahasa Indonesia), memproses aset visual pendukung, serta menyediakan opsi draf lokal atau langsung mendeploy hasilnya ke CMS WordPress via REST API secara otomatis — **termasuk dalam format yang langsung dapat diedit melalui Elementor Free.**

## Fitur Utama
- **Interactive & Dynamic Web Interface:** Antarmuka berbasis web (FastAPI) yang bersih, dilengkapi **Live Dynamic Progress Bar (%)**, **Real-Time Token Usage Counter (Input & Output)** untuk memantau konsumsi kuota LLM secara instan, konsol log asinkron untuk memantau proses secara real-time, serta tombol **"Buka Pratinjau Lokal"** yang aktif otomatis setelah pembuatan selesai.
- **Smart Auto-Failover LLM Guard:** Sistem dilengkapi dengan mekanisme cadangan otomatis (*failover*) dinamis 3 lapis antara **Groq API**, **Cerebras Cloud API**, dan **GitHub Models (gpt-4o-mini)**. Jika provider utama mengalami *rate limit* (429), kehabisan kuota, atau *down* di tengah jalan, sistem secara cerdas akan mengalihkan proses pembuatan konten ke provider cadangan selanjutnya sesuai urutan prioritas yang dipilih pengguna tanpa menghentikan pipeline.
- **Dynamic Multi-Tenant WordPress Deploy:** Pengguna umum dapat memasukkan URL WordPress target, username, dan application password langsung dari formulir Web UI tanpa perlu mengubah file konfigurasi sistem backend.
- **Elementor Free Integration:** Setiap halaman yang di-deploy ke WordPress secara otomatis menyertakan meta `_elementor_data` berisi struktur layout lengkap. Halaman langsung dapat diedit menggunakan Elementor Free tanpa konfigurasi tambahan.
- **Multi-Template Layout System:** Operator dapat memilih dari 3 template layout profesional:
  - **Prestige** — putih bersih, layout 2-kolom, aksen border, cocok untuk Cybersecurity & Compliance
  - **Clarity** — sangat lega, centered, aksen angka besar, cocok untuk SaaS, Cloud & ERP
  - **Momentum** — hero berwarna brand, energik, cocok untuk Network, SD-WAN & Infrastruktur
  - **Otomatis** — sistem memilih template terbaik berdasarkan analisis kata kunci konten brand
- **Dynamic Brand Color Extraction:** Pengguna dapat mengunggah logo brand melalui Web UI. Sistem mengekstrak warna dominan dan menggunakannya sebagai tema utama di seluruh halaman. Fallback ke warna iLogo (#1E7E34) jika tidak ada logo.
- **Engine Scraper Modern:** Menggunakan Playwright (Chromium Headless) untuk menangani arsitektur web modern yang membutuhkan Javascript Rendering.
- **Ekstraksi Teks Bersih:** Integrasi BeautifulSoup4 untuk menyaring elemen sampah agar menghemat kuota token LLM.
- **Anti-Hallucination Guard & Auto-Retry:** Mekanisme pengulangan otomatis hingga 3 kali jika scraping gagal, dengan ambang batas minimum 500 karakter teks bersih.
- **Modular Provider Abstraction:** Fondasi kode siap pakai yang dapat dipertukarkan antar LLM provider (default: Groq API).
- **Dual Rate Limit Guard:** Jeda waktu asinkron otomatis antar request (35 detik untuk teks, 5 detik untuk visual) untuk menjaga kuota API.
- **Global Header & Footer via ElementsKit:** Header navigasi dan footer standar iLogo dideploy **sekali** per brand sebagai template global menggunakan ElementsKit Free. Template berlaku otomatis di seluruh halaman — untuk mengubah footer atau header, cukup update satu template tanpa menyentuh halaman satu per satu.
- **AI Visual Generation:** Integrasi `Pollinations.ai` untuk pembuatan hero banner secara dinamis.
- **Stock Photo Integration:** Pencarian gambar stok otomatis via **Unsplash API** dengan graceful fallback.
- **LLM-Micro Keyword Translator:** Sub-proses LLM untuk mengonversi topik Bahasa Indonesia menjadi 2-4 kata kunci Bahasa Inggris yang optimal untuk pencarian visual.
- **Local Draft Mode & Integrated Preview:** Pipeline lokal tanpa deploy ke WordPress. Output berupa JSON, gambar `.jpg`, dan `preview_lokal.html` berbasis Tailwind CSS.
- **Explicit Product URL Input:** Input URL produk eksplisit untuk kontrol lebih presisi dan penghematan token LLM.
- **WordPress REST API Auto-Deploy:** Deploy otomatis via `httpx` + Application Password, lengkap dengan upload media dan meta Elementor.
- **Multi-Running Mode Flexibility:** Kombinasi parameter operasi untuk efisiensi token dan keamanan data.

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
├── db/
│   ├── __init__.py
│   └── settings_store.py     # SQLite-backed API key management
├── visual/
│   ├── __init__.py
│   ├── color_extractor.py
│   ├── banner_gen.py
│   ├── image_fetch.py
│   └── preview_templates.py
├── wordpress/
│   ├── __init__.py
│   ├── client.py
│   ├── page_builder.py       # HTML builder (local preview fallback)
│   └── elementor_builder.py  # Elementor JSON builder (WordPress deploy)
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

> 💡 **Catatan Kredensial:** Khusus untuk konfigurasi WordPress, parameter di `.env` bertindak sebagai **Developer Fallback**. Jika pengguna akhir memasukkan kredensial langsung lewat Web UI, pengaturan di `.env` akan di-bypass otomatis.

> ⚙️ **API Key via UI:** Seluruh API key (Groq, Cerebras, GitHub, Unsplash) kini dapat dikelola langsung dari browser melalui `http://127.0.0.1:8000/settings` tanpa menyentuh file `.env`. Nilai yang disimpan di UI tersimpan di `iaawg_settings.db` dan mengambil prioritas lebih tinggi dari `.env`.

```text
GROQ_API_KEY=gsk_your_api_key_here
CEREBRAS_API_KEY=csk-your-api-key-here
UNSPLASH_API_KEY=your_unsplash_access_key_here
GITHUB_TOKEN=ghp_your_github_personal_access_token_here

# WordPress REST API Config (Developer Fallback / CLI Mode)
WP_URL=http://localhost/zecurion
WP_USERNAME=username_admin_anda
WP_APPLICATION_PASSWORD=xxxx xxxx xxxx xxxx xxxx
```

5. **Cara Menjalankan Sistem:**

### Opsi 1: Web UI (Sangat Direkomendasikan)

```bash
uvicorn web:app
```

Akses `http://127.0.0.1:8000`. Form mencakup:
- **Nama Brand** dan **URL Homepage**
- **URL Produk (opsional)** — per baris, sistem hanya memproses URL yang diberikan
- **Upload Logo Brand (opsional)** — warna dominan diekstrak sebagai tema
- **Template Layout Website** — Prestige / Clarity / Momentum / Otomatis (mempengaruhi pratinjau lokal **dan** WordPress)
- **Skip Generation Mode** dan **Local Draft Mode**
- **Target WordPress Deployment**

> ⚠️ **Windows:** Jangan gunakan `--reload`. Playwright tidak kompatibel dengan event loop yang digunakan auto-reload di Windows.

---

### Opsi 2: CLI

```bash
# A. Full Pipeline
python main.py --brand zecurion --url zecurion.com

# B. Dengan URL Produk Eksplisit
python main.py --brand zecurion --url zecurion.com --product-urls "https://zecurion.com/produk-a,https://zecurion.com/produk-b"

# C. Skip Generation (pakai JSON lokal)
python main.py --brand zecurion --skip-generation

# D. Local Draft (tanpa deploy WordPress)
python main.py --brand zecurion --url zecurion.com --skip-deploy

# E. Fast Offline Preview
python main.py --brand zecurion --skip-generation --skip-deploy

# F. Pilih Template Layout
python main.py --brand zecurion --url zecurion.com --template prestige
python main.py --brand zecurion --url zecurion.com --template clarity
python main.py --brand zecurion --url zecurion.com --template momentum

# G. Warna custom via CLI
python main.py --brand zecurion --url zecurion.com --primary-color "#FF5733"
```

---

## WordPress Plugins (Wajib untuk Deploy)

iAAWG memerlukan dua plugin WordPress pendamping agar proses deploy berjalan penuh dan otomatis. Kedua plugin ini **tidak tersedia di WordPress Plugin Directory** — file PHP-nya disertakan langsung di repositori ini.

> ⚠️ **Urutan aktivasi penting:** Aktifkan **ElementsKit** terlebih dahulu, baru aktifkan kedua plugin iAAWG di bawah ini.

---

### Plugin 1 — `iaawg-elementor-css-regen`

Memicu regenerasi CSS Elementor secara otomatis setiap kali halaman di-deploy via REST API. Tanpa plugin ini, halaman mungkin perlu dibuka di editor Elementor sekali agar CSS ter-compile dan tampilan muncul dengan benar.

**Instalasi:**
1. Buat folder `wp-content/plugins/iaawg-elementor-css-regen/`
2. Letakkan `iaawg-elementor-css-regen.php` di dalamnya
3. Aktifkan dari WordPress Admin → Plugins

---

### Plugin 2 — `iaawg-elementskit-rest-bridge`

Melakukan dua hal sekaligus:
1. **Membuka akses REST API** untuk CPT `elementskit_template` milik ElementsKit (yang secara default tidak diekspos ke REST), serta mendaftarkan semua meta field yang diperlukan agar bisa ditulis via REST.
2. **Auto-aktivasi template global** — setiap kali iAAWG membuat header/footer template via REST, plugin ini langsung mendaftarkannya ke `elementskit_header_footer_data` di `wp_options` (registry internal ElementsKit yang menentukan template mana yang ditampilkan di frontend). Ini menggantikan langkah manual yang biasanya dilakukan lewat UI ElementsKit → Header & Footer → Save.

**Instalasi:**
1. Buat folder `wp-content/plugins/iaawg-elementskit-rest-bridge/`
2. Letakkan `iaawg-elementskit-rest-bridge.php` di dalamnya
3. Aktifkan dari WordPress Admin → Plugins

---

### Plugin yang Diperlukan dari WordPress Plugin Directory

| Plugin | Sumber | Keterangan |
|---|---|---|
| **Elementor** (Free) | wordpress.org/plugins | Page builder utama |
| **ElementsKit Elementor Addons** (Free) | wordpress.org/plugins | Wajib untuk global header/footer |

---

## Arsitektur Elementor Deploy

### Halaman Konten

Setiap halaman konten (Beranda, Solusi, Produk, Kontak) yang di-deploy menyertakan 5 meta field:

| Meta Key | Nilai | Keterangan |
|---|---|---|
| `_elementor_data` | JSON string | Struktur layout konten halaman |
| `_elementor_edit_mode` | `"builder"` | Mengaktifkan Elementor |
| `_elementor_template_type` | `"wp-page"` | Tipe halaman |
| `_elementor_version` | `"3.21.0"` | Versi Elementor |
| `_elementor_page_settings` | object | `page_layout: "default"` — menggunakan theme wrapper sehingga ElementsKit dapat menyisipkan header/footer global |

### Global Header & Footer

Header dan footer **tidak disematkan ke setiap halaman**. Keduanya dideploy sekali sebagai CPT `elementskit_template` dengan meta tambahan:

| Meta Key | Nilai | Keterangan |
|---|---|---|
| `_elementskit_template_type` | `"header"` / `"footer"` | Menentukan peran template |
| `_elementskit_conditions` | JSON string | Kondisi tampil: `general` = seluruh situs |

ElementsKit membaca registry dari `wp_options` (`elementskit_header_footer_data`) dan menyisipkan template yang sesuai di setiap halaman secara otomatis. Plugin `iaawg-elementskit-rest-bridge` yang menulis ke registry tersebut setelah setiap deploy.

### Widget Elementor Free yang Digunakan

`heading`, `text-editor`, `button`, `image`, `spacer`, `divider`