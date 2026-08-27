# -*- coding: utf-8 -*-
"""
Web UI routes untuk Blog Autopost Generator.

Additive module — tidak menyentuh `web.py` existing. Cukup import
`register_blog_routes` di web.py dan panggil dengan instance `app` FastAPI-nya.

Routes:
  GET  /blog              → form generator + autopost
  POST /blog/generate     → trigger background task (scrape → generate → deploy)
  GET  /blog/status       → polling status batch

Berbagi state opsional dengan pipeline website via `website_is_running_getter`
untuk mencegah dua batch jalan berbarengan.
"""

import asyncio
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, Form, BackgroundTasks
from fastapi.responses import HTMLResponse, JSONResponse

from content.blog_generator import (
    collect_brand_material,
    generate_blog_batch,
)
from wordpress.client import WordPressClient
from wordpress.blog_deploy import deploy_blog_batch
from visual.image_fetch import StockImageFetcher


# ─────────────────────────────────────────────────────────────────────────────
# Module-level state (batch blog)
# ─────────────────────────────────────────────────────────────────────────────

_blog_state = {
    "is_running": False,
    "logs": [],
    "progress_current": 0,
    "progress_total": 0,
    "progress_message": "",
    "articles": [],
    "deploy_results": [],
    "prompt_tokens": 0,
    "completion_tokens": 0,
    "material_chars": 0,
    "started_at": None,
    "finished_at": None,
    "error": None,
}


def _log(msg: str):
    print(msg)
    _blog_state["logs"].append(msg)
    if len(_blog_state["logs"]) > 500:
        _blog_state["logs"] = _blog_state["logs"][-400:]


def _on_progress(current: int, total: int, message: str):
    _blog_state["progress_current"] = current
    _blog_state["progress_total"] = total
    _blog_state["progress_message"] = message


def _reset_state():
    _blog_state.update({
        "is_running": True,
        "logs": [],
        "progress_current": 0,
        "progress_total": 0,
        "progress_message": "Memulai...",
        "articles": [],
        "deploy_results": [],
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "material_chars": 0,
        "started_at": datetime.now().isoformat(),
        "finished_at": None,
        "error": None,
    })


# ─────────────────────────────────────────────────────────────────────────────
# Background worker
# ─────────────────────────────────────────────────────────────────────────────

