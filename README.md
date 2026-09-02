# iLogo AI Auto Website Generator (iAAWG)

iAAWG adalah sistem otomatisasi berbasis AI yang dirancang khusus untuk mempercepat pembuatan website subdomain brand di bawah naungan PT. iLogo Infralogy Indonesia. Sistem ini mengekstrak esensi informasi dari website resmi brand, memprosesnya menggunakan LLM, menghasilkan struktur konten terlokalisasi (Bahasa Indonesia), memproses aset visual pendukung, serta menyediakan opsi draf lokal atau langsung mendeploy hasilnya ke CMS WordPress via REST API secara otomatis — **termasuk dalam format yang langsung dapat diedit melalui Elementor Free.**

Sistem terdiri dari dua pipeline yang berbagi fondasi (LLM failover engine, WordPress client, settings DB, image fetcher):

1. **Website Generator** — pipeline utama untuk membangun subdomain brand baru (Beranda, Solusi, Produk, Kontak) dari scrape situs brand.
2. **Blog Autopost Generator** — pipeline sekunder untuk menghasilkan artikel blog SEO (1500+ kata) dalam batch dan menjadwalkan autopost ke WordPress via native scheduler. Cocok untuk maintenance konten setelah website berdiri.

## Fitur Utama
- **Interactive & Dynamic Web Interface:** Antarmuka berbasis web (FastAPI) yang bersih, dilengkapi **Live Dynamic Progress Bar (%)**, **Real-Time Token Usage Counter (Input & Output)** untuk memantau konsumsi kuota LLM secara instan, konsol log asinkron untuk memantau proses secara real-time, serta tombol **"Buka Pratinjau Lokal"** yang aktif otomatis setelah pembuatan selesai.
- **Smart Auto-Failover LLM Guard:** Sistem dilengkapi dengan mekanisme cadangan otomatis (*failover*) dinamis 2 lapis antara **OpenAI API (GPT-4.1 mini)** sebagai provider utama dan **Groq API** sebagai cadangan. Jika provider utama mengalami *rate limit* (429), kehabisan kuota, atau *down* di tengah jalan, sistem secara cerdas akan mengalihkan proses pembuatan konten ke provider cadangan tanpa menghentikan pipeline.
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
- **Modular Provider Abstraction:** Fondasi kode siap pakai yang dapat dipertukarkan antar LLM provider (default: OpenAI API).
- **Visual Rate Limit Guard:** Jeda waktu asinkron otomatis 5 detik antar request visual (banner & stock photo) untuk menjaga stabilitas pipeline.
- **Global Header & Footer via ElementsKit:** Header navigasi dan footer standar iLogo dideploy **sekali** per brand sebagai template global menggunakan ElementsKit Free. Template berlaku otomatis di seluruh halaman — untuk mengubah footer atau header, cukup update satu template tanpa menyentuh halaman satu per satu.
- **Smart Slider 3 Auto Hero Slider:** Setiap deploy brand otomatis menghasilkan hero slider di halaman Beranda menggunakan Smart Slider 3 Free. Sistem membungkus 3 banner AI (home / solusi / produk) ke dalam template `.ss3` dan meng-import-nya via Public API resmi Nextend. Slider yang dihasilkan **100% dapat diedit operator** di WP Admin → Smart Slider (ganti gambar, edit teks, tambah/hapus slide, atur animasi & autoplay). Kalau plugin belum diinstall di WP target, pipeline tetap jalan normal — halaman Beranda otomatis fallback ke hero image biasa.
- **AI Visual Generation:** Integrasi `Pollinations.ai` untuk pembuatan hero banner secara dinamis.
- **Stock Photo Integration:** Pencarian gambar stok otomatis via **Unsplash API** dengan graceful fallback.
- **LLM-Micro Keyword Translator:** Sub-proses LLM untuk mengonversi topik Bahasa Indonesia menjadi 2-4 kata kunci Bahasa Inggris yang optimal untuk pencarian visual.
- **Local Draft Mode & Integrated Preview:** Pipeline lokal tanpa deploy ke WordPress. Output berupa JSON, gambar `.jpg`, dan `preview_lokal.html` berbasis Tailwind CSS.
- **Dual Product Mode:** Dua mode pemrosesan produk saat URL eksplisit diisi:
  - **Halaman Individual** — setiap URL produk menghasilkan satu halaman WordPress tersendiri (default)
  - **Mode Katalog** — produk dari beberapa URL dikelompokkan otomatis berdasarkan kategori. Setiap kategori menghasilkan satu halaman katalog di WordPress (`/produk/{kategori}/`). Klasifikasi kategori dilakukan secara deterministik dari path URL (bukan LLM), sehingga tidak ada risiko halusinasi.
