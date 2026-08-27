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

2. PANJANG: Minimum 1500 kata di dalam field "content". Artikel kurang dari
   1500 kata dianggap gagal. Target ideal 1600-1900 kata.

3. STRUKTUR:
   - Paragraf pembuka (intro) 150-200 kata. Keyword utama HARUS muncul di
     dalam 100 kata pertama.
   - 4-6 bagian utama, masing-masing diawali heading H2. Setiap bagian
     200-350 kata. Boleh pakai H3 untuk sub-bagian bila diperlukan.
   - Boleh gunakan <ul> atau <ol> untuk poin daftar bila memang relevan
     (JANGAN jadikan seluruh artikel bullet point).
   - Paragraf penutup (kesimpulan) 150-200 kata. Sertakan CTA soft yang
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

Output JSON format wajib (pastikan valid JSON, escape " menjadi \\" di dalam string):
{{
  "title": "Judul artikel final (boleh sedikit berbeda dari brief agar lebih SEO)",
  "slug": "url-slug-artikel-yang-friendly",
  "meta_description": "Meta description 150-160 karakter yang mengandung keyword utama",
  "excerpt": "Ringkasan 2-3 kalimat untuk ditampilkan di listing blog",
  "content": "<p>Paragraf pembuka mengandung keyword utama...</p><h2>Bagian 1</h2><p>...</p><h2>Bagian 2</h2><p>...</p><h2>Kesimpulan</h2><p>...</p>",
  "tags": ["tag1", "tag2", "tag3", "tag4", "tag5"]
}}
"""