async def _run_blog_pipeline(
    brand_name: str,
    homepage_url: str,
    reference_urls: list[str],
    manual_content: str,
    main_keyword: str,
    secondary_keywords: list[str],
    n_articles: int,
    provider_chain_str: str,
    do_deploy: bool,
    wp_url: str,
    wp_username: str,
    wp_app_password: str,
    category_name: str,
    start_date: Optional[datetime],
    interval_days: int,
    publish_hour: int,
    include_featured_image: bool,
):
    """Background task — collect material → generate → (opsional) deploy."""
    try:
        # ── Step A: Kumpulkan materi brand ──────────────────────────────────
        _on_progress(0, n_articles + 2, "Mengumpulkan materi brand (scrape + manual)")
        material = await collect_brand_material(
            homepage_url=homepage_url,
            reference_urls=reference_urls,
            manual_content=manual_content,
            log=_log,
        )
        _blog_state["material_chars"] = len(material)

        # Kalau materi kosong dan user tidak paste apapun, TOLAK — jangan
        # biarkan LLM mengarang.
        if not material.strip():
            msg = ("Materi brand kosong — tidak ada sumber yang berhasil di-scrape "
                   "dan tidak ada manual content. Isi minimal salah satu: homepage "
                   "URL yang valid, reference URL, atau paste manual content.")
            _blog_state["error"] = msg
            _log(f"[Blog Fatal] {msg}")
            return

        # ── Step B: Generate ────────────────────────────────────────────────
        articles, stats = await asyncio.to_thread(
            generate_blog_batch,
            brand_name=brand_name,
            brand_material=material,
            main_keyword=main_keyword,
            secondary_keywords=secondary_keywords,
            n_articles=n_articles,
            provider_chain_str=provider_chain_str,
            log=_log,
            on_progress=_on_progress,
        )

        _blog_state["articles"] = articles
        _blog_state["prompt_tokens"] = stats.get("prompt_tokens", 0)
        _blog_state["completion_tokens"] = stats.get("completion_tokens", 0)

        if not articles:
            _blog_state["error"] = "Tidak ada artikel yang berhasil di-generate."
            return

        # ── Step C: Featured image (opsional) ───────────────────────────────
        featured_urls: list[Optional[str]] = []
        if include_featured_image and do_deploy:
            _log("[Blog] Mengambil featured image via Unsplash...")
            fetcher = StockImageFetcher()
            for a in articles:
                query = a.get("_topic_target_keyword") or main_keyword
                try:
                    url = await fetcher.fetch_stock_url(query)
                    featured_urls.append(url or None)
                except Exception as e:
                    _log(f"[Blog Warning] Featured image fetch gagal: {e}")
                    featured_urls.append(None)
                await asyncio.sleep(5)  # ikuti Visual Rate Limit Guard iAAWG

        # ── Step D: Deploy ke WordPress ─────────────────────────────────────
        if not do_deploy:
            _log("[Blog] Skip deploy — artikel tersedia di /blog/status untuk review.")
            return

        try:
            client = WordPressClient(
                url=wp_url,
                username=wp_username,
                app_password=wp_app_password,
            )
        except ValueError as e:
            _blog_state["error"] = f"WordPress credential invalid: {e}"
            _log(f"[Blog Fatal] {_blog_state['error']}")
            return

        _log(f"[Blog] Deploy ke {wp_url} dimulai...")
        deploy_results = await deploy_blog_batch(
            client=client,
            articles=articles,
            category_name=category_name,
            start_date=start_date,
            interval_days=interval_days,
            publish_hour=publish_hour,
            featured_image_urls=featured_urls if featured_urls else None,
            log=_log,
        )
        _blog_state["deploy_results"] = deploy_results

    except Exception as e:
        _blog_state["error"] = f"Unhandled: {e}"
        _log(f"[Blog Fatal] {e}")
    finally:
        _blog_state["is_running"] = False
        _blog_state["finished_at"] = datetime.now().isoformat()


# ─────────────────────────────────────────────────────────────────────────────
# HTML form
# ─────────────────────────────────────────────────────────────────────────────

