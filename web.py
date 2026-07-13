import os
import sys
import json
import asyncio
import tempfile
import shutil
from fastapi import FastAPI, Request, Form, BackgroundTasks, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from main import run_pipeline
from visual.color_extractor import ColorExtractor

app = FastAPI(title="iAAWG Web UI")

# Mount folder output agar pratinjau lokal dan aset gambar bisa diakses langsung lewat browser
if not os.path.exists("output"):
    os.makedirs("output", exist_ok=True)
app.mount("/output", StaticFiles(directory="output"), name="output")

process_logs = []
is_running = False
current_progress = 0
current_brand = ""
# Variabel global untuk token
total_prompt_tokens = 0
total_completion_tokens = 0

# Simpan referensi task asyncio yang sedang berjalan secara global
current_task = None

MAX_PRODUCTS = 5  # Harus sama dengan konstanta di main.py

# Warna default iLogo (fallback jika tidak ada logo)
DEFAULT_PRIMARY_COLOR = "#1E7E34"

def generate_local_preview_html(brand: str, primary_color: str = DEFAULT_PRIMARY_COLOR):
    """
    Membaca data JSON dari output lokal dan menyusun sebuah landing page
    simulasi terintegrasi berbasis Tailwind CSS yang sangat profesional.
    Dilengkapi Dynamic Theming berdasarkan primary_color (HEX) dari logo.
    """
    brand_lower = brand.lower()
    content_dir = os.path.join("output", brand_lower, "content")
    preview_file = os.path.join(content_dir, "preview_lokal.html")
    
    static_pages = ["home", "produk", "solusi", "contact"]
    data = {}
    
    # Load semua file JSON halaman statis
    for p in static_pages:
        file_path = os.path.join(content_dir, f"{p}.json")
        if os.path.exists(file_path):
            with open(file_path, "r", encoding="utf-8") as f:
                try:
                    data[p] = json.load(f)
                except:
                    data[p] = {}
        else:
            data[p] = {}

    products_list = data.get("produk", {}).get("products_list", [])[:MAX_PRODUCTS]

    # Setup path gambar lokal
    def get_asset_url(p_type, a_type):
        return f"/output/{brand_lower}/visual/{brand_lower}_{p_type}_{a_type}.jpg"

    def get_product_asset_url(prod_slug, a_type):
        return f"/output/{brand_lower}/visual/{brand_lower}_{prod_slug}_{a_type}.jpg"

    # =========================================================================
    # DYNAMIC BRANDING LOGIC – menggunakan hue dari primary_color
    # =========================================================================
    # Konversi HEX ke HSL untuk mendapatkan hue
    def hex_to_hue(hex_color):
        hex_color = hex_color.lstrip('#')
        if len(hex_color) == 3:
            hex_color = ''.join([c*2 for c in hex_color])
        r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
        # Konversi RGB ke HSL
        r_norm = r / 255.0
        g_norm = g / 255.0
        b_norm = b / 255.0
        max_val = max(r_norm, g_norm, b_norm)
        min_val = min(r_norm, g_norm, b_norm)
        diff = max_val - min_val
        if diff == 0:
            hue = 0
        elif max_val == r_norm:
            hue = (60 * ((g_norm - b_norm) / diff) + 360) % 360
        elif max_val == g_norm:
            hue = (60 * ((b_norm - r_norm) / diff) + 120) % 360
        else:
            hue = (60 * ((r_norm - g_norm) / diff) + 240) % 360
        return int(round(hue))

    hue_primary = hex_to_hue(primary_color)

    # =========================================================================
    # KOMPONEN RENDER: Value Propositions (Home)
    # =========================================================================
    vps = data.get('home', {}).get('value_propositions', [])
    vp_html = ""
    for idx, vp in enumerate(vps):
        vp_html += f"""
        <div class="bg-white p-8 rounded-2xl shadow-sm border border-slate-100 hover:shadow-xl hover:-translate-y-1 transition-all duration-300">
            <div class="w-14 h-14 bg-brand-50 rounded-2xl flex items-center justify-center text-brand-600 mb-6 shadow-inner">
                <i data-lucide="check-circle-2" class="w-7 h-7"></i>
            </div>
            <h3 class="text-xl font-bold text-slate-900 mb-3">{vp.get('title', f'Keunggulan {idx+1}')}</h3>
            <p class="text-slate-600 leading-relaxed text-sm">{vp.get('description', '')}</p>
        </div>"""
        
    if not vp_html:
        vp_html = "<p class='text-slate-400'>Keunggulan belum dimuat.</p>"

    # =========================================================================
    # KOMPONEN RENDER: Produk (Sidebar & Content)
    # =========================================================================
    produk_sidebar = ""
    produk_content = ""
    for i, prod in enumerate(products_list):
        prod_name = prod.get("name", f"Produk {i+1}")
        prod_slug = prod.get("slug", f"produk-{i+1}")
        is_first = "bg-brand-50 text-brand-700 border-r-4 border-brand-600 font-bold" if i == 0 else "text-slate-500 hover:bg-slate-50 hover:text-slate-900 border-r-4 border-transparent font-medium"
        
        # Sidebar Menu
        produk_sidebar += f"""
        <button onclick="switchProdukTab('{prod_slug}')" id="produk-btn-{prod_slug}" 
            class="produk-tab-btn w-full text-left px-5 py-4 text-sm transition-all {is_first}">
            {prod_name}
        </button>"""

        # Features
        key_features_html = "".join([f"<li class='flex items-start gap-3'><i data-lucide='badge-check' class='w-5 h-5 text-brand-500 flex-shrink-0 mt-0.5'></i><span class='text-slate-600 text-sm'>{feat}</span></li>" for feat in prod.get("key_features", [])])
        
        # Use Cases
        use_cases_html = "".join([f"<li class='flex items-start gap-3'><i data-lucide='building-2' class='w-5 h-5 text-slate-400 flex-shrink-0 mt-0.5'></i><span class='text-slate-600 text-sm'>{uc}</span></li>" for uc in prod.get("use_cases", [])])

        display_style = "block" if i == 0 else "none"
        produk_content += f"""
        <div id="produk-tab-{prod_slug}" class="produk-tab-content animate-fade-in" style="display:{display_style};">
            <div class="mb-8">
                <span class="text-xs font-bold tracking-widest text-brand-600 uppercase mb-2 block">PRODUK UNGGULAN</span>
                <h2 class="text-3xl md:text-4xl font-extrabold text-slate-900 mb-4">{prod_name}</h2>
                <p class="text-lg text-slate-500">{prod.get('tagline', '')}</p>
            </div>
            
            <div class="relative h-64 md:h-80 w-full rounded-2xl overflow-hidden mb-10 shadow-lg">
                <img src="{get_product_asset_url(prod_slug, 'banner')}" class="w-full h-full object-cover" onerror="this.src='https://images.unsplash.com/photo-1518770660439-4636190af475?w=1200'">
                <div class="absolute inset-0 bg-gradient-to-t from-slate-900/60 to-transparent"></div>
            </div>

            <div class="grid grid-cols-1 md:grid-cols-2 gap-10 mb-10">
                <div class="prose prose-slate text-slate-600 text-sm leading-loose">
                    {''.join(f'<p>{para.strip()}</p>' for para in prod.get('description','').split(chr(10)) if para.strip())}
                </div>
                <div class="space-y-8">
                    <div class="bg-white border border-slate-100 rounded-xl p-6 shadow-sm">
                        <h4 class="text-slate-900 font-bold mb-4 flex items-center gap-2"><i data-lucide="layers"></i> Fitur Utama</h4>
                        <ul class="space-y-3">{key_features_html}</ul>
                    </div>
                    {f'''<div class="bg-slate-50 rounded-xl p-6 border border-slate-100">
                        <h4 class="text-slate-900 font-bold mb-4 flex items-center gap-2"><i data-lucide="target"></i> Use Cases</h4>
                        <ul class="space-y-3">{use_cases_html}</ul>
                    </div>''' if use_cases_html else ''}
                </div>
            </div>
            
            <div class="bg-brand-900 rounded-2xl p-8 flex flex-col md:flex-row items-center justify-between gap-6 shadow-xl relative overflow-hidden">
                <div class="absolute top-0 right-0 opacity-10 transform translate-x-1/4 -translate-y-1/4">
                    <i data-lucide="shield-check" class="w-64 h-64 text-white"></i>
                </div>
                <div class="relative z-10 md:w-2/3">
                    <h4 class="text-white text-xl font-bold mb-2">Mengapa Memilih {prod_name}?</h4>
                    <p class="text-brand-100 text-sm leading-relaxed">{prod.get('why_choose', 'Solusi terbaik untuk bisnis Anda.')}</p>
                </div>
                <div class="relative z-10">
                    <button onclick="switchTab('contact')" class="bg-brand-500 hover:bg-brand-400 text-white font-bold py-3 px-6 rounded-lg transition-colors whitespace-nowrap">Jadwalkan Demo</button>
                </div>
            </div>
        </div>"""

    # =========================================================================
    # KOMPONEN RENDER: Solusi (Bento Grid)
    # =========================================================================
    solutions = data.get('solusi', {}).get('solutions_list', [])
    solusi_html = ""
    for s_item in solutions:
        solusi_html += f"""
        <div class="group bg-white border border-slate-200 rounded-2xl p-8 hover:border-brand-500 hover:shadow-2xl transition-all duration-300">
            <div class="w-12 h-12 bg-slate-100 group-hover:bg-brand-600 rounded-xl flex items-center justify-center text-slate-500 group-hover:text-white transition-colors mb-6">
                <i data-lucide="briefcase" class="w-6 h-6"></i>
            </div>
            <h4 class="text-lg font-bold text-slate-900 mb-3 group-hover:text-brand-600 transition-colors">{s_item.get('target', '')}</h4>
            <p class="text-slate-600 text-sm leading-relaxed">{s_item.get('benefit', '')}</p>
        </div>"""

    # =========================================================================
    # HTML UTAMA
    # =========================================================================
    html_content = f"""<!DOCTYPE html>
<html lang="id" class="scroll-smooth">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{brand.upper()} - Official Website</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap" rel="stylesheet">
    <script src="https://unpkg.com/lucide@latest"></script>
    
    <style>
        :root {{
            /* Dynamic Branding Injected Here – berdasarkan hue dari logo */
            --brand-50: hsl({hue_primary}, 80%, 96%);
            --brand-100: hsl({hue_primary}, 80%, 90%);
            --brand-400: hsl({hue_primary}, 80%, 60%);
            --brand-500: hsl({hue_primary}, 80%, 50%);
            --brand-600: hsl({hue_primary}, 80%, 40%);
            --brand-700: hsl({hue_primary}, 80%, 30%);
            --brand-900: hsl({hue_primary}, 80%, 15%);
        }}
        body {{ font-family: 'Plus Jakarta Sans', sans-serif; }}
        .tab-content {{ display: none; opacity: 0; transition: opacity 0.4s ease; }}
        .tab-content.active {{ display: block; opacity: 1; }}
        
        @keyframes fadeIn {{
            from {{ opacity: 0; transform: translateY(10px); }}
            to {{ opacity: 1; transform: translateY(0); }}
        }}
        .animate-fade-in {{ animation: fadeIn 0.5s ease-out forwards; }}
    </style>
    
    <script>
        tailwind.config = {{
            theme: {{
                extend: {{
                    colors: {{
                        brand: {{
                            50: 'var(--brand-50)',
                            100: 'var(--brand-100)',
                            400: 'var(--brand-400)',
                            500: 'var(--brand-500)',
                            600: 'var(--brand-600)',
                            700: 'var(--brand-700)',
                            900: 'var(--brand-900)',
                        }}
                    }}
                }}
            }}
        }}
    </script>
</head>
<body class="bg-slate-50 text-slate-800 flex flex-col min-h-screen">

    <!-- Floating Badge Preview -->
    <div class="fixed bottom-6 right-6 z-50 bg-slate-900 text-white px-4 py-3 rounded-xl shadow-2xl flex items-center gap-3 border border-slate-700 backdrop-blur-md bg-opacity-90">
        <span class="relative flex h-3 w-3"><span class="animate-ping absolute inline-flex h-full w-full rounded-full bg-brand-400 opacity-75"></span><span class="relative inline-flex rounded-full h-3 w-3 bg-brand-500"></span></span>
        <div class="flex flex-col">
            <span class="text-xs font-bold uppercase tracking-wider">iAAWG Preview</span>
            <span class="text-[10px] text-slate-400">Offline Mockup Mode</span>
        </div>
    </div>

    <!-- Actual Website Navbar -->
    <nav class="bg-white/80 backdrop-blur-lg sticky top-0 z-40 border-b border-slate-200 transition-all shadow-sm">
        <div class="max-w-7xl mx-auto px-6 h-20 flex items-center justify-between">
            <div class="flex items-center gap-3 cursor-pointer" onclick="switchTab('home')">
                <div class="w-10 h-10 bg-brand-600 rounded-xl flex items-center justify-center text-white font-extrabold text-xl shadow-lg shadow-brand-500/30">
                    {brand[:2].upper()}
                </div>
                <span class="font-extrabold text-2xl tracking-tight text-slate-900">{brand.capitalize()}</span>
            </div>
            
            <div class="hidden md:flex items-center space-x-1">
                <button onclick="switchTab('home')" id="btn-home" class="tab-btn px-5 py-2.5 rounded-lg text-sm font-semibold bg-brand-50 text-brand-600 transition-all">Beranda</button>
                <button onclick="switchTab('produk')" id="btn-produk" class="tab-btn px-5 py-2.5 rounded-lg text-sm font-medium text-slate-600 hover:text-brand-600 hover:bg-slate-50 transition-all">Produk</button>
                <button onclick="switchTab('solusi')" id="btn-solusi" class="tab-btn px-5 py-2.5 rounded-lg text-sm font-medium text-slate-600 hover:text-brand-600 hover:bg-slate-50 transition-all">Solusi</button>
            </div>
            
            <div class="hidden md:block">
                <button onclick="switchTab('contact')" id="btn-contact" class="tab-btn bg-slate-900 hover:bg-slate-800 text-white px-6 py-2.5 rounded-lg text-sm font-bold shadow-md transition-all">Hubungi Kami</button>
            </div>
        </div>
    </nav>

    <main class="flex-grow w-full">
        
        <!-- ================= TAB BERANDA ================= -->
        <section id="tab-home" class="tab-content active">
            <!-- Hero Banner -->
            <div class="relative bg-slate-900 overflow-hidden">
                <div class="absolute inset-0">
                    <img src="{get_asset_url('home', 'banner')}" class="w-full h-full object-cover opacity-30 mix-blend-overlay" onerror="this.src='https://images.unsplash.com/photo-1451187580459-43490279c0fa?w=1200'">
                    <div class="absolute inset-0 bg-gradient-to-r from-slate-900 via-slate-900/90 to-transparent"></div>
                </div>
                <div class="relative max-w-7xl mx-auto px-6 py-32 md:py-40 flex flex-col md:w-2/3">
                    <div class="inline-flex items-center gap-2 bg-slate-950/80 border border-white/10 text-white backdrop-blur-sm px-4 py-1.5 rounded-full text-xs font-bold tracking-wide uppercase mb-6 w-max shadow-lg">
                        <i data-lucide="shield" class="w-4 h-4 text-brand-500"></i>
                        <span>Official Partner</span>
                    </div>
                    <h1 class="text-4xl md:text-6xl font-extrabold text-white tracking-tight leading-tight mb-6">
                        {data.get('home', {}).get('hero_headline', 'Infrastruktur Canggih untuk Bisnis Anda')}
                    </h1>
                    <p class="text-lg md:text-xl text-slate-300 font-medium mb-10 leading-relaxed max-w-2xl">
                        {data.get('home', {}).get('hero_subheadline', '')}
                    </p>
                    <div class="flex flex-wrap gap-4">
                        <button onclick="switchTab('contact')" class="bg-brand-600 hover:bg-brand-500 text-white font-bold px-8 py-4 rounded-xl transition-all shadow-lg shadow-brand-600/30 flex items-center gap-2">
                            {data.get('home', {}).get('cta_button_text', 'Konsultasi Sekarang')} <i data-lucide="arrow-right" class="w-5 h-5"></i>
                        </button>
                        <button onclick="switchTab('produk')" class="bg-white/10 hover:bg-white/20 text-white border border-white/20 font-bold px-8 py-4 rounded-xl transition-all backdrop-blur-sm">
                            Pelajari Solusi Kami
                        </button>
                    </div>
                </div>
            </div>
            
            <!-- Value Propositions Section -->
            <div class="bg-slate-50 py-24 relative">
                <div class="max-w-7xl mx-auto px-6">
                    <div class="text-center max-w-3xl mx-auto mb-16">
                        <h2 class="text-3xl font-extrabold text-slate-900 mb-4">Masa Depan IT Infrastructure</h2>
                        <p class="text-slate-500 text-lg">Mengapa perusahaan terkemuka mempercayakan arsitektur teknologi mereka kepada {brand.capitalize()}.</p>
                    </div>
                    <div class="grid grid-cols-1 md:grid-cols-3 gap-8">
                        {vp_html}
                    </div>
                </div>
            </div>

            <!-- About Section -->
            <div class="max-w-7xl mx-auto py-24 px-6">
                <div class="bg-white border border-slate-200 rounded-3xl p-8 md:p-12 shadow-sm grid grid-cols-1 md:grid-cols-2 gap-12 items-center">
                    <div class="space-y-6">
                        <h3 class="text-3xl font-extrabold text-slate-900">{data.get('home', {}).get('title', 'Tentang Kami')}</h3>
                        <div class="w-20 h-1.5 bg-brand-600 rounded-full"></div>
                        <p class="text-slate-600 leading-relaxed text-lg">{data.get('home', {}).get('about_summary', 'Deskripsi performa brand belum dimuat.')}</p>
                    </div>
                    <div class="relative h-full min-h-[300px] rounded-2xl overflow-hidden shadow-xl">
                        <img src="{get_asset_url('home', 'stock')}" class="absolute inset-0 w-full h-full object-cover" onerror="this.src='https://images.unsplash.com/photo-1526374965328-7f61d4dc18c5?w=600'">
                    </div>
                </div>
            </div>
        </section>

        <!-- ================= TAB PRODUK ================= -->
        <section id="tab-produk" class="tab-content bg-white">
            <div class="bg-brand-900 py-20 px-6 border-b border-brand-800">
                <div class="max-w-7xl mx-auto text-center space-y-4">
                    <h2 class="text-4xl font-extrabold text-white">{data.get('produk', {}).get('intro_page_title', 'Portofolio Produk')}</h2>
                    <p class="text-brand-100 max-w-2xl mx-auto text-lg">{data.get('produk', {}).get('intro_page_description', '')}</p>
                </div>
            </div>

            <div class="max-w-7xl mx-auto px-6 py-12 flex flex-col md:flex-row gap-12">
                <div class="md:w-1/4 flex-shrink-0">
                    <div class="sticky top-28 bg-white border border-slate-200 rounded-2xl p-2 shadow-sm overflow-hidden flex flex-col">
                        <div class="p-4 border-b border-slate-100 mb-2">
                            <span class="text-xs font-bold text-slate-400 uppercase tracking-wider">Katalog Produk</span>
                        </div>
                        {produk_sidebar if products_list else '<div class="p-4 text-sm text-slate-400">Belum ada produk.</div>'}
                    </div>
                </div>
                <div class="md:w-3/4">
                    {produk_content if products_list else '<div class="py-16 text-center text-slate-400">Data produk belum tersedia.</div>'}
                </div>
            </div>
        </section>

        <!-- ================= TAB SOLUSI ================= -->
        <section id="tab-solusi" class="tab-content bg-slate-50">
            <div class="relative bg-slate-900 py-24 px-6 overflow-hidden">
                <div class="absolute inset-0">
                    <img src="{get_asset_url('solusi', 'banner')}" class="w-full h-full object-cover opacity-20">
                    <div class="absolute inset-0 bg-gradient-to-b from-transparent to-slate-900"></div>
                </div>
                <div class="relative z-10 max-w-4xl mx-auto text-center space-y-4">
                    <h2 class="text-4xl md:text-5xl font-extrabold text-white">{data.get('solusi', {}).get('title', 'Solusi & Implementasi')}</h2>
                    <p class="text-slate-300 text-lg md:text-xl">{data.get('solusi', {}).get('intro', '')}</p>
                </div>
            </div>
            
            <div class="max-w-7xl mx-auto py-20 px-6">
                <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8">
                    {solusi_html}
                </div>
            </div>
        </section>

        <!-- ================= TAB CONTACT ================= -->
        <section id="tab-contact" class="tab-content bg-white">
            <div class="max-w-7xl mx-auto py-24 px-6">
                <div class="bg-slate-900 rounded-3xl overflow-hidden shadow-2xl flex flex-col md:flex-row">
                    <div class="md:w-5/12 bg-brand-600 p-12 text-white flex flex-col justify-between relative overflow-hidden">
                        <div class="absolute top-0 right-0 w-64 h-64 bg-white opacity-5 rounded-full blur-3xl transform translate-x-1/2 -translate-y-1/2"></div>
                        <div class="relative z-10 space-y-8">
                            <div>
                                <h2 class="text-4xl font-extrabold mb-2">{data.get('contact', {}).get('title', 'Hubungi Kami')}</h2>
                                <h3 class="text-brand-100 text-lg">{data.get('contact', {}).get('headline', '')}</h3>
                            </div>
                            <p class="text-brand-50 text-sm leading-relaxed">{data.get('contact', {}).get('cta_text', '')}</p>
                            
                            <div class="space-y-6 pt-8 border-t border-brand-500/50">
                                <div class="flex items-center gap-4">
                                    <div class="w-10 h-10 bg-brand-700/50 rounded-lg flex items-center justify-center"><i data-lucide="mail"></i></div>
                                    <div><p class="text-xs text-brand-200">Email</p><p class="font-semibold">{brand.lower()}@ilogoindonesia.com</p></div>
                                </div>
                                <div class="flex items-start gap-4">
                                    <div class="w-10 h-10 bg-brand-700/50 rounded-lg flex items-center justify-center flex-shrink-0"><i data-lucide="map-pin"></i></div>
                                    <div>
                                        <p class="text-xs text-brand-200">Headquarters (Support Center)</p>
                                        <p class="font-semibold text-sm">AKR Tower – 9th Floor<br>Jl. Panjang no. 5, Kebon Jeruk, Jakarta</p>
                                    </div>
                                </div>
                                <div class="flex items-start gap-4">
                                    <div class="w-10 h-10 bg-brand-700/50 rounded-lg flex items-center justify-center flex-shrink-0"><i data-lucide="building"></i></div>
                                    <div>
                                        <p class="text-xs text-brand-200">Sales & Marketing Office</p>
                                        <p class="font-semibold text-sm">Jl. Kebon Jeruk Raya Villa Kebon Jeruk Office F1, Jakarta</p>
                                    </div>
                                </div>
                                <div class="flex items-center gap-4">
                                    <div class="w-10 h-10 bg-brand-700/50 rounded-lg flex items-center justify-center"><i data-lucide="phone"></i></div>
                                    <div><p class="text-xs text-brand-200">Telepon</p><p class="font-semibold">(021) 53660861</p></div>
                                </div>
                            </div>
                        </div>
                    </div>
                    
                    <div class="md:w-7/12 p-12 bg-white flex flex-col justify-center">
                        <form class="space-y-6" onsubmit="event.preventDefault();">
                            <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
                                <div class="space-y-2"><label class="text-sm font-semibold text-slate-700">Nama Lengkap</label><input type="text" class="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 focus:outline-none focus:border-brand-500 focus:ring-1 focus:ring-brand-500" placeholder="John Doe"></div>
                                <div class="space-y-2"><label class="text-sm font-semibold text-slate-700">Email Perusahaan</label><input type="email" class="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 focus:outline-none focus:border-brand-500 focus:ring-1 focus:ring-brand-500" placeholder="john@company.com"></div>
                            </div>
                            <div class="space-y-2"><label class="text-sm font-semibold text-slate-700">Pesan / Kebutuhan IT</label><textarea rows="4" class="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 focus:outline-none focus:border-brand-500 focus:ring-1 focus:ring-brand-500" placeholder="Ceritakan tantangan infrastruktur Anda..."></textarea></div>
                            <button type="submit" class="w-full bg-slate-900 hover:bg-slate-800 text-white font-bold py-4 rounded-xl transition-all shadow-lg flex items-center justify-center gap-2">Kirim Pesan <i data-lucide="send" class="w-4 h-4"></i></button>
                        </form>
                    </div>
                </div>
            </div>
        </section>

    </main>

    <!-- Footer Terintegrasi 3 Kolom -->
    <footer class="bg-slate-950 text-slate-400 pt-16 pb-8 px-6 border-t border-slate-900 mt-auto">
        <div class="max-w-7xl mx-auto grid grid-cols-1 md:grid-cols-3 gap-12 mb-12 text-left">
            
            <!-- Kolom 1: Partnership -->
            <div class="space-y-6">
                <div class="flex items-center gap-3">
                    <div class="w-10 h-10 bg-brand-600 rounded-xl flex items-center justify-center text-white font-extrabold text-xl">
                        {brand[:2].upper()}
                    </div>
                    <span class="font-extrabold text-2xl text-white tracking-tight">{brand.capitalize()}</span>
                </div>
                <p class="text-sm leading-loose text-slate-400">
                    <strong class="text-white">{brand.capitalize()} Indonesia</strong> merupakan bagian dari PT. iLogo Infralogy Indonesia, yang bertindak sebagai partner resmi <strong class="text-white">{brand.capitalize()}</strong>. Selain itu, kami juga berperan sebagai penyedia layanan (vendor) sekaligus distributor berbagai produk Infrastruktur IT dan Cybersecurity terbaik di Indonesia.
                </p>
            </div>

            <!-- Kolom 2: Sales & Marketing -->
            <div class="space-y-6">
                <h4 class="font-bold text-white text-lg tracking-wide uppercase">Sales & Marketing</h4>
                <div class="space-y-4 text-sm">
                    <p class="font-bold text-slate-300">PT iLogo Indonesia</p>
                    <ul class="space-y-4">
                        <li class="flex items-start gap-3">
                            <i data-lucide="phone" class="w-5 h-5 text-brand-500 flex-shrink-0 mt-0.5"></i> 
                            <span>(021) 53660861</span>
                        </li>
                        <li class="flex items-start gap-3">
                            <i data-lucide="map-pin" class="w-5 h-5 text-brand-500 flex-shrink-0 mt-0.5"></i> 
                            <span>Jl. Kebon Jeruk Raya Villa Kebon Jeruk Office F1</span>
                        </li>
                        <li class="flex items-start gap-3">
                            <i data-lucide="mail" class="w-5 h-5 text-brand-500 flex-shrink-0 mt-0.5"></i> 
                            <span>{brand.lower()}@ilogoindonesia.com</span>
                        </li>
                    </ul>
                </div>
            </div>

            <!-- Kolom 3: Support Center & Medsos -->
            <div class="space-y-6">
                <h4 class="font-bold text-white text-lg tracking-wide uppercase">Support Center</h4>
                <ul class="space-y-4 text-sm mb-8">
                    <li class="flex items-start gap-3">
                        <i data-lucide="building-2" class="w-5 h-5 text-brand-500 flex-shrink-0 mt-0.5"></i> 
                        <span>AKR Tower – 9th Floor<br>Jl. Panjang no. 5, Kebon Jeruk</span>
                    </li>
                </ul>
                
                <h4 class="font-bold text-white text-lg tracking-wide uppercase">Ikuti Kami</h4>
                <div class="flex items-center gap-4">
                    <a href="#" class="w-10 h-10 rounded-full bg-slate-900 flex items-center justify-center border border-slate-800 hover:bg-brand-600 hover:border-brand-500 text-slate-400 hover:text-white transition-all">
                        <i data-lucide="facebook" class="w-4 h-4"></i>
                    </a>
                    <a href="#" class="w-10 h-10 rounded-full bg-slate-900 flex items-center justify-center border border-slate-800 hover:bg-brand-600 hover:border-brand-500 text-slate-400 hover:text-white transition-all">
                        <i data-lucide="instagram" class="w-4 h-4"></i>
                    </a>
                    <a href="#" class="w-10 h-10 rounded-full bg-slate-900 flex items-center justify-center border border-slate-800 hover:bg-brand-600 hover:border-brand-500 text-slate-400 hover:text-white transition-all">
                        <i data-lucide="linkedin" class="w-4 h-4"></i>
                    </a>
                </div>
            </div>

        </div>
        
        <div class="max-w-7xl mx-auto pt-8 border-t border-slate-900 text-center flex flex-col md:flex-row items-center justify-between gap-4">
            <p class="text-xs text-slate-500">© 2026 PT. iLogo Infralogy Indonesia. All Rights Reserved.</p>
            <p class="text-xs text-slate-600">Generated by iAAWG</p>
        </div>
    </footer>

    <script>
        // Tab Navigasi Utama
        function switchTab(tabId) {{
            document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
            document.getElementById('tab-' + tabId).classList.add('active');
            
            // Reset Navbar Styling
            document.querySelectorAll('.tab-btn').forEach(btn => {{
                if (btn.id !== 'btn-contact') {{
                    btn.classList.remove('bg-brand-50', 'text-brand-600');
                    btn.classList.add('text-slate-600', 'hover:bg-slate-50');
                }}
            }});
            
            // Set Active Navbar
            const activeBtn = document.getElementById('btn-' + tabId);
            if(activeBtn && activeBtn.id !== 'btn-contact') {{
                activeBtn.classList.remove('text-slate-600', 'hover:bg-slate-50');
                activeBtn.classList.add('bg-brand-50', 'text-brand-600');
            }}
            
            window.scrollTo({{ top: 0, behavior: 'smooth' }});
        }}

        // Tab Navigasi Produk Internal
        function switchProdukTab(prodSlug) {{
            document.querySelectorAll('.produk-tab-content').forEach(el => {{ el.style.display = 'none'; }});
            
            const target = document.getElementById('produk-tab-' + prodSlug);
            if (target) {{ 
                target.style.display = 'block'; 
                // Retrigger animation
                target.classList.remove('animate-fade-in');
                void target.offsetWidth; 
                target.classList.add('animate-fade-in');
            }}
            
            document.querySelectorAll('.produk-tab-btn').forEach(btn => {{
                btn.classList.remove('bg-brand-50', 'text-brand-700', 'border-brand-600', 'font-bold');
                btn.classList.add('text-slate-500', 'border-transparent', 'font-medium');
            }});
            
            const activeSubBtn = document.getElementById('produk-btn-' + prodSlug);
            if (activeSubBtn) {{
                activeSubBtn.classList.remove('text-slate-500', 'border-transparent', 'font-medium');
                activeSubBtn.classList.add('bg-brand-50', 'text-brand-700', 'border-brand-600', 'font-bold');
            }}
        }}

        lucide.createIcons();
    </script>
</body>
</html>
"""
    with open(preview_file, "w", encoding="utf-8") as fh:
        fh.write(html_content)
    print(f"[✓] Berhasil mengompilasi File Preview Lokal Terintegrasi di: {preview_file}")


