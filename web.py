import os
import sys
from fastapi import FastAPI, Request, Form, BackgroundTasks
from fastapi.responses import HTMLResponse, JSONResponse
from main import run_pipeline

app = FastAPI(title="iAAWG Web UI")

process_logs = []
is_running = False
current_progress = 0

class LogCaptureStream:
    """Helper untuk menangkap print statement dan memperbarui progress bar secara presisi"""
    def write(self, text):
        global current_progress
        clean_text = text.strip()
        if clean_text:
            process_logs.append(clean_text)
            
            upper_text = clean_text.upper()
            
            if "MEMPROSES" in upper_text and "ASET VISUAL" in upper_text:
                if "HOME" in upper_text:
                    current_progress = 20
                elif "PRODUK" in upper_text:
                    current_progress = 40
                elif "SOLUSI" in upper_text:
                    current_progress = 60
                elif "CONTACT" in upper_text:
                    current_progress = 80
                elif "BLOG" in upper_text:
                    current_progress = 95
            
            elif "SELURUH PIPELINE" in upper_text and "BERHASIL SELESAI!" in upper_text:
                current_progress = 100
                
    def flush(self):
        pass

async def pipeline_wrapper(brand: str, url: str, skip_generation: bool, custom_creds: dict, skip_deploy: bool):
    global is_running, process_logs, current_progress
    is_running = True
    current_progress = 5
    process_logs.clear()
    
    old_stdout = sys.stdout
    sys.stdout = LogCaptureStream()
    
    try:
        # Jalankan dengan menyertakan parameter skip_deploy
        await run_pipeline(brand, url, skip_generation, custom_creds, skip_deploy=skip_deploy)
        current_progress = 100
    except Exception as e:
        process_logs.append(f"[ERROR] Terjadi kegagalan sistem: {str(e)}")
        if current_progress == 100:
            current_progress = 99 
    finally:
        sys.stdout = old_stdout
        is_running = False