_FORM_HTML = """<!DOCTYPE html>
<html lang="id">
<head>
<meta charset="utf-8">
<title>iAAWG — Blog Autopost</title>
<style>
  body { font-family: -apple-system, Segoe UI, sans-serif; max-width: 820px; margin: 40px auto; padding: 0 20px; color: #222; }
  h1 { color: #1E7E34; margin-bottom: 4px; }
  h1 + p { color: #666; margin-top: 0; }
  fieldset { border: 1px solid #ddd; border-radius: 6px; padding: 16px 20px; margin-bottom: 18px; }
  legend { font-weight: 600; padding: 0 8px; color: #1E7E34; }
  label { display: block; margin: 10px 0 4px; font-weight: 500; font-size: 14px; }
  input[type=text], input[type=password], input[type=url], input[type=number], input[type=date], textarea, select {
    width: 100%; padding: 8px 10px; border: 1px solid #ccc; border-radius: 4px; font-size: 14px; font-family: inherit; box-sizing: border-box;
  }
  textarea { min-height: 80px; font-family: inherit; }
  textarea.material { min-height: 140px; font: 12px/1.5 Menlo, Consolas, monospace; }
  .row { display: flex; gap: 12px; }
  .row > div { flex: 1; }
  .hint { font-size: 12px; color: #888; margin-top: 3px; }
  .required-mark { color: #c62828; font-weight: 700; }
  button { background: #1E7E34; color: white; border: 0; padding: 10px 18px; border-radius: 4px; font-size: 15px; font-weight: 600; cursor: pointer; margin-top: 12px; }
  button:disabled { background: #999; cursor: not-allowed; }
  #status { background: #f6f6f6; border-radius: 6px; padding: 14px 18px; margin-top: 20px; display: none; }
  #status.on { display: block; }
  .progress-bar { background: #e0e0e0; border-radius: 3px; height: 8px; margin: 8px 0; overflow: hidden; }
  .progress-fill { background: #1E7E34; height: 100%; transition: width .3s; }
  #logs { background: #1e1e1e; color: #d4d4d4; padding: 10px 14px; font: 12px/1.5 Menlo, monospace; height: 260px; overflow-y: auto; border-radius: 4px; margin-top: 10px; white-space: pre-wrap; }
  #articles { margin-top: 14px; }
  .article-card { background: white; border: 1px solid #ddd; border-radius: 4px; padding: 10px 14px; margin-bottom: 8px; }
  .article-card .meta { font-size: 12px; color: #666; margin-top: 3px; }
  .warn { color: #b48000; }
  .ok { color: #1E7E34; }
  .err { color: #c62828; }
  .back { display: inline-block; margin-bottom: 20px; color: #1E7E34; text-decoration: none; }
  .callout { background: #fff8e1; border-left: 3px solid #f9a825; padding: 10px 14px; font-size: 13px; margin: 10px 0; border-radius: 3px; }
</style>
</head>
<body>
  <a href="/" class="back">← Kembali ke Website Generator</a>
  <h1>Blog Autopost Generator</h1>
  <p>Generate artikel SEO 1500+ kata dan schedule autopost ke WordPress.</p>

  <form id="blogForm">
    <fieldset>
      <legend>Brand & Keyword</legend>
      <label>Nama Brand <span class="required-mark">*</span></label>
      <input type="text" name="brand_name" placeholder="Contoh: Zecurion" required>

      <label>Keyword Utama <span class="required-mark">*</span></label>
      <input type="text" name="main_keyword" placeholder="Contoh: Zecurion Indonesia" required>
      <div class="hint">Muncul di judul, meta description, intro, minimal 1 H2, dan penutup.</div>

      <label>Keyword Tambahan (pisah koma)</label>
      <input type="text" name="secondary_keywords" placeholder="Contoh: DLP Indonesia, data loss prevention enterprise">
      <div class="hint">Masing-masing keyword akan muncul minimal 2× di artikel.</div>
    </fieldset>

    <fieldset>
      <legend>Sumber Materi <span class="required-mark">*</span> (minimal salah satu)</legend>
      <div class="callout">
        Sistem TIDAK boleh mengarang produk/fitur brand yang tidak dikenalinya.
        Isi minimal salah satu sumber di bawah — semakin kaya materi, semakin
        akurat dan panjang artikelnya.
      </div>

      <label>Homepage URL Brand</label>
      <input type="url" name="homepage_url" placeholder="https://brand.com">
      <div class="hint">Akan di-scrape via Playwright (retry 3×, deteksi Cloudflare).</div>

      <label>URL Referensi Tambahan (1 per baris, opsional)</label>
      <textarea name="reference_urls" placeholder="https://brand.com/products&#10;https://brand.com/about&#10;https://brand.com/solutions/x"></textarea>
      <div class="hint">Halaman produk, about, use case, whitepaper — apa saja yang memperkaya materi.</div>

      <label>Manual Content (opsional, paste bebas)</label>
      <textarea name="manual_content" class="material" placeholder="Paste materi mentah di sini kalau situs brand di-block Cloudflare atau kalau Anda punya materi internal (press release, product brief, dsb.) yang lebih kaya dari situs publik."></textarea>
    </fieldset>

    <fieldset>
      <legend>Konfigurasi Batch</legend>
      <div class="row">
        <div>
          <label>Jumlah Artikel <span class="required-mark">*</span></label>
          <input type="number" name="n_articles" min="1" max="15" required placeholder="mis. 3">
          <div class="hint">Range 1-15. Tiap artikel = 1 LLM call, waktu ± 30-60 detik.</div>
        </div>
        <div>
          <label>LLM Chain</label>
          <select name="llm_chain">
            <option value="openai,groq" selected>OpenAI → Groq (failover)</option>
            <option value="groq,openai">Groq → OpenAI (failover)</option>
            <option value="openai">OpenAI only</option>
            <option value="groq">Groq only</option>
          </select>
        </div>
      </div>
    </fieldset>

    <fieldset>
      <legend>WordPress Deploy</legend>
      <label><input type="checkbox" name="do_deploy" checked> Deploy ke WordPress</label>

      <div class="row">
        <div>
          <label>WP URL</label>
          <input type="url" name="wp_url" placeholder="https://brand.co.id">
        </div>
        <div>
          <label>Username</label>
          <input type="text" name="wp_username">
        </div>
      </div>

      <label>Application Password</label>
      <input type="password" name="wp_app_password" placeholder="xxxx xxxx xxxx xxxx xxxx">

      <div class="row">
        <div>
          <label>Kategori</label>
          <input type="text" name="category_name" value="Insight">
        </div>
        <div>
          <label>Featured Image (Unsplash)</label>
          <select name="include_featured_image">
            <option value="yes" selected>Ya, ambil otomatis</option>
            <option value="no">Tidak</option>
          </select>
        </div>
      </div>
    </fieldset>

    <fieldset>
      <legend>Jadwal Autopost</legend>
      <label><input type="checkbox" name="use_schedule" checked> Jadwalkan (staggered), jangan publish semua sekaligus</label>

      <div class="row">
        <div>
          <label>Mulai Tanggal</label>
          <input type="date" name="start_date">
        </div>
        <div>
          <label>Interval Hari</label>
          <input type="number" name="interval_days" value="1" min="1" max="30">
        </div>
        <div>
          <label>Jam Publish</label>
          <input type="number" name="publish_hour" value="9" min="0" max="23">
        </div>
      </div>
      <div class="hint">Contoh: mulai besok, interval 1 → publish H+1, H+2, H+3, dst di jam 9 pagi. Kalau uncheck, semua artikel publish langsung.</div>
    </fieldset>

    <button type="submit" id="submitBtn">Generate & Autopost</button>
  </form>

  <div id="status">
    <div><strong id="progressMsg">Memulai...</strong> — <span id="progressPct">0%</span></div>
    <div class="progress-bar"><div id="progressFill" class="progress-fill" style="width:0%"></div></div>
    <div class="hint">
      Materi: <span id="matChars">0</span> char ·
      Tokens: <span id="tokens">0 in / 0 out</span>
    </div>
    <div id="logs"></div>
    <div id="articles"></div>
  </div>

<script>
// Set default start date = tomorrow
(function(){
  const t = new Date(); t.setDate(t.getDate()+1);
  document.querySelector('input[name=start_date]').value = t.toISOString().slice(0,10);
})();

const form = document.getElementById('blogForm');
const statusEl = document.getElementById('status');
const submitBtn = document.getElementById('submitBtn');

form.addEventListener('submit', async (e) => {
  e.preventDefault();

  // Client-side check: minimal salah satu sumber materi
  const fd = new FormData(form);
  const hasHome = (fd.get('homepage_url')||'').trim();
  const hasRefs = (fd.get('reference_urls')||'').trim();
  const hasManual = (fd.get('manual_content')||'').trim();
  if (!hasHome && !hasRefs && !hasManual) {
    alert('Isi minimal salah satu sumber materi: Homepage URL, URL Referensi, atau Manual Content.');
    return;
  }

  submitBtn.disabled = true;
  submitBtn.textContent = 'Berjalan...';
  statusEl.classList.add('on');

  const resp = await fetch('/blog/generate', { method: 'POST', body: fd });
  if (!resp.ok) {
    const j = await resp.json().catch(()=>({detail:'Unknown error'}));
    alert('Gagal start: ' + (j.detail || resp.status));
    submitBtn.disabled = false;
    submitBtn.textContent = 'Generate & Autopost';
    return;
  }
  pollStatus();
});

async function pollStatus() {
  const logsEl = document.getElementById('logs');
  const articlesEl = document.getElementById('articles');
  const progressMsg = document.getElementById('progressMsg');
  const progressPct = document.getElementById('progressPct');
  const progressFill = document.getElementById('progressFill');
  const tokensEl = document.getElementById('tokens');
  const matEl = document.getElementById('matChars');

  const iv = setInterval(async () => {
    let s;
    try { s = await (await fetch('/blog/status')).json(); }
    catch(e) { return; }

    logsEl.textContent = s.logs.join('\\n');
    logsEl.scrollTop = logsEl.scrollHeight;

    const pct = s.progress_total ? Math.round(100 * s.progress_current / s.progress_total) : 0;
    progressMsg.textContent = s.progress_message || '...';
    progressPct.textContent = pct + '%';
    progressFill.style.width = pct + '%';
    tokensEl.textContent = s.prompt_tokens + ' in / ' + s.completion_tokens + ' out';
    matEl.textContent = s.material_chars || 0;

    if (!s.is_running) {
      clearInterval(iv);
      submitBtn.disabled = false;
      submitBtn.textContent = 'Generate & Autopost';

      if (s.articles && s.articles.length) {
        articlesEl.innerHTML = '<h3>Artikel yang dibuat:</h3>' +
          s.articles.map((a, i) => {
            const wc = a._word_count || 0;
            const wcClass = a._meets_min_words ? 'ok' : 'warn';
            const dep = s.deploy_results && s.deploy_results[i];
            const depBadge = dep && dep.id
              ? '<span class="ok">✓ deployed (id ' + dep.id + (dep.status==='future' ? ', scheduled ' + dep.date : '') + ')</span>'
              : (dep === undefined ? '' : '<span class="err">✗ deploy gagal</span>');
            const anchor = a._topic_material_anchor
              ? '<div class="meta">Anchor materi: ' + escapeHtml(a._topic_material_anchor) + '</div>' : '';
            return '<div class="article-card"><strong>' + escapeHtml(a.title || 'Untitled') + '</strong>'
              + '<div class="meta"><span class="' + wcClass + '">' + wc + ' kata</span> · '
              + escapeHtml(a._topic_angle || '-') + ' · '
              + escapeHtml((a.tags||[]).join(', ')) + ' ' + depBadge + '</div>' + anchor + '</div>';
          }).join('');
      }
      if (s.error) {
        articlesEl.innerHTML = '<div class="article-card err">Error: ' + escapeHtml(s.error) + '</div>' + articlesEl.innerHTML;
      }
    }
  }, 1500);
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'})[c]);
}
</script>
</body>
</html>
"""