class LogCaptureStream:
    """Helper untuk menangkap print statement dan memperbarui progress bar secara presisi"""
    def write(self, text):
        global current_progress, total_prompt_tokens, total_completion_tokens
        clean_text = text.strip()
        
        if not clean_text:
            return
            
        if "[TOKEN_USAGE]" in clean_text:
            try:
                parts = clean_text.split("|")
                p_val = int(parts[0].split(":")[1].strip())
                c_val = int(parts[1].split(":")[1].strip())
                total_prompt_tokens += p_val
                total_completion_tokens += c_val
            except Exception:
                pass
            return 

        process_logs.append(clean_text)
        
        upper_text = clean_text.upper()
        if "MEMPROSES" in upper_text and "ASET VISUAL" in upper_text:
            if "HOME" in upper_text: current_progress = 20
            elif "SOLUSI" in upper_text: current_progress = 60
            elif "CONTACT" in upper_text: current_progress = 70
        elif "MEMULAI PROSES" in upper_text and "HALAMAN PRODUK INDIVIDUAL" in upper_text:
            current_progress = 75
        elif "MEMPROSES ASET VISUAL UNTUK PRODUK" in upper_text:
            if current_progress < 95:
                current_progress = min(current_progress + 5, 95)
        elif "SELURUH PIPELINE" in upper_text and "BERHASIL SELESAI!" in upper_text:
            current_progress = 100

    def flush(self):
        pass


