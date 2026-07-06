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
        <title>iAAWG — AI Auto Website Generator</title>
        <style>
            :root {
                --brand-green: #1E7E34;    
                --brand-orange: #FF9E1B;   
                --brand-dark: #1A1A1A;     
                --bg-light: #FAFAFA;
            }

            body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: var(--bg-light); color: #333; margin: 0; padding: 40px; }
            .container { max-width: 800px; background: white; padding: 30px; border-radius: 12px; box-shadow: 0 4px 12px rgba(0,0,0,0.05); margin: 0 auto; }
            h1 { color: var(--brand-dark); margin-top: 0; border-bottom: 2px solid #EEE; padding-bottom: 10px; font-weight: 700; }
            .form-group { margin-bottom: 20px; }
            label { display: block; font-weight: 600; margin-bottom: 8px; color: #444; }
            input[type="text"], input[type="url"] { width: 100%; padding: 12px; border: 1px solid #DDD; border-radius: 6px; box-sizing: border-box; transition: border 0.2s; }
            input[type="text"]:focus, input[type="url"]:focus { border-color: var(--brand-green); outline: none; }
            .checkbox-group { display: flex; align-items: center; margin-top: 15px; margin-bottom: 15px; }
            .checkbox-group input { margin-right: 10px; width: 18px; height: 18px; accent-color: var(--brand-green); }
            fieldset { border: 1px solid #DDD; padding: 20px; border-radius: 8px; margin-top: 25px; margin-bottom: 25px; background-color: #FCFCFC; }
            legend { font-weight: bold; color: var(--brand-dark); padding: 0 10px; font-size: 14px; }
            button { background-color: var(--brand-green); color: white; padding: 14px 20px; border: none; border-radius: 6px; cursor: pointer; font-size: 16px; width: 100%; font-weight: bold; transition: background 0.2s; }
            button:hover { background-color: #155D25; }
            button:disabled { background-color: #CCC; cursor: not-allowed; }
            #loadingSection { display: none; margin-top: 25px; padding: 20px; background: #F4FBF6; border-left: 4px solid var(--brand-orange); border-radius: 6px; }
            .spinner { border: 4px solid #F3F3F3; border-top: 4px solid var(--brand-green); border-radius: 50%; width: 24px; height: 24px; animation: spin 1s linear infinite; display: inline-block; vertical-align: middle; margin-right: 10px; }
            @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
            .progress-container { width: 100%; background-color: #EEE; border-radius: 20px; margin: 15px 0; overflow: hidden; display: block; }
            .progress-bar { width: 0%; height: 20px; background-color: var(--brand-orange); text-align: center; line-height: 20px; color: white; font-weight: bold; font-size: 12px; transition: width 0.4s ease; }
            #logConsole { background: #1E1E1E; color: #E0E0E0; padding: 15px; border-radius: 6px; height: 250px; overflow-y: auto; font-family: 'Courier New', Courier, monospace; font-size: 13px; margin-top: 15px; white-space: pre-wrap; box-shadow: inset 0 2px 4px rgba(0,0,0,0.2); }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>iLogo AI Auto Website Generator (iAAWG)</h1>
            <p style="color: #666;">Hasilkan website subdomain iLogo secara otomatis dari website resmi brand dalam hitungan menit.</p>
            
            <form id="generatorForm" onsubmit="startGeneration(event)">
                <div class="form-group">
                    <label for="brand">Nama Brand:</label>
                    <input type="text" id="brand" name="brand" placeholder="Contoh: zecurion" required>
                </div>
                
                <div class="form-group">
                    <label for="url">URL Referensi Brand:</label>
                    <input type="text" id="url" name="url" placeholder="Contoh: zecurion.com">
                </div>
                
                <div class="checkbox-group">
                    <input type="checkbox" id="skip_generation" name="skip_generation">
                    <label for="skip_generation"><strong>Skip Generation Mode</strong> (Gunakan data JSON lokal yang sudah ada, hemat token LLM)</label>
                </div>

                <!-- CHECKBOX BARU UNTUK SKIP DEPLOYMENT -->
                <div class="checkbox-group" style="background: #FFF9E6; padding: 10px; border-radius: 6px; border: 1px dashed var(--brand-orange);">
                    <input type="checkbox" id="skip_deploy" name="skip_deploy">
                    <label for="skip_deploy"><strong>Local Draft Mode</strong> (Hanya simpan Teks, Gambar & Preview HTML di komputer lokal, tanpa deploy ke WordPress)</label>
                </div>
                
                <fieldset id="wpFieldset">
                    <legend>Pengaturan WordPress Target (User Custom)</legend>
                    <p style="font-size: 12px; color: #777; margin-top: 0; margin-bottom: 15px;">
                        * Kosongkan area di bawah ini jika Anda ingin sistem menggunakan data WordPress default dari file .env internal developer.
                    </p>
                    
                    <div class="form-group">
                        <label for="wp_url">WordPress Base URL Target:</label>
                        <input type="url" id="wp_url" name="wp_url" placeholder="Contoh: http://localhost/zecurion">
                    </div>
                    
                    <div class="form-group">
                        <label for="wp_username">WordPress Username Admin:</label>
                        <input type="text" id="wp_username" name="wp_username" placeholder="Masukkan nama pengguna WordPress admin">
                    </div>
                    
                    <div class="form-group">
                        <label for="wp_app_password">WordPress Application Password:</label>
                        <input type="text" id="wp_app_password" name="wp_app_password" placeholder="Format: xxxx xxxx xxxx xxxx xxxx">
                    </div>
                </fieldset>
                
                <div style="margin-top: 25px;">
                    <button type="submit" id="submitBtn">Mulai Proses Generator</button>
                </div>
            </form>

            <div id="loadingSection">
                <div id="statusHeader" style="margin-bottom: 10px;">
                    <div class="spinner" id="statusSpinner"></div>
                    <strong style="font-size: 16px; color: #005177;" id="statusText">Sistem sedang bekerja, mohon jangan tutup halaman ini...</strong>
                </div>
                
                <div class="progress-container">
                    <div id="myProgressBar" class="progress-bar">0%</div>
                </div>

                <div id="logConsole">Menunggu log sistem...</div>
            </div>
        </div>

        <script>
            let logInterval;

            // Efek interaktif: Nonaktifkan form WP jika Local Draft dicentang
            document.getElementById('skip_deploy').addEventListener('change', function() {
                const fieldset = document.getElementById('wpFieldset');
                if(this.checked) {
                    fieldset.style.opacity = "0.5";
                    fieldset.querySelectorAll('input').forEach(i => i.disabled = true);
                } else {
                    fieldset.style.opacity = "1";
                    fieldset.querySelectorAll('input').forEach(i => i.disabled = false);
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
                document.getElementById('loadingSection').style.display = 'block';
                document.getElementById('statusSpinner').style.display = 'inline-block';
                document.getElementById('statusText').innerText = "Sistem sedang bekerja, mohon jangan tutup halaman ini...";
                document.getElementById('myProgressBar').style.width = '0%';
                document.getElementById('myProgressBar').innerText = '0%';
                document.getElementById('logConsole').innerHTML = "[*] Menginisialisasi pipeline di background thread...";

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
                    document.getElementById('logConsole').innerHTML = "[X] Gagal terhubung ke server.";
                }
            }

            async function pollLogs() {
                try {
                    const response = await fetch('/status');
                    const data = await response.json();
                    
                    const progress = data.progress;
                    const pBar = document.getElementById('myProgressBar');
                    pBar.style.width = progress + '%';
                    pBar.innerText = progress + '%';
                    
                    const consoleElem = document.getElementById('logConsole');
                    if (data.logs.length > 0) {
                        consoleElem.innerHTML = data.logs.join('\\n');
                        consoleElem.scrollTop = consoleElem.scrollHeight;
                    }

                    if (!data.is_running) {
                        clearInterval(logInterval);
                        document.getElementById('submitBtn').disabled = false;
                        document.getElementById('statusSpinner').style.display = 'none';
                        
                        if (progress === 100) {
                            document.getElementById('statusText').innerText = "✓ Selesai! Seluruh proses sukses dieksekusi.";
                            document.getElementById('statusText').style.color = "#28a745";
                            alert("Proses Selesai! File draf Anda siap diperiksa.");
                        } else {
                            document.getElementById('statusText').innerText = "❌ Gagal! Terjadi interupsi kesalahan pada sistem.";
                            document.getElementById('statusText').style.color = "#dc3545";
                        }
                    }
                } catch (e) {
                    console.error("Gagal melakukan polling log", e);
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