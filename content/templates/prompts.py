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
Berdasarkan data referensi brand berikut, buatlah konten untuk halaman 'Produk' (Products Page). 
Identifikasi produk-produk utama mereka.
Data Referensi:
{raw_data}

Output JSON format wajib seperti ini:
{{
  "title": "Solusi & Produk Kami",
  "intro": "Deskripsi pengantar portofolio produk",
  "products_list": [
     {{
       "name": "Nama Produk 1",
       "description": "Deskripsi lengkap fitur dan keunggulan produk 1 dalam Bahasa Indonesia"
     }},
     {{
       "name": "Nama Produk 2",
       "description": "Deskripsi lengkap fitur dan keunggulan produk 2 dalam Bahasa Indonesia"
     }}
  ],
  "seo_keywords": ["keyword1", "keyword2"]
}}
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
""",
    "blog": """
Berdasarkan data referensi brand berikut, buatlah konten draft 1 artikel 'Blog' edukatif yang relevan untuk pasar Indonesia.
Data Referensi:
{raw_data}

Output JSON format wajib seperti ini:
{{
  "title": "Judul Artikel Blog Edukatif & Menarik",
  "excerpt": "Rangkuman singkat artikel",
  "content": "Isi lengkap artikel minimal 3 paragraf panjang, mendalam, dan kaya edukasi."
}}
"""
}