async def pipeline_wrapper(brand: str, url: str, skip_generation: bool, custom_creds: dict, skip_deploy: bool, product_urls: list, llm_provider: str, primary_color: str):
    global is_running, process_logs, current_progress, current_brand, total_prompt_tokens, total_completion_tokens, current_task
    
    current_task = asyncio.current_task()
    is_running = True
    current_progress = 5
    current_brand = brand
    total_prompt_tokens = 0      
    total_completion_tokens = 0  
    process_logs.clear()
    
    old_stdout = sys.stdout
    sys.stdout = LogCaptureStream()
    
    try:
        await run_pipeline(brand, url, skip_generation, custom_creds, skip_deploy=skip_deploy, product_urls=product_urls, llm_provider=llm_provider, primary_color=primary_color)
        generate_local_preview_html(brand, primary_color)
        current_progress = 100
    except asyncio.CancelledError:
        process_logs.append("[X] Proses dihentikan paksa oleh operator (Aborted).")
        current_progress = 0
    except Exception as e:
        import traceback
        error_msg = f"[ERROR] Terjadi kegagalan sistem: {str(e)}\n{traceback.format_exc()}"
        process_logs.append(error_msg)
        print(error_msg)  # supaya kelihatan di terminal juga
        if current_progress == 100:
            current_progress = 99
    finally:
        sys.stdout = old_stdout
        is_running = False
        current_task = None  


