# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Project Is

**iAAWG** (iLogo AI Auto Website Generator) — two-pipeline AI automation system for PT. iLogo Infralogy Indonesia:

1. **Website Generator** — scrapes a brand's public website → generates localized Indonesian content (Beranda/Solusi/Produk/Kontak) → deploys Elementor-compatible pages to WordPress via REST API.
2. **Blog Autopost Generator** — generates SEO articles (~900 words each, band 850-1000) in batches from brand material, with optional WordPress scheduled publishing.

Both pipelines share: LLM failover engine, WordPress REST client, SQLite settings DB, and image fetching utilities.

## Running the App

**Web UI (recommended):**
```bash
# Windows — do NOT use --reload (Playwright incompatible with Windows auto-reload)
uvicorn web:app
```

Routes:
- `http://127.0.0.1:8000/` — Website Generator
- `http://127.0.0.1:8000/blog` — Blog Autopost Generator
- `http://127.0.0.1:8000/settings` — API key management (stored in `iaawg_settings.db`)
- `http://127.0.0.1:8000/profiles` — Profil Website: profil per-brand yang mengisi otomatis form Blog Autopost

**CLI (website pipeline only):**
```bash
python main.py --brand <brand> --url <homepage>
python main.py --brand zecurion --url zecurion.com --template prestige
python main.py --brand zecurion --skip-generation          # reuse cached JSON
python main.py --brand zecurion --url zecurion.com --skip-deploy  # local draft only
python main.py --brand zecurion --append-mode --product-urls "url1,url2"
```

**Install dependencies:**
```bash
pip install -r requirements.txt
playwright install chromium
```

## Architecture

### Configuration Priority

Settings resolve as: **SQLite DB** (`iaawg_settings.db`, via `/settings` UI) → **`.env`** → hardcoded default. Always use `get_setting("KEY")` from `config/settings.py` — never read `settings.KEY_NAME` directly — so DB overrides apply.

### LLM Failover Engine (`content/generator.py`)

`get_llm_provider(provider_name)` returns `OpenAIProvider` or `GroqProvider`. The website pipeline uses `_generate_with_json_retry()` in `main.py` which retries across providers on JSON parse failure. Blog pipeline uses `generate_with_failover()` in `content/blog_generator.py`. Both support the `"openai,groq"` chain string (comma-separated, ordered by priority).

- OpenAI: `gpt-4.1-mini`, `max_tokens=5500`
- Groq: fallback model, `max_tokens=5500`

### Pipeline Entrypoints

| File | Role |
|---|---|
| `main.py` | CLI entrypoint for website pipeline |
| `web.py` | FastAPI app; website form, startup, shared state |
| `web_blog_routes.py` | Blog routes registered via `register_blog_routes(app, ...)` |
| `content/generator.py` | LLM provider abstraction + failover |
| `content/blog_generator.py` | Blog orchestrator: material collection → topics → articles |
| `wordpress/elementor_builder.py` | Builds Elementor JSON for each page type |
| `wordpress/client.py` | WordPress REST API client (pages, posts, media, templates) |
| `wordpress/smartslider_deploy.py` | Imports `.ss3` slider bundle per brand |
| `wordpress/blog_deploy.py` | Deploys blog posts with scheduling (`status: future`) |
| `visual/preview_templates.py` | Local HTML preview (Tailwind-based, template-aware) |
| `db/settings_store.py` | SQLite-backed key/value store for API keys |
| `db/brand_profiles_store.py` | SQLite-backed per-brand website profiles (tabel `brand_profiles`, DB yang sama) |
| `db/blog_drafts_store.py` | File-based store for blog drafts (`output/<brand>/blog_drafts/<batch_id>/`) — review/publish flow |

### Output Structure

Generated content per brand: `output/<brand>/content/<page>.json` + images. The brand slug matches CLI `--brand` / Web UI field.

### WordPress Deploy Architecture