- **WordPress REST API Auto-Deploy:** Deploy otomatis via `httpx` + Application Password, lengkap dengan upload media dan meta Elementor.
- **Multi-Running Mode Flexibility:** Kombinasi parameter operasi untuk efisiensi token dan keamanan data.
- **Append Mode — Incremental Product Deployment:** Menambahkan halaman produk baru ke site yang sudah pernah dideploy tanpa mengulang generate/deploy halaman Home, Solusi, Contact, header, footer, atau slider. Cocok untuk skenario update katalog (brand rilis produk baru, takedown produk lama) tanpa harus rebuild seluruh site dari nol. Halaman produk baru otomatis ditambahkan sebagai child dari `/produk/` existing dan item baru di-append ke nav menu di bawah dropdown "Produk" — item lama tetap utuh. Untuk hapus halaman, gunakan wp-admin secara langsung.
- **Blog Autopost Generator (Pipeline Sekunder):** Pipeline terpisah untuk menghasilkan artikel blog SEO (1500+ kata per artikel) dalam batch dan menjadwalkan autopost ke WordPress. Konten wajib berbasis materi referensi (scrape homepage + URL tambahan + manual paste) untuk mencegah halusinasi. Prompt sepenuhnya generik — cocok untuk brand di industri apa pun. Autopost menggunakan native WordPress scheduler (`status: future` + wp-cron), tanpa scheduler tambahan di sisi Python. Lihat section **Blog Autopost Generator** di bawah untuk detail.

## Struktur Proyek
```text
iaawg/
├── assets/
│   └── sliders/
│       └── hero-template.ss3     # Template Smart Slider 3 (bundle export)
├── config/
│   ├── settings.py
├── crawler/
│   ├── __init__.py
│   └── scraper.py
├── content/
│   ├── __init__.py
│   ├── generator.py              # LLM engine + failover (shared)
│   ├── blog_generator.py         # Orchestrator blog: materi → topik → artikel
│   └── templates/
│       ├── __init__.py
│       ├── prompts.py            # Prompt website (home, solusi, produk, kontak)
│       └── blog_prompts.py       # Prompt blog SEO (topik + artikel 1500+ kata)
├── db/
│   ├── __init__.py
│   └── settings_store.py         # SQLite-backed API key management
├── visual/
│   ├── __init__.py
│   ├── color_extractor.py
│   ├── banner_gen.py
│   ├── image_fetch.py
│   └── preview_templates.py
├── wordpress/
│   ├── __init__.py
│   ├── client.py                 # WP REST client (shared: page + post + media)
│   ├── page_builder.py           # HTML builder (local preview fallback)
│   ├── elementor_builder.py      # Elementor JSON builder (website deploy)
│   ├── smartslider_deploy.py     # Orchestrator import slider SS3 per brand
│   └── blog_deploy.py            # Deploy blog: kategori, tag, featured img, scheduled
├── wordpress-plugins/            # Plugin PHP pendamping (lihat bagian bawah)
├── output/                       # Folder penyimpanan data hasil generate per brand
├── .env
├── .gitignore
├── main.py                       # CLI entry pipeline website
├── web.py                        # Aplikasi Web UI FastAPI (website + registrasi blog)
├── web_blog_routes.py            # Route blog: /blog, /blog/generate, /blog/status
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

> ⚙️ **API Key via UI:** Seluruh API key (OpenAI, Groq, Unsplash) kini dapat dikelola langsung dari browser melalui `http://127.0.0.1:8000/settings` tanpa menyentuh file `.env`. Nilai yang disimpan di UI tersimpan di `iaawg_settings.db` dan mengambil prioritas lebih tinggi dari `.env`.

