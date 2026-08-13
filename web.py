import os
import sys
import json
import asyncio
import tempfile
import time as _time
from fastapi import FastAPI, Request, Form, BackgroundTasks, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from main import run_pipeline
from visual.color_extractor import ColorExtractor
from visual.preview_templates import generate_preview_html
from db.settings_store import (
    init_db, get_all_settings, set_setting, delete_setting,
    mask_value, SETTINGS_KEYS, SECRET_KEYS,
)
from config.settings import settings as _env_settings, get_max_products


app = FastAPI(title="iAAWG Web UI")

@app.on_event("startup")
async def _startup():
    """Initialise the SQLite settings DB on first launch."""
    init_db()

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

# Waktu mulai pipeline (epoch float), digunakan untuk menghitung elapsed time & ETA
pipeline_start_time: float | None = None

# Warna default iLogo (fallback jika tidak ada logo)
DEFAULT_PRIMARY_COLOR = "#1E7E34"

def generate_local_preview_html(brand: str, primary_color: str = DEFAULT_PRIMARY_COLOR, template_name: str = ""):
    """
    Membaca data JSON dari output lokal, memilih template yang sesuai, lalu menyusun
    file preview_lokal.html.
    - Jika template_name diisi ("prestige" / "clarity" / "momentum"), template
      tersebut langsung digunakan sesuai pilihan operator.
    - Jika template_name kosong ("" / "auto"), template dipilih otomatis berdasarkan
      karakteristik konten brand (keyword matching).
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
                except Exception:
                    data[p] = {}
        else:
            data[p] = {}

    # Normalisasi: kosong atau "auto" berarti pilih otomatis
    chosen_template = template_name.strip() if template_name and template_name != "auto" else ""

    if chosen_template:
        print(f"[Preview Engine] Template dipilih manual oleh operator: '{chosen_template}'")
    else:
        print("[Preview Engine] Template mode: otomatis (berdasarkan konten brand)")

    # Render HTML menggunakan multi-template engine.
    # max_products is read dynamically so the preview always reflects the
    # current operator-configured limit, not a stale hardcoded constant.
    html_content = generate_preview_html(
        brand=brand,
        data=data,
        primary_color=primary_color,
        max_products=get_max_products(),
        template_name=chosen_template  # "" → auto-select di dalam engine
    )

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

        # === Phase 1: Content Generation (10–35%) ===
        if "MEMPROSES HALAMAN: HOME" in upper_text:
            current_progress = 10
        elif "MEMPROSES HALAMAN: SOLUSI" in upper_text:
            current_progress = 20
        elif "MEMPROSES HALAMAN: CONTACT" in upper_text:
            current_progress = 28
        elif "MEMPROSES URL PRODUK" in upper_text or "MEMPROSES" in upper_text and "KATEGORI" in upper_text:
            current_progress = 32

        # === Phase 2: Visual Generation (40–72%) ===
        elif "MEMPROSES VISUAL UNTUK HALAMAN: HOME" in upper_text:
            current_progress = 40
        elif "MEMPROSES VISUAL UNTUK HALAMAN: SOLUSI" in upper_text:
            current_progress = 50
        elif "MEMPROSES VISUAL UNTUK HALAMAN: CONTACT" in upper_text:
            current_progress = 58
        elif "MEMPROSES VISUAL UNTUK HALAMAN INDUK: PRODUK" in upper_text:
            current_progress = 63
        elif "MEMPROSES VISUAL UNTUK PRODUK:" in upper_text:
            if current_progress < 72:
                current_progress = min(current_progress + 4, 72)

        # === Phase 3: WordPress Deploy (75–98%) ===
        elif "MENDEPLOY HALAMAN: HOME" in upper_text:
            current_progress = 75
        elif "MENDEPLOY HALAMAN: SOLUSI" in upper_text:
            current_progress = 81
        elif "MENDEPLOY HALAMAN: CONTACT" in upper_text:
            current_progress = 86
        elif "MENDEPLOY HALAMAN INDUK: PRODUK" in upper_text or "MENDEPLOY HALAMAN KATALOG OVERVIEW" in upper_text:
            current_progress = 89
        elif "MENDEPLOY PRODUK:" in upper_text or "MENDEPLOY KATALOG:" in upper_text:
            if current_progress < 98:
                current_progress = min(current_progress + 3, 98)

        # === Done ===
        elif "SELURUH PIPELINE" in upper_text and "BERHASIL SELESAI!" in upper_text:
            current_progress = 100

    def flush(self):
        pass


async def pipeline_wrapper(
    brand: str,
    url: str,
    skip_generation: bool,
    custom_creds: dict,
    skip_deploy: bool,
    product_urls: list,
    llm_provider: str,
    primary_color: str,
    template_name: str = "",
    product_mode: str = "individual",
    catalog_groups: list = None,
    homepage_manual_content: str = "",       # ← NEW: bypass scraper untuk homepage
    product_manual_contents: dict = None,    # ← NEW: {url: content} bypass scraper per-URL
):
    global is_running, process_logs, current_progress, current_brand, total_prompt_tokens, total_completion_tokens, current_task, pipeline_start_time
    
    current_task = asyncio.current_task()
    is_running = True
    current_progress = 5
    current_brand = brand
    total_prompt_tokens = 0      
    total_completion_tokens = 0  
    process_logs.clear()
    pipeline_start_time = _time.time()
    
    old_stdout = sys.stdout
    sys.stdout = LogCaptureStream()
    
    try:
        await run_pipeline(
            brand, url, skip_generation, custom_creds,
            skip_deploy=skip_deploy,
            product_urls=product_urls,
            llm_provider=llm_provider,
            primary_color=primary_color,
            template_name=template_name,
            product_mode=product_mode,
            catalog_groups=catalog_groups or [],
            homepage_manual_content=homepage_manual_content,
            product_manual_contents=product_manual_contents or {},
        )
        generate_local_preview_html(brand, primary_color, template_name)
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
    html_content = r"""<!DOCTYPE html>