Pages carry 5 Elementor meta fields (`_elementor_data`, `_elementor_edit_mode`, `_elementor_template_type`, `_elementor_version`, `_elementor_page_settings`). Global header/footer deploy once as `elementskit_template` CPT — not embedded per-page. Smart Slider 3 hero imports via the custom PHP bridge plugin.

Four custom PHP plugins (in `wordpress-plugins/`): `iaawg-elementskit-rest-bridge.php`, `iaawg-smartslider-bridge.php`, `iaawg-elementor-css-regen.php` are required for full website deploy; `iaawg-yoast-rest-bridge.php` is an optional fallback for the blog pipeline (see Blog Deploy section). Blog Autopost works without any plugins using only native WordPress REST API.

**Blog page (posts archive):** On a full (non-append) deploy, `main.py::run_pipeline()` creates a plain WordPress page (title "Blog", slug `blog`, no Elementor content — `page_layout: default` so the theme still renders global header/footer) and calls `WordPressClient.set_blog_page(page_id)` to set it as `page_for_posts`. WordPress then renders that page as the standard latest-posts archive, listing whatever the Blog Autopost pipeline has published — no custom Elementor post-grid widget needed. The nav menu gets a "Blog" item (order 4, between Produk and Kontak) in `WordPressClient.create_menu_items()`, added only if the Blog page was created successfully (`page_links["blog"]` non-empty) so a failed create never leaves a dead nav link. Skipped entirely in `append_mode`, same as the other one-time deploy steps (CF7, Smart Slider, static pages, header/footer).

**Blog Review & Publish flow:** `blog/generate` no longer deploys straight to WordPress — it only produces a draft batch persisted via `db/blog_drafts_store.py` (`output/<brand>/blog_drafts/<batch_id>/batch.json`). The operator reviews/edits articles (WYSIWYG) and optionally uploads a custom featured image per article at `/blog/review/{batch_id}`, then triggers the actual WordPress publish from `POST /blog/draft/{batch_id}/publish`, which calls `publish_reviewed_articles()` in `wordpress/blog_deploy.py`. Routes: `/blog/drafts` (list), `/blog/review/{batch_id}` (editor page), `/blog/draft/{batch_id}` (GET full draft JSON), `/blog/draft/{batch_id}/{article_id}` (POST field edits — allowed fields: `title`, `seo_title`, `slug`, `tags`, `meta_description`, `content`, `excerpt`), `/blog/draft/{batch_id}/{article_id}/image` (POST custom image upload). WP credentials are never persisted in the draft — re-entered by the operator at publish time. Publish can be partial (a subset of `article_ids`); each article's status flips to `"published"` individually in `batch.json`.

**Route registration order matters:** `/blog/draft/{batch_id}/publish` must be registered before `/blog/draft/{batch_id}/{article_id}` — Starlette matches paths by registration order, not specificity, so the reverse order would catch `.../publish` as `article_id="publish"`.

### Key Constraints