@app.get("/", response_class=HTMLResponse)
async def index_page():
    html_content = """<!DOCTYPE html>
<html lang="id">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>iLogo AI Auto Website Generator</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
    <script src="https://unpkg.com/lucide@latest"></script>
    <script>
        tailwind.config = {
            theme: {
                extend: {
                    colors: {
                        ilogo: {
                            green: '#1E7E34',
                            orange: '#FF9E1B',
                        }
                    },
                    fontFamily: {
                        sans: ['Inter', 'sans-serif'],
                        mono: ['JetBrains Mono', 'monospace'],
                    }
                }
            }
        }
    </script>
</head>
<body class="bg-slate-50 text-slate-800 min-h-screen antialiased">

    <header class="border-b border-slate-200 bg-white sticky top-0 z-50 px-6 py-4 shadow-sm">
        <div class="max-w-7xl mx-auto flex items-center justify-between">
            <div class="flex items-center space-x-3">
                <div class="bg-ilogo-green text-white p-2 rounded-lg">
                    <i data-lucide="cpu" class="w-5 h-5"></i>
                </div>
                <div>
                    <h1 class="text-base font-bold tracking-tight text-slate-950">iLogo AI Auto Website Generator (iAAWG)</h1>
                    <p class="text-xs text-slate-500">Hasilkan website subdomain iLogo secara otomatis dari website resmi brand.</p>
                </div>
            </div>
        </div>
    </header>

    <main class="max-w-7xl mx-auto p-6 grid grid-cols-1 lg:grid-cols-12 gap-6">
        <form id="generatorForm" onsubmit="startGeneration(event)" enctype="multipart/form-data" class="lg:col-span-5 space-y-5">
            <div class="bg-white border border-slate-200 rounded-xl p-5 space-y-4 shadow-sm">
                <div class="space-y-1.5">
                    <label for="brand" class="text-xs font-semibold text-slate-700">Nama Brand:</label>
                    <input type="text" id="brand" name="brand" placeholder="Contoh: zecurion" required class="w-full bg-slate-50 border border-slate-200 rounded-lg px-3 py-2 text-sm text-slate-900 placeholder-slate-400 focus:outline-none focus:border-ilogo-green focus:bg-white transition-all">
                </div>
                <div class="space-y-1.5">
                    <label for="url" class="text-xs font-semibold text-slate-700">URL Homepage Referensi:</label>
                    <input type="text" id="url" name="url" placeholder="Contoh: zecurion.com" class="w-full bg-slate-50 border border-slate-200 rounded-lg px-3 py-2 text-sm text-slate-900 placeholder-slate-400 focus:outline-none focus:border-ilogo-green focus:bg-white transition-all">
                </div>
                <div class="space-y-3">
                    <label class="text-xs font-semibold text-slate-700 block">Konfigurasi Rantai Failover LLM:</label>
    
                    <div class="grid grid-cols-1 md:grid-cols-3 gap-3">
                        <!-- Prioritas 1 (Utama) -->
                        <div class="space-y-1">
                            <label for="llm_p1" class="text-[11px] font-medium text-slate-500">Prioritas 1 (Utama)</label>
                            <select id="llm_p1" name="llm_p1" class="w-full bg-slate-50 border border-slate-200 rounded-lg px-3 py-2 text-sm text-slate-900 focus:outline-none focus:border-ilogo-green focus:bg-white transition-all">
                                <option value="groq" selected>Groq (Llama 3.1)</option>
                                <option value="cerebras">Cerebras (Gemma 4)</option>
                                <option value="github">GitHub Models (GPT-4o-mini)</option>
                            </select>
                        </div>

                        <!-- Prioritas 2 (Backup 1) -->
                        <div class="space-y-1">
                            <label for="llm_p2" class="text-[11px] font-medium text-slate-500">Prioritas 2 (Cadangan 1)</label>
                            <select id="llm_p2" name="llm_p2" class="w-full bg-slate-50 border border-slate-200 rounded-lg px-3 py-2 text-sm text-slate-900 focus:outline-none focus:border-ilogo-green focus:bg-white transition-all">
                                <option value="">-- Tidak Digunakan --</option>
                                <option value="groq">Groq (Llama 3.1)</option>
                                <option value="cerebras" selected>Cerebras (Gemma 4)</option>
                                <option value="github">GitHub Models (GPT-4o-mini)</option>
                            </select>
                        </div>

                        <!-- Prioritas 3 (Backup 2) -->
                        <div class="space-y-1">
                            <label for="llm_p3" class="text-[11px] font-medium text-slate-500">Prioritas 3 (Cadangan 2)</label>
                            <select id="llm_p3" name="llm_p3" class="w-full bg-slate-50 border border-slate-200 rounded-lg px-3 py-2 text-sm text-slate-900 focus:outline-none focus:border-ilogo-green focus:bg-white transition-all">
                                <option value="">-- Tidak Digunakan --</option>
                                <option value="groq">Groq (Llama 3.1)</option>
                                <option value="cerebras">Cerebras (Gemma 4)</option>
                                <option value="github" selected>GitHub Models (GPT-4o-mini)</option>
                            </select>
                        </div>
                    </div>
                    <p class="text-[10px] text-slate-400 mt-1">Sistem akan mengeksekusi dari Prioritas 1. Jika gagal/limit, otomatis berpindah ke Prioritas berikutnya yang aktif.</p>
                </div>
                <div class="space-y-1.5">
                    <label for="product_urls" class="text-xs font-semibold text-slate-700">URL Produk (opsional, satu per baris):</label>
                    <textarea id="product_urls" name="product_urls" rows="3" class="w-full bg-slate-50 border border-slate-200 rounded-lg px-3 py-2 text-sm text-slate-900 placeholder-slate-400 focus:outline-none focus:border-ilogo-green focus:bg-white transition-all" placeholder="https://zecurion.com/produk-a&#10;https://zecurion.com/produk-b"></textarea>
                    <p class="text-[10px] text-slate-400">Jika diisi, sistem akan mengabaikan produk yang diekstrak dari homepage dan hanya memproses produk dari URL ini.</p>
                </div>
                <div class="space-y-1.5">
                    <label for="logo_file" class="text-xs font-semibold text-slate-700">Upload Logo Brand (opsional):</label>
                    <input type="file" id="logo_file" name="logo_file" accept="image/*" class="w-full text-sm text-slate-500 file:mr-4 file:py-2 file:px-4 file:rounded-full file:border-0 file:text-sm file:font-semibold file:bg-ilogo-green file:text-white hover:file:bg-ilogo-green/80 transition-all">
                    <p class="text-[10px] text-slate-400">Jika tidak diunggah, akan digunakan warna default iLogo (#1E7E34).</p>
                </div>
            </div>

            <div class="bg-white border border-slate-200 rounded-xl p-5 space-y-3 shadow-sm">
                <label class="flex items-start gap-3 p-2.5 rounded-lg border border-transparent hover:bg-slate-50 cursor-pointer select-none">
                    <input type="checkbox" id="skip_generation" name="skip_generation" class="mt-1 rounded border-slate-300 text-ilogo-green w-4 h-4 accent-ilogo-green">
                    <div class="space-y-0.5">
                        <span class="text-xs font-semibold text-slate-900 block">Skip Generation Mode</span>
                        <span class="text-[11px] text-slate-500 block">Gunakan data JSON lokal yang sudah ada (hemat token LLM).</span>
                    </div>
                </label>

                <label class="flex items-start gap-3 p-2.5 rounded-lg bg-amber-50/60 border border-amber-200 cursor-pointer select-none">
                    <input type="checkbox" id="skip_deploy" name="skip_deploy" onchange="toggleWpForm(this.checked)" class="mt-1 rounded border-amber-300 text-ilogo-orange w-4 h-4 accent-ilogo-orange">
                    <div class="space-y-0.5">
                        <span class="text-xs font-semibold text-amber-950 block">Local Draft Mode Only</span>
                        <span class="text-[11px] text-amber-700 block">Hanya buat teks & gambar di lokal komputer tanpa unggah ke WordPress.</span>
                    </div>
                </label>
            </div>

            <div id="wpCredentialsSection" class="bg-white border border-slate-200 rounded-xl p-5 space-y-3.5 shadow-sm transition-all duration-300">
                <div class="flex items-center space-x-2 pb-1 border-b border-slate-100">
                    <i data-lucide="wordpress" class="w-4 h-4 text-slate-500"></i>
                    <h3 class="text-xs font-bold text-slate-800 tracking-wide uppercase">Target Deployment Custom</h3>
                </div>
                <div class="space-y-1">
                    <label for="wp_url" class="text-[11px] font-semibold text-slate-600">WordPress Base URL:</label>
                    <input type="url" id="wp_url" name="wp_url" placeholder="https://subdomain.ilogo.co.id" class="wp-input w-full bg-slate-50 border border-slate-200 rounded-lg px-3 py-1.5 text-xs focus:outline-none focus:border-ilogo-green focus:bg-white transition-all">
                </div>
                <div class="grid grid-cols-2 gap-3">
                    <div class="space-y-1">
                        <label for="wp_username" class="text-[11px] font-semibold text-slate-600">Username Admin:</label>
                        <input type="text" id="wp_username" name="wp_username" placeholder="admin_ilogo" class="wp-input w-full bg-slate-50 border border-slate-200 rounded-lg px-3 py-1.5 text-xs focus:outline-none focus:border-ilogo-green focus:bg-white transition-all">
                    </div>
                    <div class="space-y-1">
                        <label for="wp_app_password" class="text-[11px] font-semibold text-slate-600">Application Password:</label>
                        <input type="password" id="wp_app_password" name="wp_app_password" placeholder="xxxx xxxx xxxx xxxx" class="wp-input w-full bg-slate-50 border border-slate-200 rounded-lg px-3 py-1.5 text-xs focus:outline-none focus:border-ilogo-green focus:bg-white transition-all">
                    </div>
                </div>
            </div>

            <div class="flex gap-3">
                <button type="submit" id="submitBtn" class="flex-grow bg-slate-900 hover:bg-slate-800 text-white text-sm font-semibold py-3 px-4 rounded-xl shadow-md transition-all flex items-center justify-center">
                    <span>Mulai Proses Otomatisasi</span>
                </button>
                <button type="button" id="stopBtn" onclick="stopGeneration()" class="hidden bg-rose-600 hover:bg-rose-700 text-white text-sm font-semibold py-3 px-4 rounded-xl shadow-md transition-all flex items-center justify-center">
                    <span>Stop</span>
                </button>
            </div>
        </form>

        <div class="lg:col-span-7 space-y-5 flex flex-col h-[calc(100vh-140px)] sticky top-[90px]">
            <div class="bg-white border border-slate-200 rounded-xl p-5 shadow-sm flex flex-col flex-grow overflow-hidden">
                <div class="flex items-center justify-between pb-3 border-b border-slate-100 flex-shrink-0">
                    <div class="flex items-center space-x-2">
                        <span class="relative flex h-2 w-2">
                            <span id="pulseStatus" class="animate-ping absolute inline-flex h-full w-full rounded-full bg-slate-400 opacity-75"></span>
                            <span id="dotStatus" class="relative inline-flex rounded-full h-2 w-2 bg-slate-400"></span>
                        </span>
                        <h2 class="text-xs font-bold text-slate-800 tracking-wide uppercase">Monitor Real-Time Progress</h2>
                    </div>
                    <div id="previewActionWrapper" class="hidden">
                        <a id="btnBukaPreview" href="#" target="_blank" class="inline-flex items-center space-x-1.5 bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-medium px-3 py-1.5 rounded-lg shadow-sm transition-all">
                            <i data-lucide="external-link" class="w-3.5 h-3.5"></i>
                            <span>Buka Pratinjau Lokal</span>
                        </a>
                    </div>
                </div>

                <div class="py-4 border-b border-slate-50 flex-shrink-0">
                    <div class="flex justify-between text-xs font-medium text-slate-500 mb-1.5">
                        <span id="progressBarLabel">Sistem Standby</span>
                        <span id="progressBarPercent" class="font-mono font-semibold text-slate-700">0%</span>
                    </div>
                    <div class="w-full bg-slate-100 rounded-full h-2">
                        <div id="progressBarFill" class="bg-slate-400 h-2 rounded-full transition-all duration-500" style="width: 0%"></div>
                    </div>
                    <div class="flex space-x-3 mt-3">
                        <div class="flex items-center space-x-1.5 bg-slate-100 px-2.5 py-1 rounded-md border border-slate-200">
                            <i data-lucide="arrow-right-to-line" class="w-3 h-3 text-slate-400"></i>
                            <span class="text-[10px] font-semibold text-slate-500 uppercase tracking-wider">Input Tokens:</span>
                            <span id="uiPromptTokens" class="text-[11px] font-mono font-bold text-slate-800">0</span>
                        </div>
                        <div class="flex items-center space-x-1.5 bg-slate-100 px-2.5 py-1 rounded-md border border-slate-200">
                            <i data-lucide="arrow-left-from-line" class="w-3 h-3 text-slate-400"></i>
                            <span class="text-[10px] font-semibold text-slate-500 uppercase tracking-wider">Output Tokens:</span>
                            <span id="uiCompletionTokens" class="text-[11px] font-mono font-bold text-slate-800">0</span>
                        </div>
                    </div>
                </div>

                <div class="flex-grow overflow-y-auto pt-3 font-mono text-[11px] leading-relaxed text-slate-400 bg-slate-950 p-4 rounded-xl mt-3 shadow-inner scrollbar-thin" id="logConsole">
                    <div class="text-slate-500 italic">// Menunggu perintah eksekusi dari operator...</div>
                </div>
            </div>
        </div>
    </main>

    <script>
        let intervalId = null;

        function toggleWpForm(isDraftOnly) {
            const section = document.getElementById('wpCredentialsSection');
            const inputs = document.querySelectorAll('.wp-input');
            if (isDraftOnly) {
                section.classList.add('opacity-40', 'pointer-events-none');
                inputs.forEach(i => i.removeAttribute('required'));
            } else {
                section.classList.remove('opacity-40', 'pointer-events-none');
            }
        }

        async function startGeneration(e) {
            e.preventDefault();
            const form = document.getElementById('generatorForm');
            const formData = new FormData(form);

            document.getElementById('submitBtn').disabled = true;
            document.getElementById('submitBtn').classList.add('opacity-50');
            
            document.getElementById('stopBtn').classList.remove('hidden');
            document.getElementById('stopBtn').disabled = false;
            document.getElementById('stopBtn').innerHTML = '<span>Stop</span>';

            document.getElementById('previewActionWrapper').classList.add('hidden');
            document.getElementById('dotStatus').className = "relative inline-flex rounded-full h-2 w-2 bg-emerald-500";
            document.getElementById('pulseStatus').className = "animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75";
            document.getElementById('progressBarFill').className = "bg-emerald-600 h-2 rounded-full transition-all duration-500";
            document.getElementById('logConsole').innerHTML = '<div class="text-emerald-400 animate-pulse">[!] Menginisialisasi subproses backend... silakan tunggu...</div>';

            try {
                const response = await fetch('/generate', {
                    method: 'POST',
                    body: formData
                });
                const result = await response.json();
                
                if(response.ok) {
                    if(intervalId) clearInterval(intervalId);
                    intervalId = setInterval(pollProgress, 1000);
                } else {
                    alert("Gagal memulai pipeline: " + result.detail);
                    resetButton();
                }
            } catch(err) {
                alert("Kendala koneksi server: " + err);
                resetButton();
            }
        }

        async function stopGeneration() {
            const stopBtn = document.getElementById('stopBtn');
            stopBtn.disabled = true;
            stopBtn.innerText = "Stopping...";
            
            try {
                const response = await fetch('/stop', {
                    method: 'POST'
                });
                if(!response.ok) {
                    const result = await response.json();
                    alert("Gagal menghentikan proses: " + result.detail);
                }
            } catch(err) {
                alert("Kendala saat menghubungi server: " + err);
            }
        }

        async function pollProgress() {
            try {
                const response = await fetch('/status');
                const data = await response.json();

                const consoleEl = document.getElementById('logConsole');
                if (data.logs.length > 0) {
                    consoleEl.innerHTML = data.logs.map(log => {
                        let baseClass = "px-3 py-1.5 mb-2 rounded-lg border-l-4 font-sans text-xs flex items-start gap-2 transition-all ";
        
                        if (log.includes('[✓]')) {
                            return `<div class="${baseClass} bg-emerald-950/40 border-emerald-500 text-emerald-300">
                                        <span class="text-emerald-400 font-bold flex-shrink-0">✓</span>
                                        <div>${log.replace('[✓]', '').trim()}</div>
                                    </div>`;
                        }
                        if (log.includes('[X]') || log.includes('[ERROR]')) {
                            return `<div class="${baseClass} bg-rose-950/40 border-rose-500 text-rose-300 animate-pulse">
                                        <span class="text-rose-400 font-bold flex-shrink-0">✕</span>
                                        <div>${log.replace('[X]', '').replace('[ERROR]', '').trim()}</div>
                                    </div>`;
                        }
                        if (log.includes('[!]') || log.includes('[~]')) {
                            return `<div class="${baseClass} bg-amber-950/40 border-amber-500 text-amber-300">
                                        <span class="text-amber-400 font-bold flex-shrink-0">⚡</span>
                                        <div>${log.replace('[!]', '').replace('[~]', '').trim()}</div>
                                    </div>`;
                        }
                        if (log.includes('[*]')) {
                            return `<div class="${baseClass} bg-slate-900 border-sky-500 text-slate-100 font-semibold tracking-wide mt-4">
                                        <span class="text-sky-400 font-bold flex-shrink-0">◆</span>
                                        <div>${log.replace('[*]', '').trim()}</div>
                                    </div>`;
                        }
        
                        return `<div class="${baseClass} bg-slate-900/50 border-slate-700 text-slate-400">
                                    <span class="text-slate-500 flex-shrink-0">➔</span>
                                    <div>${log}</div>
                                </div>`;
                    }).join('');
    
                    consoleEl.scrollTop = consoleEl.scrollHeight;
                }

                document.getElementById('progressBarPercent').innerText = data.progress + '%';
                document.getElementById('progressBarFill').style.width = data.progress + '%';
                
                document.getElementById('uiPromptTokens').innerText = data.prompt_tokens.toLocaleString();
                document.getElementById('uiCompletionTokens').innerText = data.completion_tokens.toLocaleString();
                
                if(data.is_running) {
                    document.getElementById('progressBarLabel').innerText = "Sedang memproses dokumen...";
                } else {
                    document.getElementById('progressBarLabel').innerText = data.progress === 100 ? "Proses Selesai" : "Proses Dihentikan";
                    clearInterval(intervalId);
                    resetButton();
                    
                    if(data.progress === 100 && data.brand) {
                        const previewBtn = document.getElementById('btnBukaPreview');
                        previewBtn.href = `/output/${data.brand.toLowerCase()}/content/preview_lokal.html`;
                        document.getElementById('previewActionWrapper').classList.remove('hidden');
                    }
                }
            } catch(err) {
                console.error("Gagal polling data status:", err);
            }
        }

        function resetButton() {
            document.getElementById('submitBtn').disabled = false;
            document.getElementById('submitBtn').classList.remove('opacity-50');
            document.getElementById('stopBtn').classList.add('hidden');
            document.getElementById('dotStatus').className = "relative inline-flex rounded-full h-2 w-2 bg-slate-400";
            document.getElementById('pulseStatus').className = "hidden";
        }

        lucide.createIcons();
    </script>
</body>
</html>
"""
    return HTMLResponse(content=html_content)


