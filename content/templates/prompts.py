SYSTEM_INSTRUCTION = """
Anda adalah seorang Technical Copywriter profesional di PT. iLogo Infralogy Indonesia.
Tugas Anda adalah membuat konten website yang profesional, natural, tidak kaku (tidak terasa seperti terjemahan mesin AI), dan SEO-friendly dalam Bahasa Indonesia.

ATURAN PENTING:
1. Pertahankan istilah teknis Bahasa Inggris jika istilah tersebut lebih umum digunakan di industri IT Infrastructure dan Cybersecurity (contoh: "endpoint security", "cloud backup", "ransomware prevention", "firewall").
2. Jangan lakukan copy-paste mentah-mentah dari data teks referensi. Olah kembali secara kreatif.
3. Output HARUS selalu berupa valid JSON string dengan format yang diminta, tanpa markdown triple backticks (```json) di awal maupun akhir.
4. Untuk field berupa teks panjang (seperti description, about_summary, why_choose), tulis dengan substansial — minimal 2 paragraf penuh, bukan 1-2 kalimat saja.
"""

PAGE_PROMPTS = {
    "home": """
Berdasarkan data referensi brand berikut, buatlah konten untuk halaman 'Beranda' (Home Page).
Data Referensi:
{raw_data}

Output JSON format wajib seperti ini:
{{
  "title": "Judul Utama Halaman Beranda",
  "hero_headline": "Headline banner utama yang kuat dan menarik perhatian (maks 10 kata)",
  "hero_subheadline": "Sub-headline yang menjelaskan proposisi nilai utama brand secara ringkas dan persuasif (1-2 kalimat)",
  "cta_button_text": "Teks tombol ajakan bertindak yang actionable (contoh: Konsultasi Gratis Sekarang, Pelajari Solusi Kami)",
  "about_summary": "Paragraf profil brand: siapa mereka, masalah apa yang diselesaikan, dan mengapa mereka dipercaya. Tulis dalam 2 sampai 3 paragraf penuh dan natural, bukan poin-poin. WAJIB: sertakan frasa '{brand_name} Indonesia' secara natural minimal satu kali di dalam teks ini (contoh: '{brand_name} Indonesia telah dipercaya oleh...' atau '...solusi yang ditawarkan {brand_name} Indonesia mencakup...').",
  "value_propositions": [
    {{
      "icon_label": "Kata kunci ikon (contoh: Security, Speed, Support)",
      "title": "Judul keunggulan pertama brand (3-5 kata)",
      "description": "Penjelasan konkret keunggulan pertama dalam 1-2 kalimat penuh"
    }},
    {{
      "icon_label": "Kata kunci ikon",
      "title": "Judul keunggulan kedua brand (3-5 kata)",
      "description": "Penjelasan konkret keunggulan kedua dalam 1-2 kalimat penuh"
    }},
    {{
      "icon_label": "Kata kunci ikon",
      "title": "Judul keunggulan ketiga brand (3-5 kata)",
      "description": "Penjelasan konkret keunggulan ketiga dalam 1-2 kalimat penuh"
    }}
  ],
  "closing_statement": "Kalimat penutup yang membangun kepercayaan dan mendorong calon pelanggan untuk menghubungi tim iLogo (1-2 kalimat, persuasif dan hangat)",
  "seo_keywords": ["Wajib sertakan kombinasi nama brand diikuti kata Indonesia, contoh: '{brand_name} Indonesia'", "keyword2", "keyword3", "keyword4"]
}}
""",

    "produk": """
Berdasarkan data referensi brand berikut, identifikasi dan buatlah konten untuk SETIAP PRODUK UTAMA mereka secara terpisah.
Fokus pada produk-produk inti (BUKAN fitur atau modul kecil). Maksimal {max_products} produk utama.

Data Referensi:
{raw_data}

Output JSON format wajib seperti ini (array products_list berisi setiap produk sebagai objek terpisah):
{{
  "intro_page_title": "Produk & Solusi Kami",
  "intro_page_description": "Deskripsi pengantar portofolio produk brand ini dalam 2-3 kalimat yang meyakinkan",
  "products_list": [
    {{
      "name": "Nama Produk 1",
      "slug": "nama-produk-1",
      "tagline": "Kalimat tagline singkat yang kuat dan mudah diingat untuk produk ini (maks 10 kata)",
      "description": "Deskripsi lengkap produk dalam Bahasa Indonesia. Tulis dalam 2 sampai 3 paragraf penuh: paragraf pertama menjelaskan apa produk ini dan masalah yang diselesaikan, paragraf kedua menjelaskan cara kerja atau pendekatan utamanya, paragraf ketiga menjelaskan nilai bisnis atau dampak nyata bagi pengguna.",
      "key_features": [
        "Fitur utama 1 beserta penjelasan singkat manfaatnya",
        "Fitur utama 2 beserta penjelasan singkat manfaatnya",
        "Fitur utama 3 beserta penjelasan singkat manfaatnya",
        "Fitur utama 4 beserta penjelasan singkat manfaatnya"
      ],
      "use_cases": [
        "Contoh skenario penggunaan nyata atau industri yang relevan 1",
        "Contoh skenario penggunaan nyata atau industri yang relevan 2"
      ],
      "why_choose": "Paragraf singkat yang menjelaskan diferensiasi produk ini dibanding solusi lain di pasar. Fokus pada keunggulan kompetitif yang nyata dan relevan bagi pengambil keputusan IT.",
      "target_user": "Deskripsi spesifik siapa pengguna ideal produk ini: jabatan, ukuran perusahaan, atau industri",
      "seo_keywords": ["keyword1", "keyword2", "keyword3"]
    }},
    {{
      "name": "Nama Produk 2",
      "slug": "nama-produk-2",
      "tagline": "Kalimat tagline singkat yang kuat untuk produk ini",
      "description": "Deskripsi lengkap produk 2 dalam 2 sampai 3 paragraf penuh seperti format di atas.",
      "key_features": [
        "Fitur utama 1 dengan penjelasan manfaat",
        "Fitur utama 2 dengan penjelasan manfaat",
        "Fitur utama 3 dengan penjelasan manfaat",
        "Fitur utama 4 dengan penjelasan manfaat"
      ],
      "use_cases": [
        "Skenario penggunaan nyata 1",
        "Skenario penggunaan nyata 2"
      ],
      "why_choose": "Paragraf diferensiasi produk 2 dibanding solusi lain.",
      "target_user": "Deskripsi spesifik pengguna ideal produk 2",
      "seo_keywords": ["keyword1", "keyword2", "keyword3"]
    }}
  ],
  "seo_keywords": ["keyword_umum1", "keyword_umum2", "keyword_umum3"]
}}
Catatan: Jumlah item dalam products_list harus sesuai jumlah produk utama yang ditemukan, MAKSIMAL {max_products}. Seluruh field wajib diisi — jangan ada field yang dikosongkan atau diisi placeholder.
""",

    "solusi": """
Berdasarkan data referensi brand berikut, buatlah konten untuk halaman 'Solusi' (Solutions Page / Use Cases).
Data Referensi:
{raw_data}

Output JSON format wajib seperti ini:
{{
  "title": "Solusi Industri & Bisnis",
  "intro": "Paragraf pengantar yang menjelaskan bagaimana brand ini membantu mengatasi tantangan bisnis nyata (2-3 kalimat)",
  "solutions_list": [
    {{
      "target": "Target Solusi (contoh: Sektor Perbankan & Keuangan, Proteksi Data Kritis)",
      "benefit": "Penjelasan konkret implementasi dan manfaat solusi untuk target ini dalam 2-3 kalimat"
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
Berdasarkan data referensi halaman produk berikut, buatlah konten untuk SATU produk secara lengkap dan detail.
Data Referensi:
{raw_data}

Output JSON format wajib seperti ini (hanya satu produk, tanpa list):
{{
  "name": "Nama Produk",
  "slug": "nama-produk-slug",
  "tagline": "Kalimat tagline singkat yang kuat dan mudah diingat (maks 10 kata)",
  "description": "Deskripsi lengkap produk dalam Bahasa Indonesia. Tulis dalam 2 sampai 3 paragraf penuh: paragraf pertama menjelaskan apa produk ini dan masalah yang diselesaikan, paragraf kedua menjelaskan cara kerja atau pendekatan utamanya, paragraf ketiga menjelaskan nilai bisnis atau dampak nyata bagi pengguna.",
  "key_features": [
    "Fitur utama 1 beserta penjelasan singkat manfaatnya",
    "Fitur utama 2 beserta penjelasan singkat manfaatnya",
    "Fitur utama 3 beserta penjelasan singkat manfaatnya",
    "Fitur utama 4 beserta penjelasan singkat manfaatnya"
  ],
  "use_cases": [
    "Contoh skenario penggunaan nyata atau industri yang relevan 1",
    "Contoh skenario penggunaan nyata atau industri yang relevan 2"
  ],
  "why_choose": "Paragraf yang menjelaskan diferensiasi produk ini dibanding solusi lain di pasar. Fokus pada keunggulan kompetitif yang nyata dan relevan bagi pengambil keputusan IT.",
  "target_user": "Deskripsi spesifik siapa pengguna ideal produk ini: jabatan, ukuran perusahaan, atau industri",
  "seo_keywords": ["keyword1", "keyword2", "keyword3"]
}}
"""