- `MAX_PRODUCTS` (default 5) caps how many product pages are generated per brand — adjustable via `/settings` UI.
- Blog batch capped at 15 articles. Budget ~3 LLM calls per article in practice (1 generate + up to `MAX_EXPAND_ATTEMPTS` expands), plus 1 topic call for the whole batch — see the length note below.
- Blog material is **split per source** before article generation (`split_material_sources()` in `content/blog_generator.py`). The topic pass sees the whole blob (all reference URLs); each article call receives only the shared material (homepage + manual paste) plus the single `=== REFERENSI (url) ===` block its topic is anchored to. Routing uses the topic's `source_url` field, falling back to least-used-source assignment when the LLM omits or invents it. Budgets: `SHARED_MATERIAL_CHARS` 4000 / `TOPIC_MATERIAL_CHARS` 6000 / `EXPAND_MATERIAL_CHARS` 3000, and `SHARED_ONLY_MATERIAL_CHARS` 8000 when no reference URL exists (so homepage-only or manual-only batches behave exactly as before).
- `ARTICLE_GENERATION_PROMPT` is ordered **invariant-first**: rules, shared material, and link candidates at the top; the per-article brief (`title`/`angle`/`summary`/`material_anchor`) and its specific source material at the very bottom. This keeps a ~4.5k-token prefix byte-identical across every article in a batch so provider prompt caching applies. Do not move per-article placeholders back up into the header — that silently defeats caching.
- Both pipelines cannot run concurrently — `website_is_running_getter` guard in blog routes.
- Scraper uses Playwright (Chromium headless); retries 3× with 500-char minimum content threshold.
- Blog generation requires at least 1 external (outbound) reference link (`external_links` form field) — enforced server-side in `/blog/generate`, used as mandatory outbound link per article. Each article must also carry ≥1 internal (inbound) link; `_has_internal_link` / `_has_external_link` flags are surfaced in `/blog/status`.
- Each generated article gets an automatic CTA box appended toward the Kontak page. The CTA is **not** stored permanently in `article["content"]`; it's appended at deploy/publish time in `blog_deploy.py` (`_build_cta_block`, using `article["cta_headline"]`/`cta_button_text`/`cta_url`) — keep this in mind if you fetch `content` from a draft and expect the CTA to be included.
- **Article length is controlled by block count, not word-count targets.** `gpt-4.1-mini` ignores per-section word counts in the prompt: raising them from 130 → 170 words made first-pass output *shorter* (710/806 → 695/760 words), and every constraint added to `ARTICLE_GENERATION_PROMPT` shrank it further (down to ~460 words). What the model does obey is structure count and explicit content obligations. So `TOPIC_GENERATION_PROMPT` emits an `outline` per topic (exactly 5 H2 headings, each with 2-3 concrete `isi` points and a `format` of `list`/`paragraf`), rendered by `_format_outline()` in `content/blog_generator.py` and passed to the article prompt as `{outline}`. Do not "fix" length by adding more rules or bigger numbers to the article prompt — that has been tried four times and consistently backfires.
- Two outline fields exist to kill fix-up passes, not for style: requiring the main keyword in ≥1 outline H2 removes the `SEO_FIX_PROMPT` call, and `format: "list"` on ≥2 sections removes the scannability problem. Both are satisfied by construction in the topic call (1 per batch) instead of costing 1 LLM call per article.
- `MIN_ARTICLE_WORDS` 850 / `MAX_ARTICLE_WORDS` 1050 bracket a ~900-word target. First pass reliably lands below the floor, so the expand pass in `generate_article()` runs on nearly every article by design — that is the cheapest route to 900 words on this model (~Rp 174/article; `gpt-4.1` would be 1 call but ~2× the cost). `MAX_ARTICLE_WORDS` only warns; it never truncates, since cutting HTML mid-article would break the structure.
- `main_keyword` doubles as the Yoast/AIOSEO focus keyphrase for every article in a batch — empty `main_keyword` skips SEO meta fields entirely rather than sending blank ones.

---

## Conventions and Patterns

### Elementor JSON Builder (`wordpress/elementor_builder.py`)

Every Elementor node is built from four low-level primitives:
- `_section(settings, columns)` → section node
- `_column(width_pct, elements)` → column node
- `_widget(wtype, settings)` → any widget
- `_id()` → `uuid4().hex[:8]` — every node must have a unique id

Higher-level helpers wrap `_widget`: `_heading()`, `_text()`, `_button()`, `_image()`, `_spacer()`, `_divider()`, `_icon_widget()`. Use these instead of calling `_widget` directly.

Color manipulation uses `_darken(hex, pct)` and `_lighten(hex, pct)` — used for generating tinted variants from `primary_color`.

Each public builder function (`build_home`, `build_solusi`, `build_product_page`, etc.) returns a `str` — the JSON-serialized Elementor data ready for the `_elementor_data` meta field.

