# -*- coding: utf-8 -*-
"""
Prompt templates untuk Blog Autopost Generator.

Design principle (sama dengan `content/templates/prompts.py` yang dipakai
pipeline website):
  - Prompt bersifat GENERIK — tidak menyebut industri, produk, atau jenis
    brand tertentu. Semua nuansa brand-specific datang dari `{raw_data}`
    yang di-inject oleh caller (hasil scrape + manual input).
  - LLM WAJIB berbasis materi referensi. Kalau LLM mengarang produk, fitur,
    atau angka di luar materi → itu bug.
  - Placeholder pattern:
      {brand_name}         : nama brand (mis. "Zecurion", "Cisco", "SAP")
      {raw_data}           : materi referensi hasil scrape/manual
      {main_keyword}       : keyword utama (biasanya "{brand_name} Indonesia")
      {secondary_keywords} : keyword tambahan, comma-separated string
      {internal_link_candidates} : daftar kandidat URL milik brand sendiri
                                    (halaman statis + post lain yang sudah
                                    live), diambil via WordPress REST API —
                                    bukan dikarang LLM. Bisa "(tidak ada
                                    kandidat)".
      {external_links}     : daftar URL eksternal terpercaya yang di-input
                              operator (minimal 1) — bukan dikarang LLM.
"""


BLOG_SYSTEM_INSTRUCTION = """
Anda adalah SEO Content Writer profesional di PT. iLogo Infralogy Indonesia
yang menulis artikel blog berbahasa Indonesia untuk berbagai brand teknologi.

ATURAN PENTING:
1. Tulisan harus terasa natural, tidak kaku, dan tidak seperti hasil terjemahan
   mesin. Variasikan panjang kalimat dan gunakan transisi antar paragraf.
2. Pertahankan istilah teknis Bahasa Inggris jika istilah tersebut lebih umum
   digunakan di industri brand target (contoh umum: "endpoint", "firewall",
   "cloud", "SaaS", "SLA" — tapi ikuti terminologi khas brand yang ditemukan
   di materi referensi).
3. Output HARUS berupa valid JSON string murni — tanpa markdown triple backticks
   (```json) di awal maupun akhir, tanpa komentar, tanpa teks tambahan di luar
   objek JSON. Escape karakter khusus di dalam string sesuai spesifikasi JSON.
4. Setiap paragraf harus substansial (3-5 kalimat), bukan potongan pendek.
5. Framing brand: posisikan brand sebagai SOLUSI yang tersedia untuk pembaca,
   bukan pihak yang aktif berjualan. DILARANG frasa seperti "Hubungi [Brand]",
   "Tim ahli [Brand] siap membantu Anda", "bersama [Brand]", "[Brand] adalah
   partner terbaik Anda". BOLEH: "[Brand] Indonesia menyediakan...",
   "Dengan [Brand], organisasi dapat...", "Solusi [Brand] membantu...".
6. Hindari klaim yang tidak bisa diverifikasi ("nomor satu di dunia", "terbaik
   sepanjang masa", "digunakan oleh jutaan"). Gunakan diksi yang objektif.
7. WAJIB berbasis materi referensi. DILARANG mengarang nama produk, fitur,
   angka, sertifikasi, atau klien yang tidak ada di materi. Kalau materi
   terbatas, tulislah bagian yang lebih umum berdasarkan kategori/kapabilitas
   brand — jangan mengisi kekosongan dengan fabrikasi.
"""


TOPIC_GENERATION_PROMPT = """
Berdasarkan data referensi brand berikut, buatkan {n_topics} ide topik
artikel blog SEO untuk brand {brand_name}.

Data Referensi Brand:
{raw_data}

Keyword Utama: {main_keyword}
Keyword Tambahan: {secondary_keywords}

ATURAN TOPIK:
- Topik HARUS derived dari materi referensi. Kalau materi menyebut produk /
  kapabilitas / kasus penggunaan tertentu, prioritaskan topik seputar hal
  tersebut — jangan pilih topik yang tidak punya jangkar di materi.
- Judul harus punya SEARCH INTENT yang jelas — pilih dari salah satu angle
  berikut: informational, comparison, how-to, listicle, buyer-guide,
  thought-leadership, case-study.
- Judul HARUS mengandung salah satu keyword utama ATAU keyword tambahan
  secara natural (tidak boleh dipaksakan sehingga judul terasa aneh).
- Panjang judul: 45-70 karakter, catchy tapi tidak clickbait.
- Setiap topik harus unik dari sisi angle — jangan buat dua topik dengan
  sudut pandang yang sama meskipun keyword-nya beda.
- Distribusi angle: bervariasi dan sesuai dengan kekayaan materi. Kalau
  materi cukup kaya, campurkan how-to, listicle, comparison, dan
  thought-leadership. Kalau materi terbatas, pilih angle yang paling
  didukung materi — jangan paksakan angle yang butuh data yang tidak ada.
- JANGAN sarankan topik yang menuntut fakta spesifik (angka, sertifikasi,
  nama klien) yang tidak muncul di materi referensi.

Output JSON format wajib:
{{
  "topics": [
    {{
      "title": "Judul artikel SEO-friendly (45-70 karakter)",
      "angle": "how-to | listicle | comparison | buyer-guide | thought-leadership | case-study | informational",
      "target_keyword": "Keyword yang akan dioptimasi di artikel ini — pilih dari keyword utama atau tambahan",
      "material_anchor": "1 kalimat menyebutkan bagian materi referensi yang jadi jangkar topik ini (misal: 'produk X yang disebut sebagai unggulan untuk skenario Y')",
      "summary": "1-2 kalimat menjelaskan sudut pandang dan nilai artikel bagi pembaca"
    }}
  ]
}}
"""


