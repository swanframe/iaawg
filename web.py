import os
import sys
import json
import asyncio
from fastapi import FastAPI, Request, Form, BackgroundTasks
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from main import run_pipeline

app = FastAPI(title="iAAWG Web UI")

# Mount folder output agar pratinjau lokal dan aset gambar bisa diakses langsung lewat browser
if not os.path.exists("output"):
    os.makedirs("output", exist_ok=True)
app.mount("/output", StaticFiles(directory="output"), name="output")

process_logs = []
is_running = False
current_progress = 0
current_brand = ""
# Tambahan variabel global untuk token
total_prompt_tokens = 0
total_completion_tokens = 0

# BARU: Simpan referensi task asyncio yang sedang berjalan secara global
current_task = None

def generate_local_preview_html(brand: str):
    """
    Membaca data JSON dari output lokal dan menyusun sebuah landing page 
    simulasi terintegrasi berbasis Tailwind CSS untuk kebutuhan operator.
    """
    brand_lower = brand.lower()
    content_dir = os.path.join("output", brand_lower, "content")
    preview_file = os.path.join(content_dir, "preview_lokal.html")
    
    pages = ["home", "produk", "solusi", "contact", "blog"]
    data = {}
    
    # Load semua file JSON halaman
    for p in pages:
        file_path = os.path.join(content_dir, f"{p}.json")
        if os.path.exists(file_path):
            with open(file_path, "r", encoding="utf-8") as f:
                try:
                    data[p] = json.load(f)
                except:
                    data[p] = {}
        else:
            data[p] = {}

    # Setup path gambar lokal (menggunakan path relatif web browser)
    def get_asset_url(p_type, a_type):
        return f"/output/{brand_lower}/visual/{brand_lower}_{p_type}_{a_type}.jpg"

    html_content = f"""<!DOCTYPE html>
<html lang="id">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Pratinjau Lokal - {brand.upper()} Hub</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700&display=swap" rel="stylesheet">
    <script src="https://unpkg.com/lucide@latest"></script>
    <style>
        body {{ font-family: 'Plus Jakarta Sans', sans-serif; }}
        .tab-content {{ display: none; }}
        .tab-content.active {{ display: block; }}
    </style>
</head>
<body class="bg-slate-50 text-slate-800 min-h-screen flex flex-col">

    <!-- Top Floating Navbar Simulasi -->
    <header class="bg-white border-b border-slate-200 sticky top-0 z-50 shadow-sm">
        <div class="max-w-7xl mx-auto px-6 py-4 flex flex-col md:flex-row items-center justify-between gap-4">
            <div class="flex items-center space-x-3">
                <div class="bg-emerald-600 text-white p-2 rounded-lg font-bold tracking-wider text-sm shadow-md">
                    {brand.upper()}
                </div>
                <div>
                    <h1 class="text-base font-bold text-slate-900">iLogo Partner Preview Panel</h1>
                    <p class="text-xs text-slate-500">Simulasi Tampilan Sebelum Publikasi Live</p>
                </div>
            </div>
            
            <!-- Tab Menu Navigasi -->
            <nav class="flex space-x-1 bg-slate-100 p-1 rounded-xl">
                <button onclick="switchTab('home')" id="btn-home" class="tab-btn px-4 py-2 text-xs font-semibold rounded-lg bg-white text-emerald-700 shadow-sm transition-all">Beranda</button>
                <button onclick="switchTab('produk')" id="btn-produk" class="tab-btn px-4 py-2 text-xs font-semibold rounded-lg text-slate-600 hover:text-slate-900 transition-all">Produk</button>
                <button onclick="switchTab('solusi')" id="btn-solusi" class="tab-btn px-4 py-2 text-xs font-semibold rounded-lg text-slate-600 hover:text-slate-900 transition-all">Solusi</button>
                <button onclick="switchTab('blog')" id="btn-blog" class="tab-btn px-4 py-2 text-xs font-semibold rounded-lg text-slate-600 hover:text-slate-900 transition-all">Artikel & Edukasi</button>
                <button onclick="switchTab('contact')" id="btn-contact" class="tab-btn px-4 py-2 text-xs font-semibold rounded-lg text-slate-600 hover:text-slate-900 transition-all">Hubungi Kami</button>
            </nav>
        </div>
    </header>

    <!-- Main Container Simulasi Website -->
    <main class="flex-grow w-full">
        
        <!-- ================= TAB BERANDA ================= -->
        <section id="tab-home" class="tab-content active">
            <!-- Hero Banner -->
            <div class="relative bg-slate-900 text-white overflow-hidden py-24 px-6">
                <div class="absolute inset-0 opacity-40">
                    <img src="{get_asset_url('home', 'banner')}" class="w-full h-full object-cover" onerror="this.src='https://images.unsplash.com/photo-1518770660439-4636190af475?w=1200'">
                </div>
                <div class="relative max-w-5xl mx-auto text-center space-y-6">
                    <span class="bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 px-3 py-1 rounded-full text-xs font-semibold tracking-wide uppercase">Solusi Utama Terintegrasi</span>
                    <h2 class="text-3xl md:text-5xl font-extrabold tracking-tight leading-tight">{data.get('home', {}).get('hero_headline', 'Infrastruktur Canggih untuk Bisnis Anda')}</h2>
                    <p class="text-base md:text-xl text-slate-300 max-w-3xl mx-auto">{data.get('home', {}).get('hero_subheadline', '')}</p>
                    <div class="pt-4">
                        <button onclick="switchTab('contact')" class="bg-emerald-600 hover:bg-emerald-500 text-white font-semibold px-6 py-3 rounded-lg transition-all shadow-lg shadow-emerald-900/20">Konsultasi Sekarang</button>
                    </div>
                </div>
            </div>
            
            <!-- Ringkasan Tentang Brand -->
            <div class="max-w-5xl mx-auto py-16 px-6 grid grid-cols-1 md:grid-cols-2 gap-12 items-center">
                <div class="space-y-4">
                    <h3 class="text-2xl font-bold text-slate-900">{data.get('home', {}).get('title', 'Tentang Kami')}</h3>
                    <p class="text-slate-600 leading-relaxed text-sm">{data.get('home', {}).get('about_summary', 'Deskripsi performa brand belum dimuat.')}</p>
                </div>
                <div class="bg-white p-6 border border-slate-200 rounded-2xl shadow-sm">
                    <img src="{get_asset_url('home', 'stock')}" class="w-full h-48 object-cover rounded-xl" onerror="this.src='https://images.unsplash.com/photo-1526374965328-7f61d4dc18c5?w=600'">
                </div>
            </div>
        </section>

        <!-- ================= TAB PRODUK ================= -->
        <section id="tab-produk" class="tab-content">
            <div class="bg-slate-100 border-b border-slate-200 py-12 px-6 text-center">
                <h2 class="text-3xl font-bold text-slate-900">{data.get('produk', {}).get('title', 'Portofolio Produk Kami')}</h2>
                <p class="text-slate-500 max-w-2xl mx-auto mt-2 text-sm">{data.get('produk', {}).get('intro', '')}</p>
            </div>
            <div class="max-w-5xl mx-auto py-16 px-6">
                <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
                    """
    
    # Loop render produk_list jika ada
    products = data.get('produk', {}).get('products_list', [])
    for p_item in products:
        html_content += f"""
                    <div class="bg-white p-6 border border-slate-200 rounded-xl shadow-sm hover:shadow-md transition-all space-y-3">
                        <div class="w-10 h-10 bg-emerald-50 rounded-lg flex items-center justify-center text-emerald-600">
                            <i data-lucide="box" class="w-5 h-5"></i>
                        </div>
                        <h4 class="text-lg font-bold text-slate-900">{p_item.get('name', '')}</h4>
                        <p class="text-slate-600 text-sm leading-relaxed">{p_item.get('description', '')}</p>
                    </div>"""

    html_content += f"""
                </div>
            </div>
        </section>

        <!-- ================= TAB SOLUSI ================= -->
        <section id="tab-solusi" class="tab-content">
            <div class="bg-slate-900 text-white py-16 px-6 text-center relative overflow-hidden">
                <div class="absolute inset-0 opacity-20">
                    <img src="{get_asset_url('solusi', 'banner')}" class="w-full h-full object-cover">
                </div>
                <div class="relative z-10 max-w-3xl mx-auto space-y-2">
                    <h2 class="text-3xl font-bold">{data.get('solusi', {}).get('title', 'Solusi & Implementasi')}</h2>
                    <p class="text-slate-400 text-sm">{data.get('solusi', {}).get('intro', '')}</p>
                </div>
            </div>
            <div class="max-w-4xl mx-auto py-16 px-6 space-y-6">
                """
    
    # Loop render solutions_list jika ada
    solutions = data.get('solusi', {}).get('solutions_list', [])
    for s_item in solutions:
        html_content += f"""
                <div class="flex gap-4 p-6 bg-white border border-slate-200 rounded-xl shadow-sm">
                    <div class="text-emerald-600 mt-0.5"><i data-lucide="check-circle" class="w-6 h-6"></i></div>
                    <div>
                        <h4 class="text-base font-bold text-slate-900">{s_item.get('target', '')}</h4>
                        <p class="text-slate-600 text-sm mt-1 leading-relaxed">{s_item.get('benefit', '')}</p>
                    </div>
                </div>"""

    html_content += f"""
            </div>
        </section>

        <!-- ================= TAB BLOG ================= -->
        <section id="tab-blog" class="tab-content">
            <div class="max-w-3xl mx-auto py-16 px-6 space-y-8">
                <div class="space-y-4 text-center md:text-left">
                    <span class="text-xs font-bold uppercase tracking-widest text-emerald-600">Artikel Edukasi Terbaru</span>
                    <h2 class="text-3xl md:text-4xl font-extrabold text-slate-900 leading-tight">{data.get('blog', {}).get('title', 'Insights & Perkembangan Teknologi')}</h2>
                    <p class="text-slate-500 italic text-sm">"{data.get('blog', {}).get('excerpt', '')}"</p>
                </div>
                <div class="rounded-2xl overflow-hidden border border-slate-200 shadow-sm">
                    <img src="{get_asset_url('blog', 'stock')}" class="w-full h-64 object-cover" onerror="this.src='https://images.unsplash.com/photo-1550751827-4bd374c3f58b?w=800'">
                </div>
                <div class="prose prose-slate max-w-none text-slate-600 leading-relaxed space-y-4 text-sm md:text-base">
                    """
    
    # Render konten paragraf blog
    blog_content = data.get('blog', {}).get('content', '')
    if blog_content:
        paragraphs = blog_content.split("\n\n")
        for p in paragraphs:
            if p.strip():
                html_content += f"<p>{p.strip()}</p>"
    else:
        html_content += "<p>Konten artikel belum di-generate.</p>"

    html_content += f"""
                </div>
            </div>
        </section>

        <!-- ================= TAB CONTACT ================= -->
        <section id="tab-contact" class="tab-content">
            <div class="max-w-5xl mx-auto py-16 px-6 grid grid-cols-1 md:grid-cols-12 gap-8 items-start">
                <div class="md:col-span-5 space-y-4">
                    <h2 class="text-3xl font-extrabold text-slate-900">{data.get('contact', {}).get('title', 'Hubungi Kami')}</h2>
                    <h3 class="text-lg font-semibold text-emerald-700">{data.get('contact', {}).get('headline', '')}</h3>
                    <p class="text-slate-600 text-sm leading-relaxed">{data.get('contact', {}).get('cta_text', '')}</p>
                </div>
                <div class="md:col-span-7 bg-white border border-slate-200 rounded-2xl p-6 shadow-sm space-y-4">
                    <div class="border-2 dashed border-slate-200 bg-slate-50 rounded-xl p-8 text-center text-slate-400 text-sm">
                        <i data-lucide="form-input" class="w-8 h-8 mx-auto mb-2 text-slate-300"></i>
                        [ Formulir Kontak Terintegrasi Hubungi Kami iLogo ]
                    </div>
                </div>
            </div>
        </section>

    </main>

    <!-- Standard Footer Injection -->
    <footer class="bg-slate-900 text-slate-400 text-xs py-8 px-6 border-t border-slate-800 text-center mt-auto">
        <div class="max-w-7xl mx-auto space-y-2">
            <p>{data.get('home', {}).get('standard_footer', '© 2026 PT. iLogo Infralogy Indonesia. All Rights Reserved.')}</p>
            <p class="text-slate-600 text-[10px]">Generated dynamically via iAAWG Local Prototype Mode.</p>
        </div>
    </footer>

    <script>
        function switchTab(tabId) {{
            // Sembunyikan semua tab
            document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
            // Tampilkan tab target
            document.getElementById('tab-' + tabId).classList.add('active');
            
            // Atur gaya tombol aktif
            document.querySelectorAll('.tab-btn').forEach(btn => {{
                btn.classList.remove('bg-white', 'text-emerald-700', 'shadow-sm');
                btn.classList.add('text-slate-600');
            }});
            
            const activeBtn = document.getElementById('btn-' + tabId);
            activeBtn.classList.remove('text-slate-600');
            activeBtn.classList.add('bg-white', 'text-emerald-700', 'shadow-sm');
            
            window.scrollTo({{ top: 0, behavior: 'smooth' }});
        }}
        // Inisialisasi ikon Lucide
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
        
        # 1. Lewati string kosong atau whitespace saja agar tidak mengotori konsol
        if not clean_text:
            return
            
        # 2. Tangkap metrik token secara diam-diam (Back-end data)
        if "[TOKEN_USAGE]" in clean_text:
            try:
                parts = clean_text.split("|")
                p_val = int(parts[0].split(":")[1].strip())
                c_val = int(parts[1].split(":")[1].strip())
                total_prompt_tokens += p_val
                total_completion_tokens += c_val
            except Exception:
                pass
            # Sembunyikan pesan token mentah ini dari konsol utama agar user tidak pusing melihat angka teknis
            return 

        # 3. Format pesan yang lolos sensor agar seragam dan memiliki ruang spasi
        process_logs.append(clean_text)
        
        # Logika pembacaan progress bar
        upper_text = clean_text.upper()
        if "MEMPROSES" in upper_text and "ASET VISUAL" in upper_text:
            if "HOME" in upper_text: current_progress = 20
            elif "PRODUK" in upper_text: current_progress = 40
            elif "SOLUSI" in upper_text: current_progress = 60
            elif "CONTACT" in upper_text: current_progress = 80
            elif "BLOG" in upper_text: current_progress = 95
        elif "SELURUH PIPELINE" in upper_text and "BERHASIL SELESAI!" in upper_text:
            current_progress = 100

    def flush(self):
        pass


async def pipeline_wrapper(brand: str, url: str, skip_generation: bool, custom_creds: dict, skip_deploy: bool):
    global is_running, process_logs, current_progress, current_brand, total_prompt_tokens, total_completion_tokens, current_task
    
    # Ambil referensi task yang sedang berjalan saat ini
    current_task = asyncio.current_task()
    
    is_running = True
    current_progress = 5
    current_brand = brand
    total_prompt_tokens = 0      # Reset token
    total_completion_tokens = 0  # Reset token
    process_logs.clear()
    
    old_stdout = sys.stdout
    sys.stdout = LogCaptureStream()
    
    try:
        await run_pipeline(brand, url, skip_generation, custom_creds, skip_deploy=skip_deploy)
        # Kompilasi HTML Preview setelah seluruh pipeline selesai berjalan
        generate_local_preview_html(brand)
        current_progress = 100
    except asyncio.CancelledError:
        # Menangkap sinyal pembatalan / stop dari operator
        process_logs.append("[X] Proses dihentikan paksa oleh operator (Aborted).")
        current_progress = 0
    except Exception as e:
        process_logs.append(f"[ERROR] Terjadi kegagalan sistem: {str(e)}")
        if current_progress == 100:
            current_progress = 99
    finally:
        sys.stdout = old_stdout
        is_running = False
        current_task = None  # Reset referensi task


@app.get("/", response_class=HTMLResponse)
async def index_page():
    html_content = """<!DOCTYPE html>