# ─────────────────────────────────────────────────────────────────────────────
# Registration
# ─────────────────────────────────────────────────────────────────────────────

def register_blog_routes(app: FastAPI, website_is_running_getter=None):
    """
    Daftarkan route blog ke instance FastAPI existing.

    Args:
        app: instance FastAPI dari web.py
        website_is_running_getter: callable → bool. Kalau None, tidak cek
            konflik dengan pipeline website. Kalau di-set, blog akan menolak
            start selama website pipeline masih jalan (mencegah quota LLM
            bentrok). Contoh: `lambda: is_running`.
    """

    @app.get("/blog", response_class=HTMLResponse)
    async def blog_form():
        return HTMLResponse(_FORM_HTML)

    @app.post("/blog/generate")
    async def blog_generate(
        background_tasks: BackgroundTasks,
        brand_name: str = Form(...),
        main_keyword: str = Form(...),
        secondary_keywords: str = Form(""),
        homepage_url: str = Form(""),
        reference_urls: str = Form(""),
        manual_content: str = Form(""),
        n_articles: int = Form(...),
        llm_chain: str = Form("openai,groq"),
        do_deploy: str = Form(""),
        wp_url: str = Form(""),
        wp_username: str = Form(""),
        wp_app_password: str = Form(""),
        category_name: str = Form("Insight"),
        include_featured_image: str = Form("yes"),
        use_schedule: str = Form(""),
        start_date: str = Form(""),
        interval_days: int = Form(1),
        publish_hour: int = Form(9),
    ):
        if _blog_state["is_running"]:
            return JSONResponse(
                status_code=400,
                content={"detail": "Batch blog lain masih berjalan."},
            )
        if website_is_running_getter and website_is_running_getter():
            return JSONResponse(
                status_code=400,
                content={"detail": "Pipeline website sedang berjalan — tunggu selesai."},
            )

        # Range validation — server-side
        n_articles = int(n_articles)
        if n_articles < 1 or n_articles > 15:
            return JSONResponse(
                status_code=400,
                content={"detail": "Jumlah artikel harus antara 1 dan 15."},
            )

        # Sumber materi: minimal salah satu
        homepage_url = homepage_url.strip()
        reference_urls_list = [
            u.strip() for u in reference_urls.splitlines() if u.strip()
        ]
        manual_content = manual_content.strip()
        if not (homepage_url or reference_urls_list or manual_content):
            return JSONResponse(
                status_code=400,
                content={"detail": "Isi minimal salah satu sumber materi: "
                                   "Homepage URL, URL Referensi, atau Manual Content."},
            )

        do_deploy_bool = bool(do_deploy)
        include_featured_bool = (include_featured_image == "yes")
        use_schedule_bool = bool(use_schedule)

        if do_deploy_bool:
            if not (wp_url and wp_username and wp_app_password):
                return JSONResponse(
                    status_code=400,
                    content={"detail": "Deploy WordPress dipilih tapi credential belum lengkap."},
                )

        parsed_start: Optional[datetime] = None
        if use_schedule_bool and start_date:
            try:
                parsed_start = datetime.strptime(start_date, "%Y-%m-%d")
            except Exception:
                return JSONResponse(
                    status_code=400,
                    content={"detail": "Format start_date tidak valid (harus YYYY-MM-DD)."},
                )

        secondary_list = [k.strip() for k in secondary_keywords.split(",") if k.strip()]

        _reset_state()
        _log(f"[Blog] Request diterima. brand={brand_name}, n_articles={n_articles}, "
             f"sumber={{home:{bool(homepage_url)}, refs:{len(reference_urls_list)}, "
             f"manual:{bool(manual_content)}}}, deploy={do_deploy_bool}, "
             f"schedule={use_schedule_bool}")

        background_tasks.add_task(
            _run_blog_pipeline,
            brand_name=brand_name.strip(),
            homepage_url=homepage_url,
            reference_urls=reference_urls_list,
            manual_content=manual_content,
            main_keyword=main_keyword.strip(),
            secondary_keywords=secondary_list,
            n_articles=n_articles,
            provider_chain_str=llm_chain,
            do_deploy=do_deploy_bool,
            wp_url=wp_url.strip(),
            wp_username=wp_username.strip(),
            wp_app_password=wp_app_password.strip(),
            category_name=category_name.strip(),
            start_date=parsed_start,
            interval_days=int(interval_days),
            publish_hour=int(publish_hour),
            include_featured_image=include_featured_bool,
        )

        return {"status": "started"}

    @app.get("/blog/status")
    async def blog_status():
        arts_lite = []
        for a in _blog_state["articles"]:
            arts_lite.append({
                "title": a.get("title", ""),
                "slug": a.get("slug", ""),
                "excerpt": a.get("excerpt", ""),
                "tags": a.get("tags", []),
                "_word_count": a.get("_word_count", 0),
                "_meets_min_words": a.get("_meets_min_words", False),
                "_topic_angle": a.get("_topic_angle", ""),
                "_topic_material_anchor": a.get("_topic_material_anchor", ""),
            })
        deploy_lite = []
        for d in _blog_state["deploy_results"]:
            if isinstance(d, dict) and d.get("id"):
                deploy_lite.append({
                    "id": d.get("id"),
                    "status": d.get("status"),
                    "date": d.get("date"),
                    "link": d.get("link"),
                })
            else:
                deploy_lite.append(None)
        return {
            "is_running": _blog_state["is_running"],
            "progress_current": _blog_state["progress_current"],
            "progress_total": _blog_state["progress_total"],
            "progress_message": _blog_state["progress_message"],
            "prompt_tokens": _blog_state["prompt_tokens"],
            "completion_tokens": _blog_state["completion_tokens"],
            "material_chars": _blog_state["material_chars"],
            "logs": _blog_state["logs"][-200:],
            "articles": arts_lite,
            "deploy_results": deploy_lite,
            "error": _blog_state["error"],
            "started_at": _blog_state["started_at"],
            "finished_at": _blog_state["finished_at"],
        }