**Adding a new page type:** implement `build_<page>(data, primary_color, ...) -> str` using the primitives above, then pass the result as `elementor_json` to `client.create_page()`.

### WordPress Client (`wordpress/client.py`)

- `WordPressClient.__init__` accepts `url/username/app_password` explicitly, or falls back to `settings.*` — the explicit path is used for multi-tenant deploys from Web UI.
- `create_page(elementor_json=...)` injects all 5 Elementor meta fields when the argument is provided; omit it for plain HTML pages.
- `_elementor_page_settings` must be `{"page_layout": "default"}` (not `"elementor_canvas"`) — `"default"` lets ElementsKit inject global header/footer.
- Token usage is emitted on stdout as `[TOKEN_USAGE] prompt_tokens: N | completion_tokens: N` — `web.py`'s `LogCaptureStream` parses this exact format to update the UI counters. Never change this format without updating the parser.

### Progress Bar Contract (`web.py` — `LogCaptureStream`)

The Web UI progress bar advances by scanning `print()` output for specific uppercase substrings. When adding new pipeline phases, emit progress-marker prints in this format to keep the bar accurate:

| Print contains | Progress |
|---|---|
| `"MEMPROSES HALAMAN: HOME"` | 10% |
| `"MEMPROSES HALAMAN: SOLUSI"` | 20% |
| `"MEMPROSES HALAMAN: CONTACT"` | 28% |
| `"MEMPROSES URL PRODUK"` | 32% |
| `"MEMPROSES VISUAL UNTUK HALAMAN: HOME"` | 40% |
| `"MENDEPLOY HALAMAN: HOME"` | 75% |
| `"SELURUH PIPELINE" + "BERHASIL SELESAI!"` | 100% |

### Adding a New Web Route

Routes that belong to `web.py` (website pipeline): add directly to `web.py`.  
Routes for a new secondary pipeline: create a `web_<name>_routes.py` module with a `register_<name>_routes(app, ...)` function, then call it in `web.py` after `app = FastAPI(...)` and before `register_blog_routes`. Pass `website_is_running_getter=lambda: is_running` to prevent concurrent pipeline execution.

The header nav in all four pages (`/`, `/blog`, `/settings`, `/profiles`) must be kept in sync manually — it is hardcoded HTML in each page's `_FORM_HTML` / `_SETTINGS_HTML` / `_PROFILES_HTML` string or `index_page()`. When adding a new tab, update all four. (`/blog/drafts` and `/blog/review/{id}` use a plain back-link, not the nav.)

### LLM Prompt Conventions (`content/templates/prompts.py`)

- All prompts output **raw JSON only** — no markdown triple-backtick fences. The system instruction explicitly forbids them. Parser will fail if fences are present.
- Prompts use `{raw_data}`, `{brand_name}`, `{max_products}` as `str.format()` placeholders.
- `PRODUCT_CATALOG_PROMPT` deliberately omits `description/use_cases/why_choose/target_user` to save tokens — catalog cards only render `name/tagline/key_specs/key_features[:3]`.
- CTA copy rules: brand is the subject/solution — never `"Hubungi [Brand]"`, never `"Kami"` as the brand voice. These rules are in `SYSTEM_INSTRUCTION` and enforced by prompt wording in each `PAGE_PROMPTS` entry.

### Local Preview Engine (`visual/preview_templates.py`)

Template auto-selection (`select_template()`) scores the full content text pool against keyword lists for three templates (prestige/clarity/momentum). Tie-breaks: prestige > clarity > momentum. The function accepts `data` dict with keys matching the 4 static page slugs (`home`, `produk`, `solusi`, `contact`).

`generate_preview_html(brand, data, primary_color, max_products, template_name)` is called from `web.py:generate_local_preview_html()`. An empty `template_name` triggers auto-selection. The function writes a self-contained Tailwind HTML file to `output/<brand>/content/preview_lokal.html`.