```text
OPENAI_API_KEY=sk-your-openai-api-key-here
GROQ_API_KEY=gsk_your_groq_api_key_here
UNSPLASH_API_KEY=your_unsplash_access_key_here

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

Akses:
- `http://127.0.0.1:8000/`         → **Website Generator** (pipeline utama)
- `http://127.0.0.1:8000/blog`     → **Blog Autopost Generator** (pipeline sekunder)
- `http://127.0.0.1:8000/settings` → API key management

Form Website Generator mencakup:
- **Nama Brand** dan **URL Homepage**
- **URL Produk (opsional)** — per baris, sistem hanya memproses URL yang diberikan
- **Mode Produk** — muncul otomatis saat URL Produk diisi: *Halaman Individual* atau *Mode Katalog*
- **Upload Logo Brand (opsional)** — warna dominan diekstrak sebagai tema
- **Template Layout Website** — Prestige / Clarity / Momentum / Otomatis (mempengaruhi pratinjau lokal **dan** WordPress)
- **Skip Generation Mode** dan **Local Draft Mode**
- **Append Mode** — hanya deploy produk baru dari URL yang diisi ke site yang sudah ada; halaman statis, header, footer, dan slider tidak diproses ulang
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

# H. Append Mode (tambah produk baru ke site existing)
python main.py --brand zecurion --append-mode --product-urls "https://zecurion.com/produk-baru-1,https://zecurion.com/produk-baru-2"
```

> 💡 **Mode Katalog** hanya tersedia melalui Web UI. CLI selalu menggunakan mode Halaman Individual.

> 🔁 **Append Mode** wajib disertai `--product-urls` dan kredensial WordPress. Hanya mendukung Individual Mode; halaman induk `/produk/` dan nav menu diambil otomatis dari site existing via WP REST API. Untuk hapus halaman, gunakan wp-admin.

> 📝 **Blog Autopost hanya tersedia via Web UI** (`/blog`). Belum ada CLI equivalent — pipeline blog dirancang interaktif karena butuh keputusan operator per batch (pilih materi, jumlah artikel, jadwal).

---

## Blog Autopost Generator

Pipeline sekunder untuk menghasilkan artikel blog SEO dalam batch dan (opsional) menjadwalkan autopost ke WordPress. Berbeda konsep dengan Website Generator: kalau Website Generator adalah *one-shot deploy* untuk membangun subdomain baru, Blog Autopost adalah *recurring content generation* untuk maintenance blog setelah situs berdiri.

### Prinsip Desain

- **Materi wajib, tidak boleh mengarang.** Prompt secara eksplisit melarang LLM mengarang nama produk, fitur, angka, atau sertifikasi yang tidak ada di materi referensi. Kalau tidak ada materi, batch di-reject di server side.
- **Prompt generik.** Tidak ada asumsi industri di level prompt — sistem cocok untuk brand di sektor apa pun (cybersecurity, network, SaaS, ERP, dll). Semua nuansa brand-specific datang dari `{raw_data}` yang di-inject.
- **1 artikel = 1 LLM call.** Bukan sekali generate banyak artikel dalam satu response. Alasannya: granular failover per artikel, menghindari truncate token, dan progress bar per-artikel.
- **Native WordPress scheduler.** Autopost pakai `status: future` + `date` di WP REST — tidak ada scheduler Python-side. wp-cron di target yang eksekusi.

### Sumber Materi (Minimal Salah Satu Wajib)

Form `/blog` menyediakan 3 sumber yang bisa dikombinasikan menjadi satu blob materi:

1. **Homepage URL** — di-scrape via Playwright existing (retry 3×, deteksi Cloudflare, cap 4000 char).
2. **URL Referensi Tambahan** — multiline, misal product page, about, use case, whitepaper. Dipanggil satu per satu (cap 4000 char/URL).
3. **Manual Content** — textarea untuk paste bebas. Berguna kalau situs brand di-block Cloudflare atau kalau operator punya materi internal (press release, product brief) yang lebih kaya dari situs publik. Cap 8000 char.

Kalau ketiganya kosong dan tidak ada yang berhasil di-scrape, sistem menolak batch dengan error jelas.

### Flow Pipeline

```
User submit form /blog
    ↓