@app.post("/generate")
async def start_generation_endpoint(
    background_tasks: BackgroundTasks,
    brand: str = Form(...),
    url: str = Form(""),
    skip_generation: bool = Form(False),
    skip_deploy: bool = Form(False),
    wp_url: str = Form(""),
    wp_username: str = Form(""),
    wp_app_password: str = Form(""),
    product_urls: str = Form(""),
    # --- PERUBAHAN DI SINI: Mengganti llm_provider tunggal menjadi 3 prioritas ---
    llm_p1: str = Form(...),
    llm_p2: str = Form(""),
    llm_p3: str = Form(""),
    logo_file: UploadFile = File(None)
):
    global is_running
    if is_running:
        return JSONResponse(status_code=400, content={"detail": "Proses pipeline lain saat ini sedang berjalan."})

    if not skip_generation and not url:
        return JSONResponse(status_code=400, content={"detail": "URL Homepage Referensi wajib diisi jika Skip Generation tidak dicentang."})

    # Ekstrak warna dari logo jika diunggah
    primary_color = DEFAULT_PRIMARY_COLOR
    if logo_file and logo_file.filename:
        # Simpan file sementara
        suffix = os.path.splitext(logo_file.filename)[1] or ".png"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            content = await logo_file.read()
            tmp.write(content)
            tmp_path = tmp.name
        try:
            palette = ColorExtractor.extract_palette(tmp_path, color_count=3)
            if palette:
                primary_color = palette[0]  # ambil warna dominan
                print(f"[Color] Ekstraksi berhasil, warna utama: {primary_color}")
            else:
                print("[Color] Ekstraksi gagal, menggunakan default iLogo.")
        except Exception as e:
            print(f"[Color] Gagal mengekstrak warna dari logo: {e}, menggunakan default.")
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
    else:
        print("[Color] Tidak ada logo diunggah, menggunakan warna default iLogo.")

    custom_creds = None
    if not skip_deploy and wp_url and wp_username and wp_app_password:
        custom_creds = {
            "wp_url": wp_url,
            "wp_username": wp_username,
            "wp_app_password": wp_app_password
        }

    # Parse product_urls dari textarea (satu per baris)
    product_urls_list = []
    if product_urls:
        product_urls_list = [u.strip() for u in product_urls.splitlines() if u.strip()]

    # --- PERUBAHAN DI SINI: Logika penyusunan rantai failover dinamis ---
    selected_providers = []
    for p in [llm_p1, llm_p2, llm_p3]:
        if p and p not in selected_providers:  # Ambil yang tidak kosong dan hindari duplikat
            selected_providers.append(p)
            
    # Jika karena suatu hal semuanya kosong, beri default "groq"
    dynamic_provider_chain = ",".join(selected_providers) if selected_providers else "groq"

    # --- PERUBAHAN DI SINI: Kirim `dynamic_provider_chain` ke pipeline_wrapper ---
    background_tasks.add_task(
        pipeline_wrapper, 
        brand, 
        url, 
        skip_generation, 
        custom_creds, 
        skip_deploy, 
        product_urls_list, 
        dynamic_provider_chain, # Menggantikan llm_provider lama
        primary_color
    )
    
    return {"status": "started"}


@app.post("/stop")
async def stop_generation_endpoint():
    global current_task, is_running
    if not is_running or not current_task:
        return JSONResponse(status_code=400, content={"detail": "Tidak ada proses aktif yang sedang berjalan."})
    
    current_task.cancel()
    return {"status": "stopping"}


@app.get("/status")
async def get_status_endpoint():
    global process_logs, is_running, current_progress, current_brand, total_prompt_tokens, total_completion_tokens
    return {
        "is_running": is_running,
        "progress": current_progress,
        "logs": process_logs,
        "brand": current_brand,
        "prompt_tokens": total_prompt_tokens,
        "completion_tokens": total_completion_tokens
    }