ARTICLE_GENERATION_PROMPT = """
Tulis artikel blog SEO lengkap berbahasa Indonesia berdasarkan brief dan
materi referensi berikut.

Brand: {brand_name}
Judul: {title}
Angle: {angle}
Ringkasan Sudut Pandang: {summary}
Keyword Utama Wajib: {main_keyword}
Keyword Tambahan (sisipkan natural): {secondary_keywords}

Data Referensi Brand:
{raw_data}

Kandidat Link Internal (milik brand sendiri — pilih 1 yang paling relevan):
{internal_link_candidates}

Kandidat Link Eksternal (sumber referensi terpercaya — pilih 1 yang paling relevan):
{external_links}

PERSYARATAN ARTIKEL (WAJIB DIPATUHI):

1. SUMBER FAKTA:
   - Semua nama produk, fitur, kapabilitas, sertifikasi, kasus penggunaan,
     dan klaim tentang brand HARUS bersumber dari materi referensi.
   - DILARANG mengarang: nama produk yang tidak ada di materi, angka
     spesifik (persentase, jumlah klien, tahun berdiri) yang tidak ada di
     materi, sertifikasi/kepatuhan yang tidak disebutkan.
   - Kalau materi terbatas dan Anda perlu memperluas untuk memenuhi panjang,
     kembangkan dengan penjelasan umum tentang kategori/konsep terkait
     (misal: kalau materi menyebut brand adalah penyedia backup, Anda boleh
     menulis penjelasan umum tentang praktik backup — tapi jangan mengklaim
     brand punya fitur backup spesifik yang tidak disebutkan).

2. PANJANG: MINIMAL 1500 kata di dalam field "content" — ini BATAS BAWAH,
   bukan target. Artikel kurang dari 1500 kata dianggap gagal. Tulis
   selengkap mungkin selama masih relevan dengan materi; target realistis
   1800-2200 kata.

3. STRUKTUR (semua angka di bawah adalah MINIMAL, boleh lebih panjang):
   - Paragraf pembuka (intro) minimal 180 kata. Keyword utama HARUS muncul
     di dalam 100 kata pertama.
   - MINIMAL 6 bagian utama (bukan 4, bukan 5 — enam atau lebih), masing-
     masing diawali heading H2, masing-masing MINIMAL 280 kata. Kalau sebuah
     bagian terasa mau selesai di bawah 280 kata, perdalam dengan elaborasi,
     contoh konkret, atau implikasi praktis dari materi referensi — jangan
     pindah ke bagian berikutnya sebelum minimal tercapai.
   - STRUKTUR WAJIB BERVARIASI, bukan cuma H2 + paragraf terus-menerus —
     ini penting untuk scannability dan peluang muncul di featured snippet:
     * WAJIB pakai H3 pada bagian H2 mana pun yang membahas ≥2 sub-topik
       yang jelas terpisah (misal beberapa jenis/kategori/tahapan/skenario).
       Kalau sebuah bagian H2 memang cuma satu sub-topik, H2 tanpa H3 tetap
       boleh — jangan dipaksakan.
     * WAJIB pakai <ul> atau <ol> di MINIMAL 2 bagian H2 yang isinya hal
       yang bisa dienumerasi (fitur, manfaat, langkah, komponen, checklist,
       kriteria). Kalau seluruh isi artikel murni naratif/analitis tanpa ada
       poin yang bisa dienumerasi, boleh full paragraf — jangan paksakan
       bullet pada konten yang natural-nya naratif.
   - Paragraf penutup (kesimpulan) minimal 180 kata. Sertakan CTA soft yang
     mengarahkan pembaca ke solusi brand (bukan ajakan menghubungi).

4. KEYWORD:
   - Keyword utama HARUS muncul di: judul (title), meta_description, paragraf
     pembuka (100 kata pertama), minimal 1 heading H2, dan paragraf penutup.
   - Frekuensi keyword utama di seluruh artikel: 5-8 kali (JANGAN keyword
     stuffing — jaga kepadatan wajar).
   - Setiap keyword tambahan HARUS muncul minimal 2 kali, tersebar natural
     di berbagai bagian.

5. HTML DI FIELD "content" HANYA BOLEH PAKAI TAG:
   <h2>, <h3>, <p>, <ul>, <ol>, <li>, <strong>, <em>, <a href="...">.
   DILARANG: <h1> (sudah dipakai judul WordPress), <div>, <span>, <script>,
   <style>, atribut style="" inline, atribut class="".

6. META FIELDS:
   - meta_description: 150-160 karakter, mengandung keyword utama, ditulis
     supaya menarik di-klik di SERP.
   - slug: URL-friendly, huruf kecil, kata dipisah tanda hubung, maks 60
     karakter, tidak boleh ada karakter selain [a-z0-9-].
   - excerpt: 2-3 kalimat ringkasan untuk halaman listing blog.
   - tags: 4-7 tag relevan, huruf kecil, tanpa tanda #. Tag boleh derived
     dari kategori/produk yang muncul di materi.

7. LINK INTERNAL & EKSTERNAL (WAJIB, kecuali kandidatnya kosong):
   - Sisipkan TEPAT 1 link internal (inbound) di dalam field "content",
     mengarah ke SALAH SATU URL di "Kandidat Link Internal" di atas — pilih
     yang paling nyambung secara konteks dengan isi artikel ini, jangan asal
     pilih yang pertama. Kalau daftar kandidat kosong / tertulis "(tidak ada
     kandidat)", lewati poin ini — JANGAN mengarang URL internal sendiri.
   - Sisipkan TEPAT 1 link eksternal (outbound) di dalam field "content",
     mengarah ke SALAH SATU URL di "Kandidat Link Eksternal" di atas — pilih
     yang paling relevan. Kalau daftar kosong, lewati poin ini — JANGAN
     mengarang URL eksternal sendiri.
   - DILARANG KERAS menggunakan URL apa pun di luar dua daftar kandidat di
     atas untuk atribut href.
   - Format: `<a href="URL_PERSIS_DARI_KANDIDAT">anchor text deskriptif</a>`
     — anchor text natural sesuai konteks kalimat, BUKAN "klik di sini" atau
     "baca selengkapnya".
   - Tempatkan kedua link di paragraf isi (bagian H2 mana pun selain
     pembuka/penutup), pada kalimat yang BERBEDA satu sama lain.

8. CTA (call-to-action) BOX — teks saja, JANGAN ditulis ke dalam field
   "content". Box-nya sendiri dirender programmatic di luar LLM, tugas Anda
   hanya menyediakan dua field teks pendek berikut. WAJIB spesifik terhadap
   topik/angle artikel INI ("{title}") — sebut kapabilitas, masalah, atau
   manfaat konkret yang memang dibahas di artikel ini, JANGAN kalimat umum
   yang bisa dipakai untuk artikel topik apa pun.
   - "cta_headline": kalimat ajakan singkat, MAKS 10 kata, merujuk isi
     spesifik artikel ini, brand sebagai SOLUSI (bukan pihak yang dihubungi)
     — ikuti aturan framing di poin 5 BLOG_SYSTEM_INSTRUCTION. Pola yang
     boleh dipakai: "[Manfaat/hasil terkait topik artikel] Sekarang/Hari Ini"
     — TAPI kata-kata di dalam kurung harus diganti sesuai topik artikel ini,
     JANGAN salin persis pola contoh di atas kata demi kata. DILARANG:
     "Hubungi {brand_name} Sekarang".
   - "cta_button_text": teks tombol actionable, MAKS 5 kata, kata kerja yang
     sesuai dengan jenis aksi paling relevan untuk topik artikel ini (mis.
     konsultasi, demo, unduh panduan, cek solusi — pilih salah satu yang
     paling pas, JANGAN selalu pilih yang sama di setiap artikel). "kami"
     boleh dipakai untuk merujuk pihak pemilik website, bukan nama brand.

Output JSON format wajib (pastikan valid JSON, escape " menjadi \\" di dalam string):
{{
  "title": "Judul artikel final (boleh sedikit berbeda dari brief agar lebih SEO)",
  "slug": "url-slug-artikel-yang-friendly",
  "meta_description": "Meta description 150-160 karakter yang mengandung keyword utama",
  "excerpt": "Ringkasan 2-3 kalimat untuk ditampilkan di listing blog",
  "content": "<p>Paragraf pembuka mengandung keyword utama...</p><h2>Bagian 1</h2><p>...</p><h2>Bagian 2</h2><p>...</p><h2>Kesimpulan</h2><p>...</p>",
  "tags": ["tag1", "tag2", "tag3", "tag4", "tag5"],
  "cta_headline": "Kalimat ajakan singkat, maks 10 kata, kontekstual dengan topik artikel ini",
  "cta_button_text": "Teks tombol actionable, maks 5 kata"
}}
"""


