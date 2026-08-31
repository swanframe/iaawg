# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Project Is

**iAAWG** (iLogo AI Auto Website Generator) — two-pipeline AI automation system for PT. iLogo Infralogy Indonesia:

1. **Website Generator** — scrapes a brand's public website → generates localized Indonesian content (Beranda/Solusi/Produk/Kontak) → deploys Elementor-compatible pages to WordPress via REST API.
2. **Blog Autopost Generator** — generates SEO articles (1500+ words each) in batches from brand material, with optional WordPress scheduled publishing.

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

### Output Structure

Generated content per brand: `output/<brand>/content/<page>.json` + images. The brand slug matches CLI `--brand` / Web UI field.

### WordPress Deploy Architecture

Pages carry 5 Elementor meta fields (`_elementor_data`, `_elementor_edit_mode`, `_elementor_template_type`, `_elementor_version`, `_elementor_page_settings`). Global header/footer deploy once as `elementskit_template` CPT — not embedded per-page. Smart Slider 3 hero imports via the custom PHP bridge plugin.

Three custom PHP plugins (in `wordpress-plugins/`) are required for full deploy; Blog Autopost works without them using only native WordPress REST API.

**Blog page (posts archive):** On a full (non-append) deploy, `main.py::run_pipeline()` creates a plain WordPress page (title "Blog", slug `blog`, no Elementor content — `page_layout: default` so the theme still renders global header/footer) and calls `WordPressClient.set_blog_page(page_id)` to set it as `page_for_posts`. WordPress then renders that page as the standard latest-posts archive, listing whatever the Blog Autopost pipeline has published — no custom Elementor post-grid widget needed. The nav menu gets a "Blog" item (order 4, between Produk and Kontak) in `WordPressClient.create_menu_items()`, added only if the Blog page was created successfully (`page_links["blog"]` non-empty) so a failed create never leaves a dead nav link. Skipped entirely in `append_mode`, same as the other one-time deploy steps (CF7, Smart Slider, static pages, header/footer).

### Key Constraints

- `MAX_PRODUCTS` (default 5) caps how many product pages are generated per brand — adjustable via `/settings` UI.
- Blog batch capped at 15 articles; each article is 1 LLM call.
- `raw_data` injected into blog prompts is capped at 8000 chars (manual content) / 4000 chars per scraped URL.
- Both pipelines cannot run concurrently — `website_is_running_getter` guard in blog routes.
- Scraper uses Playwright (Chromium headless); retries 3× with 500-char minimum content threshold.

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

The header nav in all three pages (`/`, `/blog`, `/settings`) must be kept in sync manually — it is hardcoded HTML in each page's `_FORM_HTML` / `_SETTINGS_HTML` string or `index_page()`. When adding a new tab, update all three.

### LLM Prompt Conventions (`content/templates/prompts.py`)

- All prompts output **raw JSON only** — no markdown triple-backtick fences. The system instruction explicitly forbids them. Parser will fail if fences are present.
- Prompts use `{raw_data}`, `{brand_name}`, `{max_products}` as `str.format()` placeholders.
- `PRODUCT_CATALOG_PROMPT` deliberately omits `description/use_cases/why_choose/target_user` to save tokens — catalog cards only render `name/tagline/key_specs/key_features[:3]`.
- CTA copy rules: brand is the subject/solution — never `"Hubungi [Brand]"`, never `"Kami"` as the brand voice. These rules are in `SYSTEM_INSTRUCTION` and enforced by prompt wording in each `PAGE_PROMPTS` entry.

### Local Preview Engine (`visual/preview_templates.py`)

Template auto-selection (`select_template()`) scores the full content text pool against keyword lists for three templates (prestige/clarity/momentum). Tie-breaks: prestige > clarity > momentum. The function accepts `data` dict with keys matching the 4 static page slugs (`home`, `produk`, `solusi`, `contact`).

`generate_preview_html(brand, data, primary_color, max_products, template_name)` is called from `web.py:generate_local_preview_html()`. An empty `template_name` triggers auto-selection. The function writes a self-contained Tailwind HTML file to `output/<brand>/content/preview_lokal.html`.

### Blog Deploy (`wordpress/blog_deploy.py`)

- `upload_featured_image()` returns an attachment **ID** (int), not a URL — `create_page`/`upload_media` in `client.py` return URLs. The blog deploy module handles this distinction internally.
- `create_blog_post()` sets `status: "future"` only when `publish_date > datetime.now()`. Past or `None` dates publish immediately.
- `deploy_blog_batch()` calls `ensure_category` once for the whole batch and `ensure_tags` per article. Both use a search-first, create-if-missing pattern with a `term_exists` 400-error fallback.
- Meta description is sent to both `_yoast_wpseo_metadesc` and `rank_math_description`. WordPress silently ignores unknown meta keys, so this is safe even without the plugins.

### Gotchas Not Obvious From README

1. **`sys.stdout` is replaced during pipeline runs.** `web.py` swaps `sys.stdout` with `LogCaptureStream` for the duration of `pipeline_wrapper`. Any `print()` call during this window goes to the log buffer, not the terminal. The original `sys.stdout` is restored in `finally`. Don't `import sys; sys.stdout.write(...)` inside pipeline code — use `print()`.

2. **`_elementor_page_settings` must be a Python dict, not a JSON string.** The httpx client will serialize it. Passing `json.dumps(...)` here would double-encode it.

3. **Append Mode skips local preview generation.** `web.py` checks `if not append_mode:` before calling `generate_local_preview_html()`. The preview file will be stale after an append — this is intentional.

4. **`WordPressClient` in `client.py` still reads `settings.*` directly** (not `get_setting()`) in its `__init__` fallback. The explicit constructor args take precedence in multi-tenant deploys, so this only matters for pure `.env` CLI usage.

5. **Blog routes are registered before the `StaticFiles` mount** in `web.py`. If you add a route with a path prefix that collides with `"/output"`, the static mount wins.

6. **Catalog Mode is blocked in Append Mode** at the `/generate` endpoint validation level — server returns 400. The UI also forces Individual Mode when Append Mode is checked, but always enforce at the server.