Validasi: keyword + minimal 1 sumber materi + jumlah artikel (1-15)
    ↓
Background task:
    A. collect_brand_material()  → gabungkan homepage + refs + manual → raw_data
    B. generate_topics()         → 1 LLM call: N brief topik dari raw_data
    C. Loop N kali:
        generate_article()       → 1 LLM call: artikel 1500+ kata dari brief + raw_data
        (wajib menyisipkan ≥1 internal link + ≥1 external link per artikel)
    D. (Opsional) Fetch featured image via Unsplash per artikel
    E. Simpan sebagai DRAFT batch (bukan deploy) → output/<brand>/blog_drafts/<batch_id>/batch.json
    ↓
Operator review & edit di /blog/review/{batch_id} (WYSIWYG, upload gambar custom)
    ↓
Operator submit publish (bisa partial per-artikel) → POST /blog/draft/{batch_id}/publish
    - ensure_category (get-or-create)
    - ensure_tags per artikel (get-or-create)
    - upload featured image → attachment ID
    - tambahkan CTA box otomatis di akhir konten
    - create post: status "future" + date staggered
    → WP wp-cron publish otomatis di tanggal target
```

> ⚠️ **Generate ≠ Deploy.** `/blog/generate` hanya menghasilkan draft yang bisa direview/diedit — tidak pernah langsung mengirim ke WordPress. Kredensial WordPress di form generate bersifat opsional dan hanya dipakai read-only (ambil kandidat internal link + deteksi halaman Kontak untuk CTA); kredensial publish sesungguhnya diinput ulang operator di halaman review dan tidak pernah disimpan ke disk.

### Field Form `/blog`

| Section | Field | Keterangan |
|---|---|---|
| Brand & Keyword | Nama Brand *, Keyword Utama *, Keyword Tambahan | Keyword utama muncul di judul, meta, intro, min 1 H2, penutup |
| Sumber Materi | Homepage URL, URL Referensi (multiline), Manual Content | Minimal salah satu wajib |
| Konfigurasi Batch | Jumlah Artikel * (1-15), LLM Chain | LLM chain: sama seperti pipeline website |
| WordPress Deploy | WP URL, Username, App Password, Kategori, Featured Image | Kategori auto-created; featured image ambil dari Unsplash |
| Jadwal Autopost | Start Date, Interval Hari, Jam Publish | Uncheck untuk publish semua sekaligus |

### Output & Audit Trail

Setiap artikel yang dihasilkan menampilkan di card:
- **Word count** (hijau ≥1500, kuning <1500)
- **Angle topik** (how-to, listicle, comparison, dst)
- **Tags** yang ter-generate
- **Status deploy** (id post + tanggal terjadwal kalau future)
- **Material anchor** — kalimat yang menjelaskan bagian materi mana yang jadi jangkar topik ini (audit trail transparansi: apakah artikel benar-benar derived dari materi atau melenceng)

### Route API

| Method | Path | Keterangan |
|---|---|---|
| GET | `/blog` | HTML form |
| POST | `/blog/generate` | Trigger background task (multipart form) → hasil disimpan sebagai draft |
| GET | `/blog/status` | Polling status: progress, log, articles yang sudah selesai |
| GET | `/blog/drafts` | List semua draft batch |
| GET | `/blog/review/{batch_id}` | Halaman review & edit WYSIWYG per batch |
| GET | `/blog/draft/{batch_id}` | Ambil JSON draft lengkap |
| POST | `/blog/draft/{batch_id}/{article_id}` | Edit field artikel (title, seo_title, slug, tags, meta_description, content, excerpt) |
| POST | `/blog/draft/{batch_id}/{article_id}/image` | Upload gambar featured custom |
| POST | `/blog/draft/{batch_id}/publish` | Publish (bisa partial) ke WordPress — kredensial WP diinput di sini |

### Integrasi ke `web.py`

Route blog didaftarkan sebagai modul terpisah untuk menjaga `web.py` tetap ringkas:

```python
from web_blog_routes import register_blog_routes