# Dipakai sebagai fallback terprogram kalau ARTICLE_GENERATION_PROMPT tetap
# menghasilkan artikel di bawah minimum kata (lihat generate_article() di
# blog_generator.py). Tidak mengulang seluruh aturan struktur/keyword di atas
# — cukup rujukan singkat, karena BLOG_SYSTEM_INSTRUCTION sudah terkirim
# ulang sebagai system message di call ini.
ARTICLE_EXPAND_PROMPT = """
Artikel blog brand {brand_name} di bawah ini baru {current_words} kata,
padahal minimum yang dibutuhkan {min_words} kata (idealnya sekitar
{ideal_words} kata). Tulis ulang secara UTUH agar field "content" mencapai
minimal {min_words} kata.

Artikel saat ini (JSON):
{current_article_json}

Data Referensi Brand (dasar untuk menambah kedalaman — DILARANG mengarang
fakta/produk/angka baru di luar ini):
{raw_data}

CARA MEMPERPANJANG:
- Tambahkan 1-2 bagian H2 baru yang relevan dan didukung materi referensi,
  DAN/ATAU perdalam bagian yang sudah ada dengan elaborasi, contoh konkret,
  atau implikasi praktis yang belum dibahas.
- JANGAN mengulang kalimat atau paragraf yang sudah ada persis sama — setiap
  penambahan harus substansi baru.
- Pertahankan judul, keyword utama ({main_keyword}), framing brand sebagai
  solusi (bukan penjual aktif), DAN pertahankan link internal/eksternal
  (tag <a href="...">) yang sudah ada di artikel saat ini — jangan dihapus,
  jangan diganti URL-nya.
- Bagian yang ditambah/diperluas WAJIB ikut aturan struktur yang sama seperti
  versi awal: pakai H3 kalau bagian itu membahas ≥2 sub-topik terpisah, dan
  pakai <ul>/<ol> kalau isinya hal yang bisa dienumerasi (fitur, manfaat,
  langkah, komponen) — jangan cuma tambah paragraf naratif polos kalau
  artikel saat ini belum punya H3/list sama sekali. Tag HTML tetap sama
  seperti sebelumnya (<h2> <h3> <p> <ul> <ol> <li> <strong> <em> <a>).

Output JSON dengan schema PERSIS SAMA seperti artikel di atas (title, slug,
meta_description, excerpt, content, tags) — tanpa markdown fences, valid
JSON murni, escape " menjadi \\" di dalam string.
"""