@app.get("/", response_class=HTMLResponse)
async def index_page():
    html_content = """
    <!DOCTYPE html>
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

        <!-- Header Utama (Tanpa Gimmick Status) -->
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
                        <input type="text" id="brand" name="brand" placeholder="Contoh: zecurion" required
                            class="w-full bg-slate-50 border border-slate-200 rounded-lg px-3 py-2 text-sm text-slate-900 placeholder-slate-400 focus:outline-none focus:border-ilogo-green focus:bg-white transition-all">
                    </div>
                    
                    <div class="space-y-1.5">
                        <label for="url" class="text-xs font-semibold text-slate-700">URL Referensi Brand:</label>
                        <input type="text" id="url" name="url" placeholder="Contoh: zecurion.com"
                            class="w-full bg-slate-50 border border-slate-200 rounded-lg px-3 py-2 text-sm text-slate-900 placeholder-slate-400 focus:outline-none focus:border-ilogo-green focus:bg-white transition-all">
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
                        <input type="checkbox" id="skip_deploy" name="skip_deploy" class="mt-1 rounded border-amber-300 text-ilogo-orange w-4 h-4 accent-ilogo-orange">
                        <div class="space-y-0.5">
                            <span class="text-xs font-semibold text-amber-900 block">Local Draft Mode</span>
                            <span class="text-[11px] text-amber-700 block">Hanya simpan Teks, Gambar & Preview HTML di komputer lokal, tanpa deploy ke WordPress.</span>
                        </div>
                    </label>
                </div>

                <!-- Konfigurasi WordPress Target -->
                <div id="wpFieldset" class="bg-white border border-slate-200 rounded-xl p-5 space-y-4 shadow-sm transition-all duration-200">
                    <h2 class="font-bold text-xs uppercase tracking-wider text-slate-400 border-b border-slate-100 pb-2">Pengaturan WordPress Target (User Custom)</h2>
                    
                    <p class="text-[11px] text-slate-500 bg-slate-50 p-2 rounded border border-slate-100">
                        * Kosongkan area di bawah ini jika Anda ingin sistem menggunakan data WordPress default dari file .env internal developer.
                    </p>

                    <div class="space-y-1.5">
                        <label class="text-xs font-semibold text-slate-700">WordPress Base URL Target:</label>
                        <input type="url" id="wp_url" name="wp_url" placeholder="Contoh: http://localhost/zecurion"
                            class="w-full bg-slate-50 border border-slate-200 rounded-lg px-3 py-2 text-sm text-slate-900 focus:outline-none focus:border-ilogo-green focus:bg-white transition-all disabled:opacity-40">
                    </div>

                    <div class="space-y-1.5">
                        <label class="text-xs font-semibold text-slate-700">WordPress Username Admin:</label>
                        <input type="text" id="wp_username" name="wp_username" placeholder="Masukkan nama pengguna WordPress admin"
                            class="w-full bg-slate-50 border border-slate-200 rounded-lg px-3 py-2 text-sm text-slate-900 focus:outline-none focus:border-ilogo-green focus:bg-white transition-all disabled:opacity-40">
                    </div>

                    <div class="space-y-1.5">
                        <label class="text-xs font-semibold text-slate-700">WordPress Application Password:</label>
                        <input type="text" id="wp_app_password" name="wp_app_password" placeholder="Format: xxxx xxxx xxxx xxxx"
                            class="w-full bg-slate-50 border border-slate-200 rounded-lg px-3 py-2 text-sm text-slate-900 focus:outline-none focus:border-ilogo-green focus:bg-white transition-all disabled:opacity-40">
                    </div>
                </div>

                <!-- Tombol Submit Utama -->
                <button type="submit" id="submitBtn" class="w-full bg-ilogo-green hover:bg-emerald-800 text-white py-3 px-6 rounded-lg font-bold tracking-wide transition-all active:scale-[0.99] flex items-center justify-center gap-2 text-sm">
                    <i data-lucide="play" class="w-4 h-4 fill-current"></i> Mulai Proses Generator
                </button>
            </form>

            <!-- Kanan: Monitor Progress & Konsol Log -->
            <section class="lg:col-span-7 flex flex-col space-y-6">
                <div class="bg-white border border-slate-200 rounded-xl p-5 flex flex-col flex-1 shadow-sm min-h-[500px]">
                    
                    <div class="flex items-center justify-between pb-3 border-b border-slate-100">
                        <div class="flex items-center gap-2">
                            <div class="h-2 w-2 rounded-full bg-slate-300" id="statusPulse"></div>
                            <h2 class="font-bold text-xs uppercase tracking-wider text-slate-400">Status & Live Output Log</h2>
                        </div>
                        <span id="statusBadge" class="text-[10px] px-2 py-0.5 rounded font-bold bg-slate-100 text-slate-600 border border-slate-200">IDLE</span>
                    </div>

                    <!-- Progress Bar -->
                    <div class="py-4 space-y-1.5">
                        <div class="flex justify-between text-xs">
                            <span class="text-slate-500" id="progressStatusText">Menunggu proses dimulai...</span>
                            <span class="text-ilogo-green font-bold" id="progressPercentage">0%</span>
                        </div>
                        <div class="w-full bg-slate-100 h-2 rounded-full overflow-hidden border border-slate-200">
                            <div id="myProgressBar" class="h-full bg-gradient-to-r from-ilogo-orange to-amber-500 w-0 transition-all duration-300 rounded-full"></div>
                        </div>
                    </div>

                    <!-- Terminal Log Console -->
                    <div class="flex-1 flex flex-col bg-slate-950 rounded-lg overflow-hidden font-mono text-xs shadow-inner">
                        <div id="logConsole" class="flex-1 p-4 overflow-y-auto space-y-1.5 text-slate-300 max-h-[380px] select-text">
                            <div class="text-slate-500">[SYSTEM] Siap menerima perintah eksekusi...</div>
                        </div>
                    </div>
                </div>
            </section>
        </main>

        <script>
            lucide.createIcons();
            let logInterval;

            document.getElementById('skip_deploy').addEventListener('change', function() {
                const fieldset = document.getElementById('wpFieldset');
                const inputs = fieldset.querySelectorAll('input');
                if(this.checked) {
                    fieldset.classList.add('opacity-40', 'pointer-events-none');
                    inputs.forEach(i => i.disabled = true);
                } else {
                    fieldset.classList.remove('opacity-40', 'pointer-events-none');
                    inputs.forEach(i => i.disabled = false);
                }
            });

            async function startGeneration(event) {
                event.preventDefault();
                
                const brand = document.getElementById('brand').value;
                const url = document.getElementById('url').value;
                const skipGen = document.getElementById('skip_generation').checked;
                const skipDeploy = document.getElementById('skip_deploy').checked;
                
                const wpUrl = document.getElementById('wp_url').value.trim();
                const wpUser = document.getElementById('wp_username').value.trim();
                const wpPass = document.getElementById('wp_app_password').value.trim();

                if (!skipGen && !url) {
                    alert("URL Referensi Brand wajib diisi jika tidak menggunakan Skip Generation Mode!");
                    return;
                }

                if (!skipDeploy && (wpUrl || wpUser || wpPass)) {
                    if (!wpUrl || !wpUser || !wpPass) {
                        alert("PENTING: Jika ingin menggunakan kustom situs WordPress, Anda harus mengisi URL, Username, dan Application Password secara lengkap!");
                        return;
                    }
                }

                document.getElementById('submitBtn').disabled = true;
                document.getElementById('submitBtn').classList.add('opacity-50', 'cursor-not-allowed');
                
                const pulse = document.getElementById('statusPulse');
                pulse.className = "h-2 w-2 rounded-full bg-ilogo-orange animate-ping";
                
                const badge = document.getElementById('statusBadge');
                badge.innerText = "RUNNING";
                badge.className = "text-[10px] px-2 py-0.5 rounded font-bold bg-amber-50 text-ilogo-orange border border-amber-200";

                document.getElementById('progressStatusText').innerText = "Menginisialisasi backend...";
                document.getElementById('myProgressBar').style.width = '0%';
                document.getElementById('progressPercentage').innerText = '0%';
                document.getElementById('logConsole').innerHTML = "<div class='text-slate-400'>[*] Menghubungi server backend...</div>";

                const formData = new FormData();
                formData.append('brand', brand);
                formData.append('url', url);
                formData.append('skip_generation', skipGen);
                formData.append('skip_deploy', skipDeploy);
                formData.append('wp_url', wpUrl);
                formData.append('wp_username', wpUser);
                formData.append('wp_app_password', wpPass);

                try {
                    await fetch('/generate', { method: 'POST', body: formData });
                    logInterval = setInterval(pollLogs, 1000);
                } catch (error) {
                    document.getElementById('logConsole').innerHTML = "<div class='text-red-400'>[X] Gagal terhubung ke server.</div>";
                    resetUI();
                }
            }

            async function pollLogs() {
                try {
                    const response = await fetch('/status');
                    const data = await response.json();
                    
                    const progress = data.progress;
                    document.getElementById('myProgressBar').style.width = progress + '%';
                    document.getElementById('progressPercentage').innerText = progress + '%';
                    
                    if (progress > 5 && progress < 100) {
                        document.getElementById('progressStatusText').innerText = "Proses sedang berjalan...";
                    }

                    const consoleElem = document.getElementById('logConsole');
                    if (data.logs.length > 0) {
                        const coloredLogs = data.logs.map(log => {
                            if (log.includes('[✓]') || log.includes('SUCCESS') || log.includes('SELESAI')) {
                                return `<div class="text-emerald-400">${log}</div>`;
                            } else if (log.includes('[X]') || log.includes('Error') || log.includes('ERROR')) {
                                return `<div class="text-red-400 font-semibold bg-red-950/20 p-1 rounded border border-red-900/30">${log}</div>`;
                            } else if (log.includes('[!]') || log.includes('Warning')) {
                                return `<div class="text-amber-400">${log}</div>`;
                            }
                            return `<div class="text-slate-300">${log}</div>`;
                        });
                        consoleElem.innerHTML = coloredLogs.join('');
                        consoleElem.scrollTop = consoleElem.scrollHeight;
                    }

                    if (!data.is_running) {
                        clearInterval(logInterval);
                        resetUI(progress === 100);
                    }
                } catch (e) {
                    console.error("Gagal membaca log status", e);
                }
            }

            function resetUI(isSuccess = false) {
                document.getElementById('submitBtn').disabled = false;
                document.getElementById('submitBtn').classList.remove('opacity-50', 'cursor-not-allowed');
                
                const pulse = document.getElementById('statusPulse');
                const badge = document.getElementById('statusBadge');
                
                if (isSuccess) {
                    pulse.className = "h-2 w-2 rounded-full bg-ilogo-green";
                    badge.innerText = "SUCCESS";
                    badge.className = "text-[10px] px-2 py-0.5 rounded font-bold bg-emerald-50 text-ilogo-green border border-emerald-200";
                    document.getElementById('progressStatusText').innerText = "Proses selesai.";
                    alert("Proses generator selesai dieksekusi!");
                } else {
                    pulse.className = "h-2 w-2 rounded-full bg-slate-300";
                    badge.innerText = "IDLE";
                    badge.className = "text-[10px] px-2 py-0.5 rounded font-bold bg-slate-100 text-slate-600 border border-slate-200";
                    document.getElementById('progressStatusText').innerText = "Proses berhenti.";
                }
            }
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)

@app.post("/generate")
async def generate_website(
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
        return JSONResponse(status_code=400, content={"status": "error", "message": "Ada proses generator yang sedang berjalan di background."})
    
    custom_creds = None
    if not skip_deploy and wp_url and wp_username and wp_app_password:
        custom_creds = {
            "wp_url": wp_url,
            "wp_username": wp_username,
            "wp_app_password": wp_app_password
        }
    
    background_tasks.add_task(pipeline_wrapper, brand, url, skip_generation, custom_creds, skip_deploy)
    return {"status": "started"}

@app.get("/status")
async def get_status():
    global process_logs, is_running, current_progress
    return {"is_running": is_running, "logs": process_logs, "progress": current_progress}