<html lang="id">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>iLogo AI Auto Website Generator</title>
    <link rel="icon" type="image/png" href="https://img.icons8.com/?size=100&id=e5sopTWYpy6o&format=png&color=000000">
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

            <a href="/settings"
               title="API Settings"
               class="flex items-center gap-1.5 text-slate-400 hover:text-slate-700
                      hover:bg-slate-100 transition-all px-3 py-2 rounded-lg text-sm font-medium">
                <i data-lucide="settings" class="w-4 h-4"></i>
                <span class="hidden sm:inline">Settings</span>
            </a>

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
                    <div class="flex items-center justify-between gap-2">
                        <label for="url" class="text-xs font-semibold text-slate-700">URL Homepage Referensi:</label>
                        <button type="button" onclick="toggleHomepageManual()"
                                id="btnHomepageManual"
                                class="flex items-center gap-1 text-[10px] font-semibold text-slate-500
                                       hover:text-ilogo-green transition-colors group">
                            <i data-lucide="clipboard-paste" class="w-3 h-3"></i>
                            <span id="btnHomepageManualLabel">Bypass Scraper (Paste Manual)</span>
                        </button>
                    </div>
                    <input type="text" id="url" name="url" placeholder="Contoh: zecurion.com" class="w-full bg-slate-50 border border-slate-200 rounded-lg px-3 py-2 text-sm text-slate-900 placeholder-slate-400 focus:outline-none focus:border-ilogo-green focus:bg-white transition-all">

                    <!-- Manual Content panel — Homepage -->
                    <div id="homepageManualPanel" class="hidden pt-2">
                        <div class="border border-amber-200 bg-amber-50/40 rounded-lg p-3 space-y-2">
                            <div class="flex items-start gap-2 text-[11px] text-amber-800">
                                <i data-lucide="shield-alert" class="w-3.5 h-3.5 flex-shrink-0 mt-0.5"></i>
                                <div class="leading-relaxed">
                                    <strong>Mode Manual Homepage aktif.</strong>
                                    Tempelkan konten mentah homepage di sini
                                    (bisa hasil <em>View Source</em> HTML atau teks yang di-copy dari layar).
                                    Sistem akan melewati scraper untuk homepage — berguna jika target diblokir Cloudflare.
                                </div>
                            </div>
                            <textarea id="homepage_manual_content" name="homepage_manual_content" rows="6"
                                      placeholder="Tempel konten homepage di sini... (HTML view-source atau plain text keduanya diterima)"
                                      class="w-full bg-white border border-amber-200 rounded-lg px-3 py-2 text-xs
                                             font-mono text-slate-800 placeholder-slate-400 focus:outline-none
                                             focus:border-amber-400 transition-all resize-y"></textarea>
                            <div class="flex items-center justify-between text-[10px] text-slate-500">
                                <span id="homepageManualCharCount">0 karakter</span>
                                <span class="italic">Minimum 500 karakter bersih agar layak diproses LLM.</span>
                            </div>
                        </div>
                    </div>
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

                <!-- ============================================================ -->
                <!-- URL PRODUK SECTION — Mode picker + input yang sesuai         -->
                <!-- ============================================================ -->
                <div class="space-y-3">
                    <label class="text-xs font-semibold text-slate-700 block">URL Produk (opsional):</label>

                    <!-- Mode Picker -->
                    <div class="grid grid-cols-2 gap-2" id="productModePicker">
                        <label id="mode-label-individual"
                               class="flex items-start gap-2.5 p-3 rounded-lg border-2
                                      border-ilogo-green bg-emerald-50 cursor-pointer
                                      transition-all" data-mode="individual">
                            <input type="radio" name="_product_mode_radio" value="individual" checked class="hidden">
                            <div class="w-7 h-7 rounded-md bg-ilogo-green flex-shrink-0
                                        flex items-center justify-center">
                                <i data-lucide="file-text" class="w-3.5 h-3.5 text-white"></i>
                            </div>
                            <div class="min-w-0">
                                <span class="text-xs font-bold text-slate-800 block">Halaman Individual</span>
                                <span class="text-[10px] text-slate-500">Setiap produk → halaman tersendiri</span>
                            </div>
                        </label>
                        <label id="mode-label-catalog"
                               class="flex items-start gap-2.5 p-3 rounded-lg border-2
                                      border-slate-200 bg-white cursor-pointer
                                      transition-all hover:border-slate-400" data-mode="catalog">
                            <input type="radio" name="_product_mode_radio" value="catalog" class="hidden">
                            <div class="w-7 h-7 rounded-md bg-slate-100 flex-shrink-0
                                        flex items-center justify-center border border-slate-200">
                                <i data-lucide="layout-grid" class="w-3.5 h-3.5 text-slate-600"></i>
                            </div>
                            <div class="min-w-0">
                                <span class="text-xs font-bold text-slate-800 block">Mode Katalog</span>
                                <span class="text-[10px] text-slate-500">Produk dikelompokkan per kategori</span>
                            </div>
                        </label>
                    </div>

                    <!-- Individual Mode: flat textarea -->
                    <div id="individualUrlSection">
                        <textarea id="product_urls_individual" rows="3"
                                  oninput="rebuildIndividualManualPanel()"
                                  class="w-full bg-slate-50 border border-slate-200 rounded-lg px-3 py-2 text-sm
                                         text-slate-900 placeholder-slate-400 focus:outline-none
                                         focus:border-ilogo-green focus:bg-white transition-all"
                                  placeholder="https://zecurion.com/produk-a&#10;https://zecurion.com/produk-b&#10;(satu URL per baris, opsional)"></textarea>
                        <p class="text-[10px] text-slate-400 mt-1">Jika diisi, sistem hanya memproses produk dari URL ini. Jika kosong, produk diekstrak dari homepage.</p>

                        <!-- Per-URL Manual Content Override (Individual Mode) -->
                        <div class="pt-2">
                            <button type="button" onclick="toggleIndividualManualPanel()"
                                    id="btnIndividualManualToggle"
                                    class="flex items-center gap-1.5 text-[11px] font-semibold text-slate-500
                                           hover:text-ilogo-green transition-colors">
                                <i data-lucide="clipboard-paste" class="w-3.5 h-3.5"></i>
                                <span>Bypass Scraper per-URL (Manual Content)</span>
                                <i data-lucide="chevron-down" id="individualManualChevron" class="w-3 h-3 transition-transform"></i>
                            </button>
                            <div id="individualManualPanel" class="hidden mt-2 border border-amber-200 bg-amber-50/40 rounded-lg p-3 space-y-2">
                                <p class="text-[10px] text-amber-800 leading-relaxed">
                                    Tempelkan konten mentah <em>hanya</em> untuk URL yang gagal di-scrape (mis. diblokir Cloudflare).
                                    URL yang dikosongkan tetap di-scrape seperti biasa.
                                </p>
                                <div id="individualManualList" class="space-y-2">
                                    <p class="text-[10px] italic text-slate-400 text-center py-2">
                                        Belum ada URL — isi textarea di atas dulu.
                                    </p>
                                </div>
                            </div>
                        </div>
                    </div>

                    <!-- Catalog Mode: grouped blocks -->
                    <div id="catalogUrlSection" class="hidden space-y-3">
                        <div id="catalogGroups" class="space-y-3">
                            <!-- First group pre-rendered so user isn't greeted with an empty section -->
                            <div class="catalog-group border border-slate-200 rounded-lg p-3 space-y-2 bg-slate-50">
                                <div class="flex items-center gap-2">
                                    <input type="text" placeholder="Nama Kategori (contoh: Router)"
                                           class="catalog-cat-name flex-1 bg-white border border-slate-200 rounded-lg
                                                  px-3 py-2 text-sm text-slate-900 placeholder-slate-400
                                                  focus:outline-none focus:border-ilogo-green transition-all">
                                    <button type="button" onclick="removeCatalogGroup(this)"
                                            class="text-slate-300 hover:text-red-400 transition-colors flex-shrink-0"
                                            title="Hapus kategori ini">
                                        <i data-lucide="trash-2" class="w-4 h-4"></i>
                                    </button>
                                </div>
                                <div class="catalog-urls space-y-1.5">
                                    <div class="catalog-url-row space-y-1.5">
                                        <div class="flex items-center gap-1.5">
                                            <input type="text" placeholder="https://brand.com/produk-a"
                                                   class="catalog-url-input flex-1 bg-white border border-slate-200 rounded-lg
                                                          px-3 py-2 text-sm text-slate-900 placeholder-slate-400
                                                          focus:outline-none focus:border-ilogo-green transition-all">
                                            <button type="button" onclick="toggleCatalogUrlManual(this)"
                                                    class="catalog-manual-toggle text-slate-300 hover:text-amber-500 transition-colors flex-shrink-0"
                                                    title="Bypass scraper — paste konten manual">
                                                <i data-lucide="clipboard-paste" class="w-3.5 h-3.5"></i>
                                            </button>
                                            <button type="button" onclick="removeUrlRow(this)"
                                                    class="text-slate-300 hover:text-red-400 transition-colors flex-shrink-0">
                                                <i data-lucide="x" class="w-3.5 h-3.5"></i>
                                            </button>
                                        </div>
                                        <textarea rows="4"
                                                  placeholder="Tempel konten mentah URL ini (HTML view-source atau plain text). Kosongkan untuk tetap gunakan scraper."
                                                  class="catalog-url-manual hidden w-full bg-amber-50/40 border border-amber-200 rounded-lg
                                                         px-3 py-2 text-[11px] font-mono text-slate-800 placeholder-slate-400
                                                         focus:outline-none focus:border-amber-400 transition-all resize-y"></textarea>
                                    </div>
                                </div>
                                <button type="button" onclick="addUrlToGroup(this)"
                                        class="text-[11px] font-medium text-ilogo-green hover:text-green-700
                                               flex items-center gap-1 transition-colors">
                                    <i data-lucide="plus" class="w-3 h-3"></i> Tambah URL
                                </button>
                            </div>
                        </div>
                        <button type="button" onclick="addCatalogGroup()"
                                class="text-xs font-semibold text-ilogo-green hover:text-green-700
                                       flex items-center gap-1.5 transition-colors">
                            <i data-lucide="plus-circle" class="w-4 h-4"></i> Tambah Kategori
                        </button>
                        <p class="text-[10px] text-slate-400">Setiap kategori menghasilkan satu halaman WordPress. Nama kategori yang Anda tulis di sini menjadi nama halaman katalognya.</p>
                    </div>

                    <!-- Hidden fields submitted to backend -->
                    <input type="hidden" name="product_mode"      id="product_mode_hidden"      value="individual">
                    <input type="hidden" name="product_urls"      id="product_urls_hidden"      value="">
                    <input type="hidden" name="catalog_groups_json" id="catalog_groups_json_hidden" value="">
                </div>
                <!-- ============================================================ -->

                <div class="space-y-1.5">
                    <label for="logo_file" class="text-xs font-semibold text-slate-700">Upload Logo Brand (opsional):</label>
                    <input type="file" id="logo_file" name="logo_file" accept="image/*" class="w-full text-sm text-slate-500 file:mr-4 file:py-2 file:px-4 file:rounded-full file:border-0 file:text-sm file:font-semibold file:bg-ilogo-green file:text-white hover:file:bg-ilogo-green/80 transition-all">
                    <p class="text-[10px] text-slate-400">Jika tidak diunggah, akan digunakan warna default iLogo (#1E7E34).</p>
                </div>

                <!-- ============================================================ -->
                <!-- TEMPLATE PRATINJAU PICKER                                      -->
                <!-- ============================================================ -->
                <div class="space-y-2 pt-1">
                    <label class="text-xs font-semibold text-slate-700 block">Template Layout Website:</label>
                    <div class="grid grid-cols-2 gap-2" id="templatePicker">

                        <!-- Auto -->
                        <label class="template-option col-span-2 flex items-center gap-3 p-3 rounded-lg border-2 border-ilogo-green bg-emerald-50 cursor-pointer transition-all" data-value="auto">
                            <input type="radio" name="template_name" value="auto" checked class="hidden">
                            <div class="w-8 h-8 rounded-md bg-ilogo-green flex-shrink-0 flex items-center justify-center">
                                <i data-lucide="sparkles" class="w-4 h-4 text-white"></i>
                            </div>
                            <div class="min-w-0">
                                <span class="text-xs font-bold text-slate-800 block">✨ Otomatis (Rekomendasi)</span>
                                <span class="text-[10px] text-slate-500">Sistem memilih template terbaik berdasarkan konten brand</span>
                            </div>
                        </label>

                        <!-- Prestige -->
                        <label class="template-option flex items-center gap-2.5 p-3 rounded-lg border-2 border-slate-200 bg-white cursor-pointer transition-all hover:border-slate-400" data-value="prestige">
                            <input type="radio" name="template_name" value="prestige" class="hidden">
                            <div class="w-8 h-8 rounded-md bg-slate-100 flex-shrink-0 flex items-center justify-center border border-slate-200">
                                <i data-lucide="shield-check" class="w-4 h-4 text-slate-600"></i>
                            </div>
                            <div class="min-w-0">
                                <span class="text-xs font-bold text-slate-800 block">Prestige</span>
                                <span class="text-[10px] text-slate-400">Cybersecurity &amp; Compliance</span>
                            </div>
                        </label>

                        <!-- Clarity -->
                        <label class="template-option flex items-center gap-2.5 p-3 rounded-lg border-2 border-slate-200 bg-white cursor-pointer transition-all hover:border-slate-400" data-value="clarity">
                            <input type="radio" name="template_name" value="clarity" class="hidden">
                            <div class="w-8 h-8 rounded-md bg-sky-50 flex-shrink-0 flex items-center justify-center border border-sky-100">
                                <i data-lucide="cloud" class="w-4 h-4 text-sky-500"></i>
                            </div>
                            <div class="min-w-0">
                                <span class="text-xs font-bold text-slate-800 block">Clarity</span>
                                <span class="text-[10px] text-slate-400">SaaS, Cloud &amp; ERP</span>
                            </div>
                        </label>

                        <!-- Momentum -->
                        <label class="template-option col-span-2 flex items-center gap-2.5 p-3 rounded-lg border-2 border-slate-200 bg-white cursor-pointer transition-all hover:border-slate-400" data-value="momentum">
                            <input type="radio" name="template_name" value="momentum" class="hidden">
                            <div class="w-8 h-8 rounded-md bg-slate-800 flex-shrink-0 flex items-center justify-center">
                                <i data-lucide="network" class="w-4 h-4 text-white"></i>
                            </div>
                            <div class="min-w-0">
                                <span class="text-xs font-bold text-slate-800 block">Momentum</span>
                                <span class="text-[10px] text-slate-400">Network, SD-WAN &amp; Infrastruktur</span>
                            </div>
                        </label>

                    </div>
                    <p class="text-[10px] text-slate-400">Pilihan ini mempengaruhi tampilan pratinjau lokal <strong>dan</strong> layout halaman yang di-deploy ke WordPress.</p>
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
                        <div class="flex items-center space-x-1.5 bg-slate-100 px-2.5 py-1 rounded-md border border-slate-200">
                            <i data-lucide="timer" class="w-3 h-3 text-slate-400"></i>
                            <span class="text-[10px] font-semibold text-slate-500 uppercase tracking-wider">Elapsed:</span>
                            <span id="uiElapsed" class="text-[11px] font-mono font-bold text-slate-800">—</span>
                        </div>
                        <div class="flex items-center space-x-1.5 bg-slate-100 px-2.5 py-1 rounded-md border border-slate-200" title="Estimasi berdasarkan kecepatan rata-rata. Dapat berubah karena rate limit LLM.">
                            <i data-lucide="clock" class="w-3 h-3 text-amber-400"></i>
                            <span class="text-[10px] font-semibold text-slate-500 uppercase tracking-wider">ETA ±:</span>
                            <span id="uiEta" class="text-[11px] font-mono font-bold text-amber-600">—</span>
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
        const ETA_MIN_PROGRESS = 20; // don't show ETA before this % (too little data)

        function formatDuration(totalSeconds) {
            const s = Math.round(totalSeconds);
            if (s < 60) return s + 'd';
            const m = Math.floor(s / 60);
            const sec = s % 60;
            return sec > 0 ? m + 'm ' + sec + 'd' : m + 'm';
        }

        // ============================================================
        // TEMPLATE PICKER — visual radio button kustom
        // ============================================================
        document.addEventListener('DOMContentLoaded', function() {
            const options = document.querySelectorAll('.template-option');
            options.forEach(label => {
                label.addEventListener('click', function() {
                    options.forEach(opt => {
                        opt.classList.remove('border-ilogo-green', 'bg-emerald-50', 'bg-slate-50');
                        opt.classList.add('border-slate-200', 'bg-white');
                    });
                    this.classList.remove('border-slate-200', 'bg-white');
                    this.classList.add('border-ilogo-green', 'bg-emerald-50');
                    this.querySelector('input[type="radio"]').checked = true;
                });
            });

            // ============================================================
            // PRODUCT MODE PICKER
            // ============================================================
            const modeLabels = document.querySelectorAll('#productModePicker label');

            modeLabels.forEach(label => {
                label.addEventListener('click', function() {
                    const mode = this.dataset.mode;
                    // Visual toggle
                    modeLabels.forEach(l => {
                        l.classList.remove('border-ilogo-green', 'bg-emerald-50');
                        l.classList.add('border-slate-200', 'bg-white');
                    });
                    this.classList.remove('border-slate-200', 'bg-white');
                    this.classList.add('border-ilogo-green', 'bg-emerald-50');
                    this.querySelector('input[type="radio"]').checked = true;

                    // Switch input section
                    switchProductMode(mode);
                });
            });

            lucide.createIcons();

            // Initialize homepage manual content character counter
            initHomepageManualCounter();
        });

        // ============================================================
        // PRODUCT MODE SWITCHING
        // ============================================================
        function switchProductMode(mode) {
            document.getElementById('product_mode_hidden').value = mode;
            const indiv = document.getElementById('individualUrlSection');
            const cat   = document.getElementById('catalogUrlSection');
            if (mode === 'catalog') {
                indiv.classList.add('hidden');
                cat.classList.remove('hidden');
            } else {
                indiv.classList.remove('hidden');
                cat.classList.add('hidden');
            }
        }

        // ============================================================
        // CATALOG GROUP MANAGEMENT
        // ============================================================
        function addCatalogGroup() {
            const container = document.getElementById('catalogGroups');
            const div = document.createElement('div');
            div.className = 'catalog-group border border-slate-200 rounded-lg p-3 space-y-2 bg-slate-50';
            div.innerHTML = `
                <div class="flex items-center gap-2">
                    <input type="text" placeholder="Nama Kategori (contoh: Firewall)"
                           class="catalog-cat-name flex-1 bg-white border border-slate-200 rounded-lg
                                  px-3 py-2 text-sm text-slate-900 placeholder-slate-400
                                  focus:outline-none focus:border-ilogo-green transition-all">
                    <button type="button" onclick="removeCatalogGroup(this)"
                            class="text-slate-300 hover:text-red-400 transition-colors flex-shrink-0"
                            title="Hapus kategori ini">
                        <i data-lucide="trash-2" class="w-4 h-4"></i>
                    </button>
                </div>
                <div class="catalog-urls space-y-1.5">
                    <div class="catalog-url-row space-y-1.5">
                        <div class="flex items-center gap-1.5">
                            <input type="text" placeholder="https://brand.com/produk-x"
                                   class="catalog-url-input flex-1 bg-white border border-slate-200 rounded-lg
                                          px-3 py-2 text-sm text-slate-900 placeholder-slate-400
                                          focus:outline-none focus:border-ilogo-green transition-all">
                            <button type="button" onclick="toggleCatalogUrlManual(this)"
                                    class="catalog-manual-toggle text-slate-300 hover:text-amber-500 transition-colors flex-shrink-0"
                                    title="Bypass scraper — paste konten manual">
                                <i data-lucide="clipboard-paste" class="w-3.5 h-3.5"></i>
                            </button>
                            <button type="button" onclick="removeUrlRow(this)"
                                    class="text-slate-300 hover:text-red-400 transition-colors flex-shrink-0">
                                <i data-lucide="x" class="w-3.5 h-3.5"></i>
                            </button>
                        </div>
                        <textarea rows="4"
                                  placeholder="Tempel konten mentah URL ini (HTML view-source atau plain text). Kosongkan untuk tetap gunakan scraper."
                                  class="catalog-url-manual hidden w-full bg-amber-50/40 border border-amber-200 rounded-lg
                                         px-3 py-2 text-[11px] font-mono text-slate-800 placeholder-slate-400
                                         focus:outline-none focus:border-amber-400 transition-all resize-y"></textarea>
                    </div>
                </div>
                <button type="button" onclick="addUrlToGroup(this)"
                        class="text-[11px] font-medium text-ilogo-green hover:text-green-700
                               flex items-center gap-1 transition-colors">
                    <i data-lucide="plus" class="w-3 h-3"></i> Tambah URL
                </button>
            `;
            container.appendChild(div);
            lucide.createIcons();
        }

        function removeCatalogGroup(btn) {
            const groups = document.querySelectorAll('.catalog-group');
            if (groups.length <= 1) {
                // Keep at least one group; just clear it instead
                const group = btn.closest('.catalog-group');
                group.querySelector('.catalog-cat-name').value = '';
                group.querySelectorAll('.catalog-url-row').forEach((row, i) => {
                    if (i === 0) {
                        row.querySelector('.catalog-url-input').value = '';
                        const ta = row.querySelector('.catalog-url-manual');
                        if (ta) { ta.value = ''; ta.classList.add('hidden'); }
                        const tog = row.querySelector('.catalog-manual-toggle');
                        if (tog) tog.classList.remove('text-amber-500');
                    } else {
                        row.remove();
                    }
                });
                return;
            }
            btn.closest('.catalog-group').remove();
        }

        function addUrlToGroup(btn) {
            const urlsContainer = btn.previousElementSibling; // .catalog-urls div
            const row = document.createElement('div');
            row.className = 'catalog-url-row space-y-1.5';
            row.innerHTML = `
                <div class="flex items-center gap-1.5">
                    <input type="text" placeholder="https://brand.com/produk-lain"
                           class="catalog-url-input flex-1 bg-white border border-slate-200 rounded-lg
                                  px-3 py-2 text-sm text-slate-900 placeholder-slate-400
                                  focus:outline-none focus:border-ilogo-green transition-all">
                    <button type="button" onclick="toggleCatalogUrlManual(this)"
                            class="catalog-manual-toggle text-slate-300 hover:text-amber-500 transition-colors flex-shrink-0"
                            title="Bypass scraper — paste konten manual">
                        <i data-lucide="clipboard-paste" class="w-3.5 h-3.5"></i>
                    </button>
                    <button type="button" onclick="removeUrlRow(this)"
                            class="text-slate-300 hover:text-red-400 transition-colors flex-shrink-0">
                        <i data-lucide="x" class="w-3.5 h-3.5"></i>
                    </button>
                </div>
                <textarea rows="4"
                          placeholder="Tempel konten mentah URL ini (HTML view-source atau plain text). Kosongkan untuk tetap gunakan scraper."
                          class="catalog-url-manual hidden w-full bg-amber-50/40 border border-amber-200 rounded-lg
                                 px-3 py-2 text-[11px] font-mono text-slate-800 placeholder-slate-400
                                 focus:outline-none focus:border-amber-400 transition-all resize-y"></textarea>
            `;
            urlsContainer.appendChild(row);
            lucide.createIcons();
        }

        function removeUrlRow(btn) {
            const row = btn.closest('.catalog-url-row');
            const urlsContainer = row.parentElement;
            if (urlsContainer.querySelectorAll('.catalog-url-row').length > 1) {
                row.remove();
            } else {
                // Last row — just clear the input & manual textarea
                row.querySelector('.catalog-url-input').value = '';
                const ta = row.querySelector('.catalog-url-manual');
                if (ta) { ta.value = ''; ta.classList.add('hidden'); }
                const tog = row.querySelector('.catalog-manual-toggle');
                if (tog) tog.classList.remove('text-amber-500');
            }
        }

        // Toggle inline manual-content textarea for a catalog URL row
        function toggleCatalogUrlManual(btn) {
            const row = btn.closest('.catalog-url-row');
            const ta = row.querySelector('.catalog-url-manual');
            if (!ta) return;
            const opening = ta.classList.contains('hidden');
            ta.classList.toggle('hidden');
            if (opening) {
                btn.classList.add('text-amber-500');
                ta.focus();
            } else if (!ta.value.trim()) {
                // Only reset icon color if the textarea is empty
                btn.classList.remove('text-amber-500');
            }
        }

        function serializeCatalogGroups() {
            const groups = [];
            document.querySelectorAll('.catalog-group').forEach(group => {
                const category = group.querySelector('.catalog-cat-name').value.trim();
                const urls = Array.from(group.querySelectorAll('.catalog-url-input'))
                    .map(inp => inp.value.trim())
                    .filter(u => u.length > 0);
                if (category && urls.length > 0) {
                    groups.push({ category, urls });
                }
            });
            return JSON.stringify(groups);
        }

        // ============================================================
        // MANUAL CONTENT — bypass scraper (per-URL & homepage)
        // ============================================================

        // Persistent in-memory store for Individual Mode manual content.
        // Keyed by URL; survives DOM rebuilds when the operator edits the
        // URL textarea, so pasted content isn't lost mid-edit.
        const individualManualStore = {};

        function toggleHomepageManual() {
            const panel = document.getElementById('homepageManualPanel');
            const btn = document.getElementById('btnHomepageManual');
            const label = document.getElementById('btnHomepageManualLabel');
            const opening = panel.classList.contains('hidden');
            panel.classList.toggle('hidden');
            if (opening) {
                btn.classList.add('text-amber-600');
                label.textContent = 'Sembunyikan Manual Content';
                document.getElementById('homepage_manual_content').focus();
            } else {
                // Only unhighlight if textarea is empty (still active if content pasted)
                const ta = document.getElementById('homepage_manual_content');
                if (!ta.value.trim()) {
                    btn.classList.remove('text-amber-600');
                }
                label.textContent = 'Bypass Scraper (Paste Manual)';
            }
        }

        // Live character counter for homepage manual textarea
        function initHomepageManualCounter() {
            const ta = document.getElementById('homepage_manual_content');
            const counter = document.getElementById('homepageManualCharCount');
            if (!ta || !counter) return;
            const update = () => {
                const n = ta.value.length;
                counter.textContent = n.toLocaleString('id-ID') + ' karakter';
                counter.className = n >= 500
                    ? 'text-emerald-600 font-semibold'
                    : (n > 0 ? 'text-amber-600' : 'text-slate-500');
            };
            ta.addEventListener('input', update);
            update();
        }

        function toggleIndividualManualPanel() {
            const panel = document.getElementById('individualManualPanel');
            const chevron = document.getElementById('individualManualChevron');
            const btn = document.getElementById('btnIndividualManualToggle');
            const opening = panel.classList.contains('hidden');
            panel.classList.toggle('hidden');
            if (opening) {
                chevron.classList.add('rotate-180');
                btn.classList.add('text-amber-600');
                rebuildIndividualManualPanel();
            } else {
                chevron.classList.remove('rotate-180');
                // Keep amber if any URL has manual content
                if (!Object.values(individualManualStore).some(v => (v || '').trim())) {
                    btn.classList.remove('text-amber-600');
                }
            }
        }

        function _getIndividualUrls() {
            const raw = (document.getElementById('product_urls_individual') || {}).value || '';
            return raw.split(/\r?\n/).map(s => s.trim()).filter(Boolean);
        }

        // Rebuild the per-URL manual content list without losing already-pasted values.
        // Called whenever the operator edits the URL textarea.
        function rebuildIndividualManualPanel() {
            const list = document.getElementById('individualManualList');
            const panel = document.getElementById('individualManualPanel');
            if (!list) return;

            // Snapshot current textarea values into the store BEFORE rebuild
            list.querySelectorAll('.indiv-manual-item').forEach(item => {
                const url = item.dataset.url;
                const ta = item.querySelector('textarea');
                if (url && ta) individualManualStore[url] = ta.value;
            });

            const urls = _getIndividualUrls();
            if (urls.length === 0) {
                list.innerHTML = `<p class="text-[10px] italic text-slate-400 text-center py-2">
                                    Belum ada URL — isi textarea di atas dulu.
                                  </p>`;
                return;
            }

            list.innerHTML = urls.map(url => {
                const stored = individualManualStore[url] || '';
                const hasContent = stored.trim().length > 0;
                const safeUrl = url.replace(/"/g, '&quot;');
                return `
                    <div class="indiv-manual-item border border-slate-200 rounded-lg bg-white overflow-hidden"
                         data-url="${safeUrl}">
                        <div class="flex items-center justify-between gap-2 px-2.5 py-1.5 bg-slate-50 border-b border-slate-200">
                            <span class="text-[11px] font-mono text-slate-700 truncate flex-1" title="${safeUrl}">${safeUrl}</span>
                            <span class="text-[10px] font-semibold ${hasContent ? 'text-amber-600' : 'text-slate-400'} flex-shrink-0">
                                ${hasContent ? 'MANUAL' : 'AUTO SCRAPE'}
                            </span>
                        </div>
                        <textarea rows="3"
                                  oninput="_onIndividualManualInput(this)"
                                  placeholder="Tempel konten mentah URL ini. Kosongkan untuk tetap gunakan scraper."
                                  class="w-full bg-white border-0 px-2.5 py-2 text-[11px] font-mono text-slate-800
                                         placeholder-slate-400 focus:outline-none focus:bg-amber-50/30
                                         transition-all resize-y">${stored.replace(/</g, '&lt;')}</textarea>
                    </div>
                `;
            }).join('');
        }

        function _onIndividualManualInput(ta) {
            const item = ta.closest('.indiv-manual-item');
            const url = item.dataset.url;
            individualManualStore[url] = ta.value;
            const badge = item.querySelector('.text-\\[10px\\].font-semibold');
            const hasContent = ta.value.trim().length > 0;
            if (badge) {
                badge.textContent = hasContent ? 'MANUAL' : 'AUTO SCRAPE';
                badge.className = 'text-[10px] font-semibold flex-shrink-0 ' +
                                  (hasContent ? 'text-amber-600' : 'text-slate-400');
            }
            // Reflect state on the toggle button so the operator sees the badge
            const toggleBtn = document.getElementById('btnIndividualManualToggle');
            if (toggleBtn) {
                const anyActive = Object.values(individualManualStore).some(v => (v || '').trim());
                toggleBtn.classList.toggle('text-amber-600', anyActive);
            }
        }

        // Build {url: content} dict for BOTH modes at submit time.
        function serializeProductManualContents() {
            const map = {};
            const mode = document.getElementById('product_mode_hidden').value;

            if (mode === 'catalog') {
                document.querySelectorAll('.catalog-url-row').forEach(row => {
                    const urlInp = row.querySelector('.catalog-url-input');
                    const ta = row.querySelector('.catalog-url-manual');
                    if (!urlInp || !ta) return;
                    const url = urlInp.value.trim();
                    const content = (ta.value || '').trim();
                    if (url && content) map[url] = ta.value;  // preserve original whitespace
                });
            } else {
                // Individual mode — snapshot the live DOM first (in case panel is open)
                document.querySelectorAll('#individualManualList .indiv-manual-item').forEach(item => {
                    const ta = item.querySelector('textarea');
                    if (ta) individualManualStore[item.dataset.url] = ta.value;
                });
                const validUrls = new Set(_getIndividualUrls());
                for (const [url, content] of Object.entries(individualManualStore)) {
                    if (validUrls.has(url) && (content || '').trim()) {
                        map[url] = content;
                    }
                }
            }
            return JSON.stringify(map);
        }

        // ============================================================
        // FORM HELPERS
        // ============================================================
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

            // Resolve mode and serialize the correct URL data before submitting
            const mode = document.getElementById('product_mode_hidden').value;
            formData.set('product_mode', mode);

            if (mode === 'catalog') {
                formData.set('catalog_groups_json', serializeCatalogGroups());
                formData.set('product_urls', '');  // ensure individual textarea is not sent
            } else {
                const indivUrls = document.getElementById('product_urls_individual').value;
                formData.set('product_urls', indivUrls);
                formData.set('catalog_groups_json', '');
            }

            // ── Manual Content Override (bypass scraper) ────────────────
            // Homepage manual content is a normal named textarea, so it's
            // already in formData via the form field itself. We still ensure
            // it's trimmed for clean transport.
            const hpManual = document.getElementById('homepage_manual_content');
            if (hpManual) formData.set('homepage_manual_content', hpManual.value || '');

            // Per-URL manual content — serialized from either mode
            formData.set('product_manual_contents_json', serializeProductManualContents());

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

                // Elapsed time
                if (data.elapsed_seconds != null) {
                    document.getElementById('uiElapsed').innerText = formatDuration(data.elapsed_seconds);
                }

                // ETA via cumulative elapsed ratio: elapsed × (100 − progress) / progress
                const etaEl = document.getElementById('uiEta');
                if (data.is_running && data.progress >= ETA_MIN_PROGRESS && data.progress < 100 && data.elapsed_seconds > 0) {
                    const etaSec = Math.round(data.elapsed_seconds * (100 - data.progress) / data.progress);
                    etaEl.innerText = '~' + formatDuration(etaSec);
                } else if (!data.is_running) {
                    etaEl.innerText = '—';
                }

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
</html>"""
    return HTMLResponse(content=html_content)


# ─── Settings page ───────────────────────────────────────────────────────────

_SETTINGS_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>iAAWG — API Settings</title>
  <link rel="icon" type="image/png"
        href="https://img.icons8.com/?size=100&id=e5sopTWYpy6o&format=png&color=000000">
  <script src="https://cdn.tailwindcss.com"></script>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap"
        rel="stylesheet">
  <script src="https://unpkg.com/lucide@latest"></script>
  <script>
    tailwind.config = { theme: { extend: {
      colors: { 'ilogo-green': '#1E7E34', 'ilogo-orange': '#FF9E1B' },
      fontFamily: { sans: ['Inter','sans-serif'], mono: ['JetBrains Mono','monospace'] }
    }}}
  </script>
  <style>
    body { font-family: 'Inter', sans-serif; }
    .mono { font-family: 'JetBrains Mono', monospace; }
    .fade-in { animation: fadeIn .25s ease; }
    @keyframes fadeIn { from { opacity:0; transform:translateY(4px) } to { opacity:1; transform:none } }
    .fi {
      width:100%; background:#f8fafc; border:1px solid #e2e8f0; border-radius:.5rem;
      padding:.375rem .75rem; font-size:.875rem; color:#0f172a;
      placeholder-color:#94a3b8; transition:all .15s;
    }
    .fi:focus { outline:none; border-color:#1E7E34; background:#fff; }
    .fi-secret { padding-right:2.25rem; }
    .badge { font-size:.75rem; font-weight:500; padding:.125rem .5rem;
             border-radius:9999px; border:1px solid; }
  </style>
</head>
<body class="bg-slate-50 text-slate-800 min-h-screen antialiased">

<header class="border-b border-slate-200 bg-white sticky top-0 z-50 px-6 py-4 shadow-sm">
  <div class="max-w-3xl mx-auto flex items-center justify-between">
    <div class="flex items-center space-x-3">
      <a href="/" class="flex items-center gap-1.5 text-slate-400 hover:text-slate-600 transition-colors text-sm">
        <i data-lucide="arrow-left" class="w-4 h-4"></i><span>Back</span>
      </a>
      <span class="text-slate-300 select-none">|</span>
      <div class="bg-ilogo-green text-white p-2 rounded-lg">
        <i data-lucide="key-round" class="w-5 h-5"></i>
      </div>
      <div>
        <h1 class="text-base font-bold tracking-tight text-slate-950">API Settings</h1>
        <p class="text-xs text-slate-500">Manage your LLM and visual API keys.</p>
      </div>
    </div>
  </div>
</header>

<main class="max-w-3xl mx-auto px-6 py-8 space-y-6">
  <div class="flex items-start gap-3 bg-sky-50 border border-sky-200 rounded-xl px-4 py-3 text-sm text-sky-800">
    <i data-lucide="info" class="w-4 h-4 flex-shrink-0 mt-0.5 text-sky-500"></i>
    <div class="leading-relaxed">
      Values saved here are stored in
      <span class="mono bg-slate-100 border border-slate-200 px-1.5 py-0.5 rounded text-slate-700 text-xs">iaawg_settings.db</span>
      and take <strong>priority over your .env file</strong>.
      Leave a field blank and click Save to remove the DB override and fall back to .env.
    </div>
  </div>

  <div id="form-root" class="space-y-6">
    <div class="h-24 bg-slate-100 rounded-xl animate-pulse"></div>
    <div class="h-16 bg-slate-100 rounded-xl animate-pulse"></div>
  </div>

  <div class="flex items-center gap-4 pt-1 pb-4">
    <button id="btn-save" onclick="saveAll()"
      class="flex items-center gap-2 px-5 py-2.5 bg-ilogo-green hover:bg-green-700
             active:bg-green-800 text-white font-semibold rounded-lg transition-colors text-sm shadow-sm">
      <i data-lucide="save" class="w-4 h-4"></i>Save all
    </button>
    <span id="save-msg" class="text-sm font-medium transition-opacity opacity-0"></span>
  </div>
</main>

<script>
const FIELDS = {
  "LLM Providers": [
    { key: "GROQ_API_KEY",         label: "Groq API Key",           placeholder: "gsk_...",                 secret: true  },
    { key: "CEREBRAS_API_KEY",     label: "Cerebras API Key",       placeholder: "csk-...",                 secret: true  },
    { key: "GITHUB_TOKEN",         label: "GitHub Token (Models)",  placeholder: "ghp_...",                 secret: true  },
  ],
  "Visual APIs": [
    { key: "UNSPLASH_API_KEY",     label: "Unsplash Access Key",    placeholder: "your key...",             secret: true  },
  ],
  "Model Defaults": [
    { key: "DEFAULT_LLM_PROVIDER", label: "LLM Provider Chain",     placeholder: "groq,cerebras,github",    secret: false },
    { key: "DEFAULT_MODEL",        label: "Groq Default Model",     placeholder: "llama-3.1-8b-instant",    secret: false },
    { key: "CEREBRAS_MODEL",       label: "Cerebras Model",         placeholder: "gemma-4-31b",             secret: false },
    { key: "GITHUB_MODEL",         label: "GitHub Model",           placeholder: "gpt-4o-mini",             secret: false },
  ],
  "Pipeline Limits": [
    { key: "MAX_PRODUCTS",         label: "Max Products per Brand", placeholder: "Default: 5 — Maximum: 10", secret: false },
  ],
};

let serverState = {};

function badge(source) {
  const cfg = {
    db:   ['DB',      'bg-emerald-50 text-emerald-700 border-emerald-200'],
    env:  ['.env',    'bg-sky-50 text-sky-700 border-sky-200'],
    none: ['Not set', 'bg-slate-100 text-slate-400 border-slate-200'],
  };
  const [label, cls] = cfg[source] || cfg.none;
  return `<span class="badge ${cls}">${label}</span>`;
}

function sourceLine(s, key) {
  if (!s.is_set) return `<div class="mb-2">${badge(s.source)}</div>`;
  const clearBtn = s.source === 'db'
    ? `<button onclick="clearKey('${key}')" class="text-xs text-rose-400 hover:text-rose-600 ml-auto">Clear</button>`
    : '';
  return `<div class="flex items-center gap-2 mb-2">
    <span class="mono text-xs text-slate-500 bg-slate-50 border border-slate-200 px-2 py-1 rounded">${s.display}</span>
    ${badge(s.source)}${clearBtn}</div>`;
}

function render() {
  let html = '';
  for (const [group, fields] of Object.entries(FIELDS)) {
    html += `<div class="fade-in bg-white border border-slate-200 rounded-xl shadow-sm overflow-hidden">
      <div class="px-5 py-3 border-b border-slate-100 bg-slate-50">
        <h2 class="text-xs font-semibold text-slate-500 uppercase tracking-widest">${group}</h2>
      </div>
      <div class="divide-y divide-slate-100">`;

    for (const f of fields) {
      const s = serverState[f.key] || { source: 'none', is_set: false, display: '' };
      const ph = s.source === 'db'  ? 'Enter new value to update, or leave blank to keep'
               : s.source === 'env' ? 'Override .env value\u2026'
               : `Enter ${f.placeholder}`;
      const eye = f.secret
        ? `<button type="button" onclick="toggleVis('f-${f.key}','eye-${f.key}')"
                   class="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600">
             <i id="eye-${f.key}" data-lucide="eye" class="w-4 h-4"></i></button>`
        : '';
      html += `<div class="px-5 py-4">
        <label for="f-${f.key}" class="text-sm font-medium text-slate-700 block mb-1.5">${f.label}</label>
        ${sourceLine(s, f.key)}
        <div class="relative">
          <input id="f-${f.key}" type="${f.secret ? 'password' : 'text'}" placeholder="${ph}"
                 class="fi${f.secret ? ' fi-secret' : ''}">${eye}
        </div></div>`;
    }
    html += `</div></div>`;
  }
  document.getElementById('form-root').innerHTML = html;
  lucide.createIcons();
}

async function load() {
  try {
    serverState = await (await fetch('/api/settings')).json();
    render();
  } catch (e) {
    document.getElementById('form-root').innerHTML =
      `<p class="text-red-500 text-sm">Failed to load settings: ${e}</p>`;
  }
}

function toggleVis(inputId, iconId) {
  const inp = document.getElementById(inputId);
  const isPass = inp.type === 'password';
  inp.type = isPass ? 'text' : 'password';
  document.getElementById(iconId).setAttribute('data-lucide', isPass ? 'eye-off' : 'eye');
  lucide.createIcons();
}

async function clearKey(key) {
  if (!confirm(`Remove "${key}" from the database?\\nThe .env value will be used instead.`)) return;
  await fetch('/api/settings', {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({[key]: ''}),
  });
  showMsg('Cleared \u2014 refreshing\u2026', 'text-slate-400');
  setTimeout(load, 600);
}

async function saveAll() {
  const payload = {};
  for (const fields of Object.values(FIELDS))
    for (const f of fields) {
      const el = document.getElementById('f-' + f.key);
      if (el) payload[f.key] = el.value.trim();
    }
  const btn = document.getElementById('btn-save');
  btn.disabled = true;
  btn.classList.add('opacity-60', 'cursor-not-allowed');
  try {
    const ok = (await fetch('/api/settings', {
      method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload),
    })).ok;
    showMsg(ok ? '\u2713 Saved successfully' : '\u2717 Save failed', ok ? 'text-emerald-600' : 'text-red-500');
    if (ok) setTimeout(load, 700);
  } catch (e) {
    showMsg('\u2717 Network error: ' + e, 'text-red-500');
  } finally {
    btn.disabled = false;
    btn.classList.remove('opacity-60', 'cursor-not-allowed');
  }
}

function showMsg(text, cls) {
  const el = document.getElementById('save-msg');
  el.textContent = text;
  el.className = `text-sm font-medium transition-opacity ${cls}`;
  el.style.opacity = '1';
  setTimeout(() => el.style.opacity = '0', 3000);
}

lucide.createIcons();
load();
</script>
</body>
</html>"""


@app.get("/settings", response_class=HTMLResponse)
async def settings_page():
    return HTMLResponse(content=_SETTINGS_HTML)


@app.get("/api/settings")
async def api_get_settings():
    db_vals = get_all_settings()
    result = {}
    for key in SETTINGS_KEYS:
        db_value  = db_vals.get(key, "")
        env_value = getattr(_env_settings, key, "")
        effective = db_value or env_value
        if db_value:    source = "db"
        elif env_value: source = "env"
        else:           source = "none"
        result[key] = {
            "source":  source,
            "is_set":  bool(effective),
            "display": mask_value(effective) if key in SECRET_KEYS else effective,
        }
    return result


@app.post("/api/settings")
async def api_save_settings(request: Request):
    try:
        body: dict = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"detail": "Invalid JSON body."})
    saved, cleared = [], []
    for key in SETTINGS_KEYS:
        if key not in body:
            continue
        value = str(body[key]).strip()
        if value:
            set_setting(key, value)
            saved.append(key)
        else:
            delete_setting(key)
            cleared.append(key)
    return {"status": "ok", "saved": saved, "cleared": cleared}