# Dipakai sebagai fallback terprogram kalau ARTICLE_GENERATION_PROMPT tidak
# menyisipkan link internal dan/atau eksternal yang wajib ada (lihat
# link fix-up pass di generate_article(), blog_generator.py). Hanya menyuruh
# SISIPKAN, bukan tulis ulang isi artikel — supaya konten yang sudah bagus
# tidak berubah selain penambahan link.
LINK_FIX_PROMPT = """
Artikel blog brand {brand_name} di bawah ini BELUM memenuhi syarat link
wajib: {missing_description}

Artikel saat ini (JSON):
{current_article_json}

Kandidat Link Internal (milik brand sendiri):
{internal_link_candidates}

Kandidat Link Eksternal (sumber referensi terpercaya):
{external_links}

TUGAS:
- Sisipkan HANYA link yang masih kurang (sesuai keterangan di atas) ke dalam
  field "content", masing-masing memakai anchor text natural dan deskriptif:
  `<a href="URL_PERSIS_DARI_KANDIDAT">anchor text</a>`.
- JANGAN mengarang URL di luar kandidat yang diberikan. Kalau kandidat untuk
  jenis link yang kurang itu kosong, JANGAN sisipkan apa pun untuk jenis itu.
- JANGAN mengubah, menghapus, atau menulis ulang kalimat/paragraf lain di
  luar penyisipan link ini. JANGAN mengubah title, slug, meta_description,
  excerpt, atau tags.
- Sisipkan di paragraf isi yang paling relevan (bukan pembuka/penutup, dan
  bukan di kalimat yang sama dengan link lain yang sudah ada).

Output JSON dengan schema PERSIS SAMA seperti artikel di atas (title, slug,
meta_description, excerpt, content, tags) — tanpa markdown fences, valid
JSON murni, escape " menjadi \\" di dalam string.
"""
