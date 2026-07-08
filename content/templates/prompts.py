SYSTEM_INSTRUCTION = """
Anda adalah seorang Technical Copywriter profesional di PT. iLogo Infralogy Indonesia.
Tugas Anda adalah membuat konten website yang profesional, natural, tidak kaku (tidak terasa seperti terjemahan mesin AI), dan SEO-friendly dalam Bahasa Indonesia.

ATURAN PENTING:
1. Pertahankan istilah teknis Bahasa Inggris jika istilah tersebut lebih umum digunakan di industri IT Infrastructure dan Cybersecurity (contoh: "endpoint security", "cloud backup", "ransomware prevention", "firewall").
2. Jangan lakukan copy-paste mentah-mentah dari data teks referensi. Olah kembali secara kreatif.
3. Output HARUS selalu berupa valid JSON string dengan format yang diminta, tanpa markdown triple backticks (```json) di awal maupun akhir.
"""

PAGE_PROMPTS = {
    "home": """
Berdasarkan data referensi brand berikut, buatlah konten untuk halaman 'Beranda' (Home Page).
Data Referensi:
{raw_data}

Output JSON format wajib seperti ini:
{{
  "title": "Judul Utama Halaman Beranda",
  "hero_headline": "Headline banner utama yang menarik",
  "hero_subheadline": "Sub-headline penjelasan singkat solusi brand",
  "about_summary": "Ringkasan profil brand dan mengapa memilih solusi mereka",
  "seo_keywords": ["keyword1", "keyword2"]
}}
""",
    "produk": """
Berdasarkan data referensi brand berikut, identifikasi dan buatlah konten untuk SETIAP PRODUK UTAMA mereka secara terpisah.
Fokus pada produk-produk inti (BUKAN fitur atau modul kecil). Maksimal 5 produk utama.

Data Referensi:
{raw_data}

Output JSON format wajib seperti ini (array products_list berisi setiap produk sebagai objek terpisah):
{{
  "intro_page_title": "Produk & Solusi Kami",
  "intro_page_description": "Deskripsi pengantar singkat portofolio produk brand ini dalam 1-2 kalimat",
  "products_list": [
     {{
       "name": "Nama Produk 1",
       "slug": "nama-produk-1",
       "tagline": "Kalimat tagline singkat yang powerful untuk produk ini",
       "description": "Deskripsi lengkap fitur dan keunggulan produk 1 dalam Bahasa Indonesia (2-3 paragraf)",
       "key_features": ["Fitur utama 1", "Fitur utama 2", "Fitur utama 3"],
       "target_user": "Deskripsi singkat siapa pengguna ideal produk ini",
       "seo_keywords": ["keyword1", "keyword2"]
     }},
     {{
       "name": "Nama Produk 2",
       "slug": "nama-produk-2",
       "tagline": "Kalimat tagline singkat yang powerful untuk produk ini",
       "description": "Deskripsi lengkap fitur dan keunggulan produk 2 dalam Bahasa Indonesia (2-3 paragraf)",
       "key_features": ["Fitur utama 1", "Fitur utama 2", "Fitur utama 3"],
       "target_user": "Deskripsi singkat siapa pengguna ideal produk ini",
       "seo_keywords": ["keyword1", "keyword2"]
     }}
  ],
  "seo_keywords": ["keyword_umum1", "keyword_umum2"]
}}
Catatan: Jumlah item dalam products_list harus sesuai jumlah produk utama yang ditemukan, MAKSIMAL 5.
""",
    "solusi": """
Berdasarkan data referensi brand berikut, buatlah konten untuk halaman 'Solusi' (Solutions Page / Use Cases).
Data Referensi:
{raw_data}

Output JSON format wajib seperti ini:
{{
  "title": "Solusi Industri & Bisnis",
  "intro": "Bagaimana kami membantu mengatasi tantangan bisnis",
  "solutions_list": [
     {{
       "target": "Target Solusi (misal: Sektor Perbankan / Keamanan Data)",
       "benefit": "Penjelasan detail implementasi solusi"
     }}
  ],
  "seo_keywords": ["keyword1", "keyword2"]
}}
""",
    "contact": """
Buatlah konten halaman 'Hubungi Kami' untuk brand ini sebagai partner iLogo.
Data Referensi Brand: Nama Brand: {brand_name}

Output JSON format wajib seperti ini:
{{
  "title": "Hubungi Tim Ahli Kami",
  "headline": "Konsultasikan Kebutuhan Infrastruktur IT Anda Sekarang",
  "cta_text": "Isi formulir atau hubungi iLogo Infralogy Indonesia sebagai partner resmi di Indonesia untuk demo gratis."
}}
"""
}

# Prompt khusus untuk menghasilkan SATU produk dari URL produk tersendiri
PRODUCT_INDIVIDUAL_PROMPT = """
Berdasarkan data referensi halaman produk berikut, buatlah konten untuk SATU produk.
Data Referensi:
{raw_data}

Output JSON format wajib seperti ini (hanya satu produk, tanpa list):
{{
  "name": "Nama Produk",
  "slug": "nama-produk-slug",
  "tagline": "Kalimat tagline singkat yang powerful untuk produk ini",
  "description": "Deskripsi lengkap fitur dan keunggulan produk dalam Bahasa Indonesia (2-3 paragraf)",
  "key_features": ["Fitur utama 1", "Fitur utama 2", "Fitur utama 3"],
  "target_user": "Deskripsi singkat siapa pengguna ideal produk ini",
  "seo_keywords": ["keyword1", "keyword2"]
}}
"""