<html lang="id">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>iLogo AI Auto Website Generator</title>
    <!-- Tailwind CSS & Google Fonts -->
    <script src="https://cdn.tailwindcss.com"></script>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
    <!-- Lucide Icons -->
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

    <!-- Header Utama -->
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

    <!-- Main Content -->
    <main class="max-w-7xl mx-auto p-6 grid grid-cols-1 lg:grid-cols-12 gap-6">
        
        <!-- Kiri: Form Input -->
        <form id="generatorForm" onsubmit="startGeneration(event)" class="lg:col-span-5 space-y-5">
            
            <!-- Input Brand & URL -->
            <div class="bg-white border border-slate-200 rounded-xl p-5 space-y-4 shadow-sm">
                <div class="space-y-1.5">
                    <label for="brand" class="text-xs font-semibold text-slate-700">Nama Brand:</label>
                    <input type="text" id="brand" name="brand" placeholder="Contoh: zecurion" required class="w-full bg-slate-50 border border-slate-200 rounded-lg px-3 py-2 text-sm text-slate-900 placeholder-slate-400 focus:outline-none focus:border-ilogo-green focus:bg-white transition-all">
                </div>
                <div class="space-y-1.5">
                    <label for="url" class="text-xs font-semibold text-slate-700">URL Referensi Brand:</label>
                    <input type="text" id="url" name="url" placeholder="Contoh: zecurion.com" class="w-full bg-slate-50 border border-slate-200 rounded-lg px-3 py-2 text-sm text-slate-900 placeholder-slate-400 focus:outline-none focus:border-ilogo-green focus:bg-white transition-all">
                </div>
            </div>

            <!-- Mode Pilihan Eksekusi -->
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

            <!-- Kredensial Fleksibel WordPress Target -->
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

            <!-- Tombol Submit & Stop Tanpa Ikon Sekalian -->
            <div class="flex gap-3">
                <button type="submit" id="submitBtn" class="flex-grow bg-slate-900 hover:bg-slate-800 text-white text-sm font-semibold py-3 px-4 rounded-xl shadow-md transition-all flex items-center justify-center">
                    <span>Mulai Proses Otomatisasi</span>
                </button>
    
                <button type="button" id="stopBtn" onclick="stopGeneration()" class="hidden bg-rose-600 hover:bg-rose-700 text-white text-sm font-semibold py-3 px-4 rounded-xl shadow-md transition-all flex items-center justify-center">
                    <span>Stop</span>
                </button>
            </div>
        </form>

        <!-- Kanan: Monitor Progress & Konsol Log -->
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

                <!-- Progress Bar Section -->
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

                <!-- Logger Terminal Output -->
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

            // Reset UI State
            document.getElementById('submitBtn').disabled = true;
            document.getElementById('submitBtn').classList.add('opacity-50');
            
            // Memunculkan tombol Stop saat proses berjalan
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

                // Render Logs dengan Tampilan ala Timeline yang Lebih Rapi
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

                // Update Progress Bar & Token
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
            
            // Menyembunyikan kembali tombol stop
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
    wp_app_password: str = Form("")
):
    global is_running
    if is_running:
        return JSONResponse(status_code=400, content={"detail": "Proses pipeline lain saat ini sedang berjalan."})

    if not skip_generation and not url:
        return JSONResponse(status_code=400, content={"detail": "URL Referensi Brand wajib diisi jika Skip Generation tidak dicentang."})

    custom_creds = None
    if not skip_deploy and wp_url and wp_username and wp_app_password:
        custom_creds = {
            "wp_url": wp_url,
            "wp_username": wp_username,
            "wp_app_password": wp_app_password
        }

    background_tasks.add_task(pipeline_wrapper, brand, url, skip_generation, custom_creds, skip_deploy)
    return {"status": "started"}


# --- ENDPOINT BARU UNTUK STOP PROSES ---
@app.post("/stop")
async def stop_generation_endpoint():
    global current_task, is_running
    if not is_running or not current_task:
        return JSONResponse(status_code=400, content={"detail": "Tidak ada proses aktif yang sedang berjalan."})
    
    # Memicu batalkan tugas (asyncio.CancelledError) pada pipeline_wrapper
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