# ... setelah app = FastAPI(...) dan startup event ...
register_blog_routes(app, website_is_running_getter=lambda: is_running)
```

Argumen `website_is_running_getter` mencegah pipeline website dan batch blog jalan bersamaan sehingga tidak bentrok di quota LLM.

### Batasan & Catatan

- **Max 15 artikel per batch** — di atas itu risiko rate limit + user frustration polling terlalu lama. Kalau butuh banyak, jalankan batch berulang.
- **SEO on-page (Yoast / All In One SEO)** — tiap artikel mengirim focus keyphrase (`main_keyword` yang sama untuk seluruh batch), `seo_title` (judul SEO terpisah dari judul halaman, 55-60 karakter), dan meta description ke kedua plugin: field `_yoast_wpseo_focuskw` / `_yoast_wpseo_metadesc` / `_yoast_wpseo_title` (Yoast) dan `aioseo_meta_data` (AIOSEO — didukung native oleh plugin itu sendiri lewat REST, tidak butuh bridge). Featured image juga diberi `alt_text` yang memuat keyword utama. Slug dipaksa mengandung keyword utama secara programatik; title/seo_title/meta_description/H2 divalidasi lewat `_check_seo_requirements()` dan dapat 1x percobaan perbaikan otomatis (`SEO_FIX_PROMPT`) kalau prompt awal tidak dipatuhi LLM — lihat `content/blog_generator.py`. Karena satu batch berbagi satu focus keyphrase, cek "Previously used keyphrase" Yoast tetap bisa muncul di artikel ke-2+ per batch (trade-off yang disengaja). `wordpress-plugins/iaawg-yoast-rest-bridge.php` tersedia sebagai fallback opsional untuk instalasi Yoast yang belum mendaftarkan field-nya sendiri ke REST — tidak wajib diaktifkan (Yoast versi terbaru sudah otomatis mendukung ini).
- **`max_tokens=5500` di `content/generator.py`** — cukup untuk artikel 1500 kata Indonesia. Perubahan nilai ini juga berdampak ke pipeline website.
- **Belum ada topic dedup antar batch** — kalau brand sama di-generate berulang, topik bisa mirip. Extension ringan: tabel SQLite `blog_topic_history` (brand, title, generated_at) yang di-inject ke prompt sebagai "hindari topik yang sudah pernah dibuat".

---

## WordPress Plugins (Wajib untuk Deploy)

iAAWG memerlukan tiga plugin WordPress pendamping agar proses deploy berjalan penuh dan otomatis. Ketiga plugin ini **tidak tersedia di WordPress Plugin Directory** — file PHP-nya disertakan langsung di repositori ini di folder `wordpress-plugins/`.

> ⚠️ **Urutan aktivasi penting:** Aktifkan **Elementor**, **ElementsKit**, dan **Smart Slider 3** (semua Free, dari WP Plugin Directory) terlebih dahulu, baru aktifkan ketiga plugin iAAWG di bawah ini.

> 📝 **Untuk Blog Autopost saja**, ketiga plugin di bawah **tidak wajib** — Blog Autopost menggunakan CPT `post` bawaan WordPress + REST API standar. Tapi tetap disarankan diaktifkan kalau site juga digunakan untuk Website Generator.
>
> Ada satu plugin ke-4, `iaawg-yoast-rest-bridge` (lihat folder `wordpress-plugins/`), yang **opsional** — fallback untuk instalasi Yoast SEO yang belum mendaftarkan field-nya sendiri ke REST API. Tidak perlu diaktifkan di instalasi Yoast versi terbaru (sudah terverifikasi bekerja tanpa plugin ini).

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

### Plugin 3 — `iaawg-smartslider-bridge`

Membuka satu REST endpoint (`POST /wp-json/iaawg/v1/smartslider/import`) yang menerima file `.ss3` (bundle export Smart Slider 3) dari iAAWG dan meneruskannya ke Public PHP API resmi Nextend (`\Nextend\SmartSlider3\PublicApi\Project::import()`). Pendekatan ini menjamin slider yang di-import **100% valid dari sisi Smart Slider 3** — editor slider di WP Admin tetap normal (bukan blank canvas) sehingga operator bebas mengedit gambar, teks, animasi, dan menambah/menghapus slide sesuai kebutuhan setelah deploy.

**Instalasi:**
1. Buat folder `wp-content/plugins/iaawg-smartslider-bridge/`
2. Letakkan `iaawg-smartslider-bridge.php` di dalamnya
3. Aktifkan dari WordPress Admin → Plugins

---

### Plugin yang Diperlukan dari WordPress Plugin Directory

| Plugin | Sumber | Keterangan |
|---|---|---|
| **Elementor** (Free) | wordpress.org/plugins | Page builder utama |
| **ElementsKit Elementor Addons** (Free) | wordpress.org/plugins | Wajib untuk global header/footer |
| **Smart Slider 3** (Free) | wordpress.org/plugins | Engine slider hero di halaman Beranda |

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

### Hero Slider (Smart Slider 3)

Slider hero di halaman Beranda dibuat dari template `assets/sliders/hero-template.ss3` (bundle export standar Smart Slider 3 berisi PHP-serialized config + folder gambar). Alur per brand:

1. Modul `wordpress/smartslider_deploy.py` membaca template, meng-overwrite 3 slot gambar (`slide-1.jpg`, `slide-2.jpg`, `slide-3.jpg`) dengan banner AI brand terkait (home / solusi / produk) tanpa mengubah nama file — supaya referensi di dalam PHP-serialized `data` tetap valid.
2. File `.ss3` yang telah disesuaikan dikirim via multipart ke endpoint bridge (`POST /wp-json/iaawg/v1/smartslider/import`).
3. Plugin `iaawg-smartslider-bridge` memanggil `\Nextend\SmartSlider3\PublicApi\Project::import()` dan mengembalikan `slider_id`.
4. `build_home()` menerima shortcode `[smartslider3 slider="X"]` via parameter `slider_shortcode` dan menyisipkannya sebagai section pertama halaman Beranda menggunakan widget `shortcode` Elementor Free. Saat slider aktif, hero image bawaan otomatis di-skip untuk mencegah *double hero*.

Untuk mengganti desain slider (jumlah slide, layout, animasi, autoplay, dimensi, dll.), operator cukup meng-export ulang template dari Smart Slider 3 di WP dev dan mengganti file `assets/sliders/hero-template.ss3` — tidak perlu perubahan kode Python maupun PHP.

### Widget Elementor Free yang Digunakan

`heading`, `text-editor`, `button`, `image`, `spacer`, `divider`, `shortcode`


-----