# ─── End settings page ───────────────────────────────────────────────────────


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
    catalog_groups_json: str = Form(""),   # JSON string for catalog mode
    # --- Rantai failover LLM ---
    llm_p1: str = Form(...),
    llm_p2: str = Form(""),
    llm_p3: str = Form(""),
    logo_file: UploadFile = File(None),
    # --- Pilihan template pratinjau (opsional, default "auto") ---
    template_name: str = Form("auto"),
    product_mode: str = Form("individual"),
    # --- Manual Content Override (bypass scraper) ---
    homepage_manual_content: str = Form(""),         # ← NEW
    product_manual_contents_json: str = Form(""),    # ← NEW: JSON {url: content}
):
    global is_running
    if is_running:
        return JSONResponse(status_code=400, content={"detail": "Proses pipeline lain saat ini sedang berjalan."})

    brand = brand.strip()
    url = url.strip()
    homepage_manual_content = (homepage_manual_content or "").strip()
    # URL bebas kosong jika (a) skip_generation aktif, atau (b) operator sudah
    # menyediakan Manual Content untuk homepage (bypass scraper).
    if not skip_generation and not url and not homepage_manual_content:
        return JSONResponse(status_code=400, content={
            "detail": "URL Homepage Referensi wajib diisi, kecuali Anda mengaktifkan Skip Generation atau menempelkan Manual Content untuk homepage."
        })

    # Ekstrak warna dari logo jika diunggah
    primary_color = DEFAULT_PRIMARY_COLOR
    if logo_file and logo_file.filename:
        suffix = os.path.splitext(logo_file.filename)[1] or ".png"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            content = await logo_file.read()
            tmp.write(content)
            tmp_path = tmp.name
        try:
            palette = ColorExtractor.extract_palette(tmp_path, color_count=3)
            if palette:
                primary_color = palette[0]
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

    # Parse product input based on mode
    product_urls_list = []
    catalog_groups_list = []

    if product_mode == "catalog" and catalog_groups_json.strip():
        # Catalog mode: parse grouped JSON
        try:
            catalog_groups_list = json.loads(catalog_groups_json)
            if not isinstance(catalog_groups_list, list):
                raise ValueError("Bukan list")
        except Exception:
            return JSONResponse(status_code=400, content={"detail": "Format catalog groups tidak valid. Pastikan JSON dikirim dengan benar."})
    elif product_urls.strip():
        # Individual mode: flat newline-separated URLs
        product_urls_list = [u.strip() for u in product_urls.splitlines() if u.strip()]

    # ── Parse Manual Content Override (per-URL) ──────────────────────────────
    # Frontend serialisasi objek {url: raw_content} dan mengirim sebagai JSON
    # string. Empty string di sini berarti operator tidak mengaktifkan bypass
    # untuk URL manapun.
    product_manual_contents_map = {}
    if product_manual_contents_json.strip():
        try:
            parsed = json.loads(product_manual_contents_json)
            if not isinstance(parsed, dict):
                raise ValueError("Bukan dict")
            # Hanya simpan entry yang benar-benar berisi konten (non-empty)
            for k, v in parsed.items():
                if isinstance(k, str) and isinstance(v, str) and v.strip():
                    product_manual_contents_map[k.strip()] = v
        except Exception:
            return JSONResponse(status_code=400, content={
                "detail": "Format Manual Content Produk tidak valid. Pastikan JSON dikirim dengan benar."
            })

    # --- Logika penyusunan rantai failover dinamis ---
    selected_providers = []
    for p in [llm_p1, llm_p2, llm_p3]:
        if p and p not in selected_providers:
            selected_providers.append(p)
            
    dynamic_provider_chain = ",".join(selected_providers) if selected_providers else "groq"

    background_tasks.add_task(
        pipeline_wrapper,
        brand,
        url,
        skip_generation,
        custom_creds,
        skip_deploy,
        product_urls_list,
        dynamic_provider_chain,
        primary_color,
        template_name,
        product_mode,
        catalog_groups_list,
        homepage_manual_content,
        product_manual_contents_map,
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
    global process_logs, is_running, current_progress, current_brand, total_prompt_tokens, total_completion_tokens, pipeline_start_time
    elapsed = int(_time.time() - pipeline_start_time) if pipeline_start_time is not None else 0
    return {
        "is_running": is_running,
        "progress": current_progress,
        "logs": process_logs,
        "brand": current_brand,
        "prompt_tokens": total_prompt_tokens,
        "completion_tokens": total_completion_tokens,
        "elapsed_seconds": elapsed
    }