### Profil Website (`db/brand_profiles_store.py`)

Dropdown "Pilih Website" di `/blog` dan "Website Tujuan" di panel publish halaman review mengambil datanya dari tabel `brand_profiles` — 1 baris per subdomain brand, berisi seluruh isian form Blog (brand_name, keyword, sumber materi, link eksternal) plus kredensial WordPress dan default `n_articles`/`llm_chain`/`include_featured_image`.

- **`wp_app_password` DISIMPAN** di tabel ini, berbeda dengan `db/blog_drafts_store.py` yang tidak boleh menyimpan kredensial apa pun ke `batch.json`. Alasannya: semua site yang dikelola adalah subdomain internal perusahaan sendiri (distributor multi-brand), dan `iaawg_settings.db` sudah di-gitignore sejak awal sehingga tidak pernah ikut repo. Folder draft bisa dipindah/di-share per batch, file .db tidak.
- Password tidak pernah ikut di `GET /api/profiles` — listing hanya membawa flag `has_wp_app_password`. Nilai aslinya diambil terpisah lewat `GET /api/profiles/{id}/credentials`, dipanggil hanya saat operator benar-benar memilih sebuah profil.
- Pada `update_profile()`, `wp_app_password` kosong berarti **"jangan diubah"**, bukan "hapus" — supaya form edit dan checkbox "Simpan sebagai profil" di form Blog bisa mengirim field password kosong tanpa menghapus yang tersimpan.
- `brand_name` unik case-insensitive (unique index `LOWER(brand_name)`), jadi "Zecurion" dan "zecurion" tidak jadi 2 profil. `upsert_by_brand()` dipakai checkbox "Simpan sebagai profil" — create kalau brand belum ada, update kalau sudah.
- **Urutan registrasi rute penting:** `POST /api/profiles/upsert` harus terdaftar sebelum `POST /api/profiles/{profile_id}` — gotcha yang sama seperti `/blog/draft/{batch_id}/publish`, kalau dibalik "upsert" ditangkap sebagai `profile_id` dan gagal konversi int (422).
- Profil bersifat per-laptop (DB tidak ikut repo). Pindah laptop = copy `iaawg_settings.db`. Tidak ada fitur export/import — sengaja, supaya kredensial tidak pernah keluar dalam bentuk file JSON.
- Memilih profil TIDAK mencentang "Simpan sebagai profil" secara otomatis, supaya perubahan yang cuma berlaku untuk satu batch (mis. keyword khusus) tidak tertulis balik ke profil.

### Blog Deploy (`wordpress/blog_deploy.py`)

- `upload_featured_image()` returns an attachment **ID** (int), not a URL — `create_page`/`upload_media` in `client.py` return URLs. The blog deploy module handles this distinction internally.
- `create_blog_post()` sets `status: "future"` only when `publish_date > datetime.now()`. Past or `None` dates publish immediately.
- `deploy_blog_batch()` (legacy direct-deploy path from `/blog/generate`) and `publish_reviewed_articles()` (used by the Review & Publish flow, see above) both call `ensure_category` once for the whole batch and `ensure_tags` per article. Both use a search-first, create-if-missing pattern with a `term_exists` 400-error fallback.
- `publish_reviewed_articles()` resolves a featured image from `article["featured_image"]`: `{"type": "stock", "url": ...}` downloads via HTTP same as the legacy path, `{"type": "custom", "filename": ...}` reads the file from `images_dir` (an operator upload from the review page, see `db/blog_drafts_store.py`). It returns `{"id": article_id, "wp": <create_blog_post result>}` per article (not index-based) so the caller can flip `"published"` status per-article, since publish can be partial.
- SEO meta: `create_blog_post()` sends `_yoast_wpseo_metadesc`/`_yoast_wpseo_focuskw`/`_yoast_wpseo_title` and an `aioseo_meta_data` object (`title`/`description`/`keyphrases.focus.keyphrase`) directly on the `wp/v2/posts` payload — modern Yoast/AIOSEO register these fields for REST natively (verified 2026-09), no plugin needed for either. `wordpress-plugins/iaawg-yoast-rest-bridge.php` exists only as an **optional fallback** for older Yoast installs that haven't registered the REST fields themselves; WordPress silently drops unknown meta keys, so this is safe to leave inactive.

