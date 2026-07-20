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
from visual.preview_templates import generate_preview_html
from db.settings_store import (
    init_db, get_all_settings, set_setting, delete_setting,
    mask_value, SETTINGS_KEYS, SECRET_KEYS,
)
from config.settings import settings as _env_settings


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

MAX_PRODUCTS = 5  # Harus sama dengan konstanta di main.py

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

    # Render HTML menggunakan multi-template engine
    html_content = generate_preview_html(
        brand=brand,
        data=data,
        primary_color=primary_color,
        max_products=MAX_PRODUCTS,
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
        elif "MEMPROSES URL PRODUK" in upper_text:
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
        elif "MENDEPLOY HALAMAN INDUK: PRODUK" in upper_text:
            current_progress = 89
        elif "MENDEPLOY PRODUK:" in upper_text:
            if current_progress < 98:
                current_progress = min(current_progress + 3, 98)

        # === Done ===
        elif "SELURUH PIPELINE" in upper_text and "BERHASIL SELESAI!" in upper_text:
            current_progress = 100

    def flush(self):
        pass


async def pipeline_wrapper(brand: str, url: str, skip_generation: bool, custom_creds: dict, skip_deploy: bool, product_urls: list, llm_provider: str, primary_color: str, template_name: str = ""):
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
        await run_pipeline(brand, url, skip_generation, custom_creds, skip_deploy=skip_deploy, product_urls=product_urls, llm_provider=llm_provider, primary_color=primary_color, template_name=template_name)
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
    html_content = """<!DOCTYPE html>
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

        // ============================================================
        // TEMPLATE PICKER — visual radio button kustom
        // ============================================================
        document.addEventListener('DOMContentLoaded', function() {
            const options = document.querySelectorAll('.template-option');
            options.forEach(label => {
                label.addEventListener('click', function() {
                    // Reset semua opsi ke state default
                    options.forEach(opt => {
                        opt.classList.remove('border-ilogo-green', 'bg-emerald-50', 'bg-slate-50');
                        opt.classList.add('border-slate-200', 'bg-white');
                    });
                    // Aktifkan opsi yang diklik
                    this.classList.remove('border-slate-200', 'bg-white');
                    this.classList.add('border-ilogo-green', 'bg-emerald-50');
                    // Centang radio input yang tersembunyi
                    this.querySelector('input[type="radio"]').checked = true;
                });
            });
        });

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


# ─── Settings page ──────────────────────────────────────────────────────────

_SETTINGS_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>iAAWG — API Settings</title>
  <link rel="icon" type="image/png"
    href="https://img.icons8.com/?size=100&id=e5sopTWYpy6o&format=png&color=000000">
  <script src="https://cdn.tailwindcss.com"></script>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
  <script src="https://unpkg.com/lucide@latest"></script>
  <style>
    body { font-family: 'Inter', sans-serif; }
    .mono { font-family: 'JetBrains Mono', monospace; }
    input:focus { outline: none; }
    .fade-in { animation: fadeIn .25s ease; }
    @keyframes fadeIn { from { opacity:0; transform:translateY(4px); } to { opacity:1; transform:translateY(0); } }
  </style>
</head>
<body class="min-h-screen bg-slate-950 text-slate-100">
<header class="sticky top-0 z-20 border-b border-slate-800 bg-slate-950/90 backdrop-blur">
  <div class="max-w-3xl mx-auto px-5 py-4 flex items-center justify-between">
    <div class="flex items-center gap-3">
      <a href="/" class="flex items-center gap-1.5 text-slate-400 hover:text-white transition-colors text-sm">
        <i data-lucide="arrow-left" class="w-4 h-4"></i> Back
      </a>
      <span class="text-slate-600">|</span>
      <span class="flex items-center gap-2 font-semibold text-white">
        <i data-lucide="key-round" class="w-4 h-4 text-green-400"></i>
        API Settings
      </span>
    </div>
    <span class="mono text-xs text-slate-600">iAAWG</span>
  </div>
</header>
<main class="max-w-3xl mx-auto px-5 py-8 space-y-6">
  <div class="flex gap-3 bg-blue-950/60 border border-blue-800/50 rounded-xl p-4 text-sm text-blue-300">
    <i data-lucide="info" class="w-4 h-4 flex-shrink-0 mt-0.5 text-blue-400"></i>
    <div>
      Values saved here are stored in <span class="mono bg-slate-900 px-1.5 py-0.5 rounded text-blue-200">iaawg_settings.db</span>
      and take <strong>priority over your .env file</strong>.
      Leave a field blank and click Save to remove the DB override and fall back to .env.
    </div>
  </div>
  <div id="form-root" class="space-y-6">
    <div class="space-y-3">
      <div class="h-4 w-28 bg-slate-800 rounded animate-pulse"></div>
      <div class="h-20 bg-slate-800/60 rounded-xl animate-pulse"></div>
    </div>
  </div>
  <div class="flex items-center gap-4 pt-2">
    <button id="btn-save" onclick="saveAll()"
      class="flex items-center gap-2 px-5 py-2.5 bg-green-600 hover:bg-green-500 active:bg-green-700 text-white font-medium rounded-lg transition-colors text-sm">
      <i data-lucide="save" class="w-4 h-4"></i> Save All
    </button>
    <span id="save-msg" class="text-sm transition-opacity opacity-0"></span>
  </div>
</main>
<script>
const FIELDS = {
  "LLM Providers": [
    { key: "GROQ_API_KEY",      label: "Groq API Key",          placeholder: "gsk_...",                  secret: true },
    { key: "CEREBRAS_API_KEY",  label: "Cerebras API Key",      placeholder: "csk-...",                  secret: true },
    { key: "GITHUB_TOKEN",      label: "GitHub Token (Models)", placeholder: "ghp_...",                  secret: true },
  ],
  "Visual APIs": [
    { key: "UNSPLASH_API_KEY",  label: "Unsplash Access Key",   placeholder: "your key...",              secret: true },
  ],
  "Model Defaults": [
    { key: "DEFAULT_LLM_PROVIDER", label: "LLM Provider Chain",  placeholder: "groq,cerebras,github",   secret: false },
    { key: "DEFAULT_MODEL",        label: "Groq Default Model",  placeholder: "llama-3.1-8b-instant",   secret: false },
    { key: "CEREBRAS_MODEL",       label: "Cerebras Model",      placeholder: "gemma-4-31b",             secret: false },
    { key: "GITHUB_MODEL",         label: "GitHub Model",        placeholder: "gpt-4o-mini",             secret: false },
  ],
};
let serverState = {};
async function load() {
  try {
    const resp = await fetch('/api/settings');
    serverState = await resp.json();
    render();
  } catch (e) {
    document.getElementById('form-root').innerHTML = '<p class="text-red-400 text-sm">Failed to load: ' + e + '</p>';
  }
}
function sourceBadge(source) {
  if (source === 'db')  return '<span class="text-xs font-medium px-2 py-0.5 rounded-full bg-green-500/15 text-green-400 border border-green-500/25">DB</span>';
  if (source === 'env') return '<span class="text-xs font-medium px-2 py-0.5 rounded-full bg-blue-500/15 text-blue-400 border border-blue-500/25">.env</span>';
  return '<span class="text-xs font-medium px-2 py-0.5 rounded-full bg-slate-700 text-slate-500 border border-slate-600">Not set</span>';
}
function render() {
  let html = '';
  for (const [group, fields] of Object.entries(FIELDS)) {
    html += `<div class="fade-in"><h2 class="text-xs font-semibold text-slate-500 uppercase tracking-widest mb-3">${group}</h2><div class="divide-y divide-slate-800 border border-slate-800 rounded-xl overflow-hidden bg-slate-900/50">`;
    for (const f of fields) {
      const s = serverState[f.key] || { source: 'none', is_set: false, display: '' };
      html += `<div class="p-4 space-y-2">
        <div class="flex items-center justify-between">
          <label for="f-${f.key}" class="text-sm font-medium text-slate-200">${f.label}</label>
          <div class="flex items-center gap-2">
            ${sourceBadge(s.source)}
            ${s.source === 'db' ? `<button onclick="clearKey('${f.key}')" class="text-xs text-red-400 hover:text-red-300 transition-colors ml-1">Remove</button>` : ''}
          </div>
        </div>
        ${s.is_set && s.display ? `<div class="mono text-xs text-slate-500">${s.display}</div>` : ''}
        <div class="relative">
          <input id="f-${f.key}" type="${f.secret ? 'password' : 'text'}"
            placeholder="${s.source === 'db' ? 'Enter new value to update, or leave blank' : (s.source === 'env' ? 'Override .env value…' : 'Enter ' + f.placeholder)}"
            class="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2.5 text-sm mono text-slate-100 placeholder-slate-600 focus:border-green-500 transition-colors${f.secret ? ' pr-10' : ''}"/>
          ${f.secret ? `<button type="button" onclick="toggleVis('${f.key}')" class="absolute inset-y-0 right-3 text-slate-500 hover:text-slate-300"><i data-lucide="eye" id="eye-${f.key}" class="w-4 h-4"></i></button>` : ''}
        </div>
      </div>`;
    }
    html += '</div></div>';
  }
  document.getElementById('form-root').innerHTML = html;
  lucide.createIcons();
}
function toggleVis(key) {
  const inp = document.getElementById('f-' + key);
  const icon = document.getElementById('eye-' + key);
  if (inp.type === 'password') { inp.type = 'text'; icon.setAttribute('data-lucide', 'eye-off'); }
  else { inp.type = 'password'; icon.setAttribute('data-lucide', 'eye'); }
  lucide.createIcons();
}
async function clearKey(key) {
  if (!confirm(`Remove "${key}" from the database?\nThe .env value will be used instead.`)) return;
  await fetch('/api/settings', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ [key]: '' }) });
  showMsg('Cleared — refreshing…', 'text-slate-400');
  setTimeout(load, 600);
}
async function saveAll() {
  const payload = {};
  for (const fields of Object.values(FIELDS))
    for (const f of fields) { const el = document.getElementById('f-' + f.key); if (el) payload[f.key] = el.value.trim(); }
  const btn = document.getElementById('btn-save');
  btn.disabled = true; btn.classList.add('opacity-60', 'cursor-not-allowed');
  try {
    const resp = await fetch('/api/settings', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
    if (resp.ok) { showMsg('✓ Saved successfully', 'text-green-400'); setTimeout(load, 700); }
    else showMsg('✗ Save failed', 'text-red-400');
  } catch (e) { showMsg('✗ Network error: ' + e, 'text-red-400'); }
  finally { btn.disabled = false; btn.classList.remove('opacity-60', 'cursor-not-allowed'); }
}
function showMsg(text, cls) {
  const el = document.getElementById('save-msg');
  el.textContent = text; el.className = 'text-sm transition-opacity ' + cls; el.style.opacity = '1';
  setTimeout(() => { el.style.opacity = '0'; }, 3000);
}
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
        if db_value:       source = "db"
        elif env_value:    source = "env"
        else:              source = "none"
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
    # --- Rantai failover LLM ---
    llm_p1: str = Form(...),
    llm_p2: str = Form(""),
    llm_p3: str = Form(""),
    logo_file: UploadFile = File(None),
    # --- Pilihan template pratinjau (opsional, default "auto") ---
    template_name: str = Form("auto")
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
        template_name  # diteruskan ke generate_local_preview_html
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