### AI-Generated Featured Image (`visual/image_fetch.py::generate_ai_image`)

- Opt-in, per-article, triggered manually by the operator from the review page (`/blog/review/{batch_id}`) — never part of the default batch generation, since it's a real per-image cost (OpenAI `gpt-image-1`, landscape 1536x1024 only). `config/settings.py::calc_image_cost()`/`IMAGE_PRICE_USD` gives the USD/IDR estimate shown in the UI confirm dialog before the request fires; `GET /blog/image-cost` serves that table to the frontend.
- The operator sees and can edit the prompt (`.f-ai-prompt` textarea, pre-filled by `defaultAiPrompt()` in the review page JS) before clicking generate. The default prompt template explicitly forbids on-image text/lettering (`no text, no letters, no words, no typography`) — an earlier version passed the article title as literal text to render and `gpt-image-1` produced garbled misspelled text baked into the image; title/meta_description are now framed only as topic context, never as text to render.
- Reuses `OPENAI_API_KEY` from Settings — no separate API key needed. Generated bytes are saved to the same `images_dir` as manual uploads and set as `article["featured_image"] = {"type": "custom", "filename": ...}`, so `publish_reviewed_articles()` needs no special-casing — the existing custom-image path (including PNG mime-type detection) already handles it.
- Endpoint: `POST /blog/draft/{batch_id}/{article_id}/image/generate` (form fields `quality` low/medium/high, `prompt`) — registered in `web_blog_routes.py` alongside the existing manual-upload endpoint.

### Gotchas Not Obvious From README

1. **`sys.stdout` is replaced during pipeline runs.** `web.py` swaps `sys.stdout` with `LogCaptureStream` for the duration of `pipeline_wrapper`. Any `print()` call during this window goes to the log buffer, not the terminal. The original `sys.stdout` is restored in `finally`. Don't `import sys; sys.stdout.write(...)` inside pipeline code — use `print()`.

2. **`_elementor_page_settings` must be a Python dict, not a JSON string.** The httpx client will serialize it. Passing `json.dumps(...)` here would double-encode it.

3. **Append Mode skips local preview generation.** `web.py` checks `if not append_mode:` before calling `generate_local_preview_html()`. The preview file will be stale after an append — this is intentional.

4. **`WordPressClient` in `client.py` still reads `settings.*` directly** (not `get_setting()`) in its `__init__` fallback. The explicit constructor args take precedence in multi-tenant deploys, so this only matters for pure `.env` CLI usage.

5. **Blog routes are registered before the `StaticFiles` mount** in `web.py`. If you add a route with a path prefix that collides with `"/output"`, the static mount wins.

6. **Catalog Mode is blocked in Append Mode** at the `/generate` endpoint validation level — server returns 400. The UI also forces Individual Mode when Append Mode is checked, but always enforce at the server.

7. **Blog drafts on disk never carry WordPress credentials.** `db/blog_drafts_store.py::batch.json` stores article content/status only — `wp_url`/`wp_username`/`wp_app_password` are re-submitted by the operator with every `POST /blog/draft/{batch_id}/publish` call, not persisted anywhere between generate and publish.

8. **CTA block is appended at deploy/publish time, not stored in `article["content"]`.** If you read a draft's `content` field directly (e.g. for a word count or a diff), it won't include the CTA box — it's added by `_build_cta_block()` in `blog_deploy.py` right before the WordPress API call.
