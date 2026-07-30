# -*- coding: utf-8 -*-
from datetime import datetime
from collections import defaultdict

"""
visual/preview_templates.py
===========================
Multi-Template Preview Engine untuk iAAWG.

Tiga template layout profesional & corporate yang dipilih otomatis
berdasarkan karakteristik konten brand, atau manual oleh operator.

Template yang tersedia:
  - "prestige"  : Light/putih, authority hero besar, aksen warna brand di kiri.
                  Kesan: senior, trusted, enterprise. Cocok: Cybersecurity, Compliance, DLP, SIEM.
  - "clarity"   : Dua kolom bersih, card dengan angka besar, whitespace lega.
                  Kesan: modern, efisien, SaaS. Cocok: Cloud, ERP, Backup, Analytics, SaaS.
  - "momentum"  : Hero full-width dengan overlay brand halus, bento-grid solusi.
                  Kesan: berenergi, teknis, infrastruktur. Cocok: Network, SD-WAN, Monitoring, AV.

Halaman Produk — Catalog Grid System:
  Saat ada product_urls (Mode B), tab-produk menampilkan catalog grid card
  yang dikelompokkan per category. Klik card → detail produk individual.
  Tombol "← Kembali" di detail view membawa kembali ke catalog grid.
  Saat tidak ada category atau semua produk sama category → flat grid tanpa header.
"""

# =============================================================================
# SELECTOR OTOMATIS
# =============================================================================

def select_template(data: dict, brand: str) -> str:
    """
    Memilih nama template berdasarkan keyword konten brand.
    Mengembalikan: 'prestige' | 'clarity' | 'momentum'
    """
    text_pool = " ".join([
        brand,
        data.get("home", {}).get("hero_headline", ""),
        data.get("home", {}).get("hero_subheadline", ""),
        data.get("home", {}).get("about_summary", ""),
        data.get("solusi", {}).get("title", ""),
        data.get("solusi", {}).get("intro", ""),
        " ".join(data.get("home", {}).get("seo_keywords", [])),
        " ".join([s.get("target", "") for s in data.get("solusi", {}).get("solutions_list", [])]),
        " ".join([p.get("name", "") + " " + p.get("tagline", "") for p in data.get("produk", {}).get("products_list", [])]),
    ]).lower()

    prestige_keywords = [
        "security", "cyber", "threat", "firewall", "endpoint", "ransomware",
        "vulnerability", "siem", "soc", "malware", "zero trust", "dlp",
        "encryption", "ids", "ips", "pentest", "forensic", "compliance",
        "keamanan", "ancaman", "perlindungan data", "kepatuhan", "governance",
        "risk", "audit", "regulatory", "data protection",
    ]
    clarity_keywords = [
        "cloud", "saas", "erp", "crm", "software", "platform", "analytics",
        "dashboard", "automation", "workflow", "collaboration", "productivity",
        "backup", "storage", "database", "virtualization", "kubernetes",
        "perangkat lunak", "otomasi", "analitik", "penyimpanan", "manajemen",
        "enterprise resource", "business intelligence", "reporting",
    ]
    momentum_keywords = [
        "network", "networking", "wireless", "wifi", "sd-wan", "wan",
        "monitoring", "observability", "noc", "bandwidth", "routing", "switching",
        "access point", "lan", "infrastructure", "data center", "ucc",
        "unified communication", "video conferencing", "av", "audio visual",
        "jaringan", "pemantauan", "pusat data", "konektivitas", "visibility",
    ]

    score_p = sum(1 for kw in prestige_keywords if kw in text_pool)
    score_c = sum(1 for kw in clarity_keywords if kw in text_pool)
    score_m = sum(1 for kw in momentum_keywords if kw in text_pool)

    scores = {"prestige": score_p, "clarity": score_c, "momentum": score_m}
    winner = max(scores, key=scores.get)

    if scores[winner] == 0:
        return "prestige"

    print(f"[Template Selector] Skor: {scores} → dipilih: '{winner}'")
    return winner


# =============================================================================
# HELPERS BERSAMA
# =============================================================================

def _hex_to_hsl(hex_color: str) -> tuple:
    """Konversi HEX ke HSL (hue, sat%, light%) — digunakan untuk variasi warna."""
    hx = hex_color.lstrip('#')
    if len(hx) == 3:
        hx = ''.join([c * 2 for c in hx])
    r, g, b = int(hx[0:2], 16) / 255.0, int(hx[2:4], 16) / 255.0, int(hx[4:6], 16) / 255.0
    mx, mn = max(r, g, b), min(r, g, b)
    d = mx - mn
    l = (mx + mn) / 2
    s = 0 if d == 0 else d / (1 - abs(2 * l - 1))
    if d == 0:
        h = 0
    elif mx == r:
        h = (60 * ((g - b) / d) + 360) % 360
    elif mx == g:
        h = (60 * ((b - r) / d) + 120) % 360
    else:
        h = (60 * ((r - g) / d) + 240) % 360
    return int(round(h)), int(round(s * 100)), int(round(l * 100))

def _css_vars(h: int, s: int) -> str:
    """Generate CSS custom properties dari hue dan saturation brand."""
    s_ui = max(40, min(s, 75))
    return f"""
        :root {{
            --brand-h:   {h};
            --brand-s:   {s_ui}%;
            --brand-50:  hsl({h},{s_ui}%,96%);
            --brand-100: hsl({h},{s_ui}%,91%);
            --brand-200: hsl({h},{s_ui}%,82%);
            --brand-400: hsl({h},{s_ui}%,60%);
            --brand-500: hsl({h},{s_ui}%,48%);
            --brand-600: hsl({h},{s_ui}%,38%);
            --brand-700: hsl({h},{s_ui}%,28%);
            --brand-800: hsl({h},{s_ui}%,18%);
        }}"""

def _asset(b: str, page: str, kind: str) -> str:
    return f"/output/{b}/visual/{b}_{page}_{kind}.jpg"

def _prod_asset(b: str, slug: str, kind: str) -> str:
    return f"/output/{b}/visual/{b}_{slug}_{kind}.jpg"

def _paras(text: str, cls: str = "") -> str:
    """Render teks multi-paragraf (dipisah newline) sebagai tag <p>."""
    parts = [p.strip() for p in text.split("\n") if p.strip()]
    return "".join(f'<p class="{cls}">{p}</p>' for p in parts)

def _tailwind_config_script() -> str:
    return """
    <script>
        tailwind.config = {
            theme: {
                extend: {
                    colors: {
                        brand: {
                            50:  'var(--brand-50)',
                            100: 'var(--brand-100)',
                            200: 'var(--brand-200)',
                            400: 'var(--brand-400)',
                            500: 'var(--brand-500)',
                            600: 'var(--brand-600)',
                            700: 'var(--brand-700)',
                            800: 'var(--brand-800)',
                        }
                    }
                }
            }
        }
    </script>"""

def _shared_head_meta(brand: str, subtitle: str = "") -> str:
    desc = subtitle or "IT Solutions & Infrastructure"
    return f"""
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{brand.capitalize()} Indonesia | {desc}</title>
    <link rel="icon" type="image/png" href="https://img.icons8.com/?size=100&id=e5sopTWYpy6o&format=png&color=000000">
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://unpkg.com/lucide@latest"></script>"""

def _shared_scripts() -> str:
    """
    JavaScript navigasi — digunakan oleh semua template.

    switchTab(tabId)         : navigasi antar halaman utama (Beranda/Produk/Solusi/Kontak)
    switchProdukTab(slug)    : tampilkan panel detail produk tertentu (dalam detail view)
    showProductDetail(slug)  : dari catalog grid → masuk ke detail produk
    showCatalog()            : dari detail produk → kembali ke catalog grid
    """
    return """
    <script>
        function switchTab(tabId) {
            document.querySelectorAll('.tab-content').forEach(el => {
                el.classList.remove('active');
                el.style.display = 'none';
            });
            const target = document.getElementById('tab-' + tabId);
            if (target) {
                target.classList.add('active');
                target.style.display = 'block';
            }
            document.querySelectorAll('.tab-btn').forEach(btn => {
                btn.setAttribute('data-active', 'false');
            });
            const activeBtn = document.getElementById('btn-' + tabId);
            if (activeBtn) activeBtn.setAttribute('data-active', 'true');

            // Saat kembali ke tab Produk, selalu tampilkan catalog grid dulu
            if (tabId === 'produk') {
                const overview = document.getElementById('catalog-overview');
                const detail   = document.getElementById('catalog-detail');
                if (overview) overview.style.display = 'block';
                if (detail)   detail.style.display   = 'none';
            }

            window.scrollTo({ top: 0, behavior: 'smooth' });
        }

        function switchProdukTab(slug) {
            // Tampilkan panel detail produk yang dipilih, sembunyikan lainnya
            document.querySelectorAll('.produk-tab-content').forEach(el => {
                el.style.display = 'none';
            });
            const target = document.getElementById('produk-tab-' + slug);
            if (target) target.style.display = 'block';
        }

        function showProductDetail(slug) {
            // Catalog grid → Detail produk
            const overview = document.getElementById('catalog-overview');
            const detail   = document.getElementById('catalog-detail');
            if (overview) overview.style.display = 'none';
            if (detail)   detail.style.display   = 'block';
            switchProdukTab(slug);
            window.scrollTo({ top: 0, behavior: 'smooth' });
        }

        function showCatalog() {
            // Detail produk → Catalog grid
            const overview = document.getElementById('catalog-overview');
            const detail   = document.getElementById('catalog-detail');
            if (overview) overview.style.display = 'block';
            if (detail)   detail.style.display   = 'none';
            window.scrollTo({ top: 0, behavior: 'smooth' });
        }

        lucide.createIcons();
    </script>"""

def _footer_html(brand: str) -> str:
    return f"""
    <footer class="bg-slate-900 text-slate-400 pt-16 pb-8 px-6">
        <div class="max-w-7xl mx-auto grid grid-cols-1 md:grid-cols-3 gap-12 mb-12">
            <div>
                <div class="flex items-center gap-3 mb-5">
                    <div class="w-9 h-9 bg-brand-600 rounded-lg flex items-center justify-center
                                text-white font-black text-xs">{brand[:2].upper()}</div>
                    <span class="font-bold text-white text-lg">{brand.capitalize()} Indonesia</span>
                </div>
                <p class="text-sm leading-relaxed">
                    {brand.capitalize()} Indonesia adalah bagian dari PT. iLogo Infralogy Indonesia, yang bertindak sebagai partner resmi {brand.capitalize()}. Kami berperan sebagai distributor sekaligus penyedia layanan berbagai produk Infrastruktur IT dan Cybersecurity terbaik di Indonesia.
                </p>
            </div>
            <div>
                <h4 class="text-slate-200 font-semibold mb-5 text-sm uppercase tracking-wider">
                    Sales &amp; Marketing
                </h4>
                <ul class="space-y-3 text-sm">
                    <li class="flex items-start gap-2.5">
                        <i data-lucide="map-pin" class="w-4 h-4 text-brand-400 flex-shrink-0 mt-0.5"></i>
                        Jl. Kebon Jeruk Raya Villa Kebon Jeruk Office F1, Jakarta
                    </li>
                    <li class="flex items-center gap-2.5">
                        <i data-lucide="mail" class="w-4 h-4 text-brand-400 flex-shrink-0"></i>
                        {brand.lower()}@ilogoindonesia.com
                    </li>
                </ul>
            </div>
            <div>
                <h4 class="text-slate-200 font-semibold mb-5 text-sm uppercase tracking-wider">
                    Support Center
                </h4>
                <p class="text-sm mb-6 flex items-start gap-2.5">
                    <i data-lucide="building-2" class="w-4 h-4 text-brand-400 flex-shrink-0 mt-0.5"></i>
                    AKR Tower – 9th Floor, Jl. Panjang No. 5, Kebon Jeruk, Jakarta
                </p>
            </div>
        </div>
        <div class="max-w-7xl mx-auto border-t border-slate-800 pt-8 flex flex-col
                    md:flex-row items-center justify-between gap-3">
            <p class="text-xs text-slate-600">
                © {datetime.now().year} {brand.capitalize()} Indonesia. All Rights Reserved.
            </p>
            <p class="text-xs text-slate-700">
                Generated by <span class="text-brand-600 font-semibold">iAAWG</span>
            </p>
        </div>
    </footer>"""


# =============================================================================
# CATALOG GRID — Shared helper, dipanggil dari semua 3 template
#
# Logika:
#   1. Produk dikelompokkan berdasarkan field "category".
#   2. Jika semua produk punya category yang sama (atau tidak ada category),
#      grid ditampilkan flat tanpa section header.
#   3. Jika ada beberapa category berbeda, muncul section header per kelompok.
#   4. key_specs digunakan sebagai pill badge di tiap card.
#      Fallback: 3 kata pertama dari key_features jika key_specs kosong.
#   5. Klik card → showProductDetail(slug) → detail view produk individual.
# =============================================================================

def _catalog_grid_html(products_list: list, brand_lower: str, template: str) -> str:
    """
    Render catalog grid HTML untuk tab-produk.

    Args:
        products_list : list produk dari data["produk"]["products_list"]
        brand_lower   : nama brand lowercase (untuk path aset)
        template      : "prestige" | "clarity" | "momentum"

    Returns:
        HTML string catalog grid, siap dimasukkan ke #catalog-overview.
    """
    if not products_list:
        return "<p class='text-slate-400 text-sm py-16 text-center col-span-3'>Belum ada produk dalam katalog.</p>"

    # ── Kelompokkan berdasarkan category ─────────────────────────────────────
    groups = defaultdict(list)
    for prod in products_list:
        cat = (prod.get("category") or "").strip() or "Produk"
        groups[cat].append(prod)

    multi_cat = len(groups) > 1

    # ── Card builder per template ─────────────────────────────────────────────
    def _build_card(prod: dict, cat_name: str) -> str:
        name     = prod.get("name", "Produk")
        slug     = prod.get("slug", "produk")
        tagline  = prod.get("tagline", "")
        key_specs = prod.get("key_specs") or []

        # Fallback ke key_features jika key_specs belum ada (data lama)
        if not key_specs:
            raw_feats = prod.get("key_features", [])[:3]
            key_specs = [f.split("—")[0].split(":")[0].strip()[:35] for f in raw_feats]

        img_tag = (
            f'<img src="{_prod_asset(brand_lower, slug, "banner")}" '
            f'class="w-full h-full object-cover" '
            f'onerror="this.parentElement.style.background=\'#e2e8f0\'; this.style.display=\'none\'">'
        )

        if template == "prestige":
            specs_html = "".join(
                f'<span class="inline-block bg-slate-100 text-slate-500 text-xs '
                f'px-2.5 py-1 rounded-md font-medium leading-none">{sp}</span>'
                for sp in key_specs[:4]
            )
            return f"""
            <div onclick="showProductDetail('{slug}')"
                 class="bg-white rounded-2xl border border-slate-100 shadow-sm
                        hover:shadow-md hover:-translate-y-0.5 transition-all
                        duration-300 cursor-pointer overflow-hidden group"
                 style="border-top: 3px solid var(--brand-600);">
                <div class="h-44 bg-slate-100 overflow-hidden">
                    {img_tag}
                </div>
                <div class="p-5">
                    <p class="text-xs font-semibold uppercase tracking-wider mb-1"
                       style="color: var(--brand-600);">{cat_name}</p>
                    <h4 class="font-bold text-slate-900 text-base mb-1 leading-snug
                               group-hover:text-brand-700 transition-colors">{name}</h4>
                    <p class="text-slate-400 text-xs mb-4 leading-relaxed line-clamp-2">{tagline}</p>
                    <div class="flex flex-wrap gap-1.5">{specs_html}</div>
                    <div class="mt-4 flex items-center gap-1 text-xs font-semibold"
                         style="color: var(--brand-600);">
                        Lihat Detail
                        <i data-lucide="arrow-right" class="w-3.5 h-3.5"></i>
                    </div>
                </div>
            </div>"""

        elif template == "clarity":
            specs_html = "".join(
                f'<span class="inline-block bg-brand-50 text-brand-700 text-xs '
                f'px-2.5 py-1 rounded-md font-medium leading-none">{sp}</span>'
                for sp in key_specs[:4]
            )
            return f"""
            <div onclick="showProductDetail('{slug}')"
                 class="bg-white rounded-2xl border border-slate-100
                        hover:border-brand-200 hover:shadow-md transition-all
                        cursor-pointer overflow-hidden group">
                <div class="h-44 bg-slate-50 overflow-hidden">
                    {img_tag}
                </div>
                <div class="p-5">
                    <div class="flex items-center gap-2 mb-2">
                        <div class="h-0.5 w-4 rounded-full flex-shrink-0"
                             style="background: var(--brand-600);"></div>
                        <p class="text-xs font-medium" style="color: var(--brand-600);">{cat_name}</p>
                    </div>
                    <h4 class="font-bold text-slate-900 text-base mb-1 leading-snug">{name}</h4>
                    <p class="text-slate-400 text-xs mb-4 leading-relaxed line-clamp-2">{tagline}</p>
                    <div class="flex flex-wrap gap-1.5 mb-4">{specs_html}</div>
                    <div class="flex items-center gap-1 text-xs font-semibold"
                         style="color: var(--brand-600);">
                        Lihat Detail
                        <i data-lucide="chevron-right" class="w-3.5 h-3.5"></i>
                    </div>
                </div>
            </div>"""

        else:  # momentum
            specs_html = "".join(
                f'<span class="inline-block bg-slate-800 text-slate-300 text-xs '
                f'px-2.5 py-1 rounded-md font-medium leading-none">{sp}</span>'
                for sp in key_specs[:4]
            )
            return f"""
            <div onclick="showProductDetail('{slug}')"
                 class="bg-white rounded-2xl overflow-hidden shadow-sm
                        hover:shadow-md transition-all cursor-pointer group
                        border border-slate-100">
                <div class="h-2 w-full" style="background: var(--brand-600);"></div>
                <div class="h-40 bg-slate-900 overflow-hidden">
                    {img_tag}
                </div>
                <div class="p-5">
                    <p class="text-xs font-semibold uppercase tracking-wider mb-1"
                       style="color: var(--brand-500);">{cat_name}</p>
                    <h4 class="font-bold text-slate-900 text-base mb-1 leading-snug
                               group-hover:text-brand-600 transition-colors">{name}</h4>
                    <p class="text-slate-400 text-xs mb-4 leading-relaxed line-clamp-2">{tagline}</p>
                    <div class="flex flex-wrap gap-1.5 mb-4">{specs_html}</div>
                    <div class="flex items-center gap-1 text-xs font-semibold"
                         style="color: var(--brand-500);">
                        Lihat Detail
                        <i data-lucide="arrow-right" class="w-3.5 h-3.5"></i>
                    </div>
                </div>
            </div>"""

    # ── Susun grid ────────────────────────────────────────────────────────────
    html = ""
    for cat_name, prods in groups.items():
        if multi_cat:
            # Section header per category
            if template == "momentum":
                header_cls = "text-xs font-semibold uppercase tracking-widest mb-4 px-1 pb-3 border-b border-slate-200"
                header_style = "color: var(--brand-500);"
            else:
                header_cls = "text-xs font-semibold uppercase tracking-widest mb-4 px-1 pb-3 border-b border-slate-200"
                header_style = "color: var(--brand-600);"

            html += f"""
            <div class="mb-10">
                <h3 class="{header_cls}" style="{header_style}">{cat_name}</h3>
                <div class="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-5">
            """
        else:
            html += '<div class="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-5">'

        for prod in prods:
            html += _build_card(prod, cat_name)

        html += "</div>"
        if multi_cat:
            html += "</div>"

    return html


# =============================================================================
# TEMPLATE 1: PRESTIGE
# Cocok: Cybersecurity, Compliance, DLP, SIEM, Governance
# Karakter: Authority, trusted, senior enterprise — light background, bukan dark.
#   - Hero: putih bersih, heading sangat besar, left-border accent brand
#   - Stats bar di bawah hero (3 angka kunci)
#   - Produk: catalog grid card → klik → detail produk (sidebar diganti grid)
#   - Solusi: list dengan border-left brand, bukan grid gelap
# =============================================================================

def render_prestige(brand: str, data: dict, primary_color: str, max_products: int) -> str:
    h, s, l = _hex_to_hsl(primary_color)
    brand_lower = brand.lower()
    products_list = data.get("produk", {}).get("products_list", [])[:max_products]
    home = data.get("home", {})
    vps  = home.get("value_propositions", [])

    # --- Value propositions ---
    vp_icons = ["shield-check", "award", "lock-keyhole", "eye", "badge-check", "trending-up"]
    vp_html = ""
    for i, vp in enumerate(vps):
        icon = vp_icons[i % len(vp_icons)]
        vp_html += f"""
        <div class="bg-white rounded-2xl p-8 border border-slate-100 shadow-sm
                    hover:shadow-lg hover:-translate-y-0.5 transition-all duration-300 group">
            <div class="w-11 h-11 bg-brand-50 rounded-xl flex items-center justify-center
                        text-brand-600 mb-5 group-hover:bg-brand-600 group-hover:text-white
                        transition-colors duration-300">
                <i data-lucide="{icon}" class="w-5 h-5"></i>
            </div>
            <h3 class="text-base font-semibold text-slate-900 mb-2 leading-snug">
                {vp.get("title", f"Keunggulan {i+1}")}
            </h3>
            <p class="text-slate-500 text-sm leading-relaxed">{vp.get("description", "")}</p>
        </div>"""
    if not vp_html:
        vp_html = "<p class='text-slate-400 col-span-3 text-sm'>Data keunggulan belum tersedia.</p>"

    # --- Catalog grid (menggantikan sidebar nav) ---
    catalog_html = _catalog_grid_html(products_list, brand_lower, "prestige")

    # --- Product detail panels (unchanged) ---
    prod_content = ""
    for i, prod in enumerate(products_list):
        name = prod.get("name", f"Produk {i+1}")
        slug = prod.get("slug", f"produk-{i+1}")
        desc    = _paras(prod.get("description", ""), "text-slate-600 text-sm leading-relaxed mb-3")
        display = "block" if i == 0 else "none"

        feats_cards = "".join(
            f"<div class='flex items-start gap-3 bg-white rounded-xl p-4 border border-slate-100'>"
            f"<div class='w-7 h-7 rounded-lg flex items-center justify-center flex-shrink-0 mt-0.5'"
            f"     style='background:var(--brand-50);'>"
            f"<i data-lucide='check' class='w-4 h-4' style='color:var(--brand-600);'></i></div>"
            f"<span class='text-slate-700 text-sm leading-relaxed'>{feat}</span></div>"
            for feat in prod.get("key_features", [])
        )
        feats_section = (
            f"<div class='bg-slate-50 rounded-2xl p-6 mb-6 border border-slate-100'>"
            f"<h3 class='text-xs font-semibold text-slate-400 uppercase tracking-widest mb-4'>"
            f"Fitur Utama</h3>"
            f"<div class='grid grid-cols-1 md:grid-cols-2 gap-3'>{feats_cards}</div>"
            f"</div>"
        ) if feats_cards else ""

        ucs_html = "".join(
            f"<div class='flex items-start gap-2.5 py-2.5 border-b border-slate-100 last:border-0'>"
            f"<i data-lucide='arrow-right' class='w-3.5 h-3.5 flex-shrink-0 mt-0.5'"
            f"   style='color:var(--brand-500);'></i>"
            f"<span class='text-sm text-slate-600 leading-relaxed'>{uc}</span></div>"
            for uc in prod.get("use_cases", [])
        )
        ucs_section = (
            f"<div class='bg-white rounded-xl border border-slate-200 p-6'>"
            f"<div class='flex items-center gap-2.5 mb-3'>"
            f"<div class='w-7 h-7 rounded-lg flex items-center justify-center'"
            f"     style='background:var(--brand-50);'>"
            f"<i data-lucide='layout-grid' class='w-4 h-4' style='color:var(--brand-600);'></i></div>"
            f"<h4 class='text-xs font-semibold text-slate-500 uppercase tracking-wider'>Cocok Untuk</h4>"
            f"</div><div>{ucs_html}</div></div>"
        ) if ucs_html else "<div></div>"

        why_text = prod.get("why_choose", "")
        why_section = (
            f"<div class='rounded-2xl p-8 mb-6' style='background:var(--brand-600);'>"
            f"<div class='flex items-start gap-5'>"
            f"<div class='w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0'"
            f"     style='background:rgba(255,255,255,0.18);'>"
            f"<i data-lucide='star' class='w-5 h-5 text-white'></i></div>"
            f"<div class='flex-1'>"
            f"<h3 class='text-xs font-semibold uppercase tracking-widest mb-3'"
            f"    style='color:var(--brand-200);'>Mengapa {name}?</h3>"
            f"<p class='text-white text-sm leading-relaxed mb-5'>{why_text}</p>"
            f"<button onclick='switchTab(\"contact\")'"
            f"        class='inline-flex items-center gap-2 bg-white font-semibold text-sm"
            f"               px-5 py-2.5 rounded-lg hover:bg-slate-50 transition-colors'"
            f"        style='color:var(--brand-700);'>"
            f"Jadwalkan Demo "
            f"<i data-lucide='arrow-right' class='w-4 h-4'></i>"
            f"</button></div></div></div>"
        ) if why_text else ""

        target_text = prod.get("target_user", "")
        target_section = (
            f"<div class='bg-white rounded-xl border border-slate-200 p-6'>"
            f"<div class='flex items-center gap-2.5 mb-3'>"
            f"<div class='w-7 h-7 rounded-lg flex items-center justify-center'"
            f"     style='background:var(--brand-50);'>"
            f"<i data-lucide='users' class='w-4 h-4' style='color:var(--brand-600);'></i></div>"
            f"<h4 class='text-xs font-semibold text-slate-500 uppercase tracking-wider'>Untuk Siapa?</h4>"
            f"</div>"
            f"<p class='text-slate-600 text-sm leading-relaxed'>{target_text}</p></div>"
        ) if target_text else "<div></div>"

        prod_content += f"""
        <div id="produk-tab-{slug}" class="produk-tab-content" style="display:{display}">
            <div class="relative rounded-2xl overflow-hidden mb-8 bg-slate-200" style="height:320px;">
                <img src="{_prod_asset(brand_lower, slug, 'banner')}"
                     class="w-full h-full object-cover"
                     onerror="this.style.display='none'">
                <div class="absolute inset-0"
                     style="background:linear-gradient(to right,rgba(15,23,42,.82) 0%,rgba(15,23,42,.35) 60%,transparent 100%);"></div>
                <div class="absolute inset-0 flex flex-col justify-end p-8">
                    <span class="text-xs font-semibold uppercase tracking-widest mb-2"
                          style="color:var(--brand-400);">Produk Unggulan</span>
                    <h2 class="text-2xl md:text-3xl font-bold text-white mb-2 leading-tight">{name}</h2>
                    <p class="text-base font-medium" style="color:var(--brand-200);">{prod.get("tagline", "")}</p>
                </div>
            </div>
            <div class="mb-8">{desc}</div>
            {feats_section}
            {why_section}
            <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                {target_section}
                {ucs_section}
            </div>
        </div>"""

    # --- Solusi ---
    solutions = data.get("solusi", {}).get("solutions_list", [])
    sol_html = ""
    for i, s_item in enumerate(solutions):
        num = str(i + 1).zfill(2)
        sol_html += f"""
        <div class="bg-white rounded-xl border-t-[3px] border-x border-b border-slate-100
                    p-6 hover:shadow-md transition-all"
             style="border-top-color: var(--brand-600);">
            <div class="w-7 h-7 rounded-md flex items-center justify-center
                        text-white font-extrabold text-xs flex-shrink-0 mb-3"
                 style="background: var(--brand-600);">
                {num}
            </div>
            <h4 class="font-bold text-slate-900 text-base mb-2 leading-snug">
                {s_item.get("target", "")}
            </h4>
            <p class="text-slate-500 text-sm leading-relaxed">{s_item.get("benefit", "")}</p>
        </div>"""

    return f"""<!DOCTYPE html>
<html lang="id" class="scroll-smooth">
<head>
    {_shared_head_meta(brand, "Enterprise Security & IT Solutions")}
    <link href="https://fonts.googleapis.com/css2?family=Inter:ital,wght@0,300;0,400;0,500;0,600;0,700;1,400&display=swap" rel="stylesheet">
    <style>
        {_css_vars(h, s)}
        body {{ font-family: 'Inter', sans-serif; }}
        .tab-content {{ display: none; }}
        .tab-content.active {{ display: block; }}
        [data-active="true"].tab-btn {{ color: var(--brand-700); font-weight: 600; }}
        .line-clamp-2 {{ display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }}
    </style>
    {_tailwind_config_script()}
</head>
<body class="bg-slate-50 text-slate-800 antialiased">

    <!-- Preview badge -->
    <div class="fixed bottom-5 right-5 z-50 flex items-center gap-2.5 bg-white text-slate-600
                px-4 py-2.5 rounded-xl border border-slate-200 shadow-lg text-xs font-medium">
        <span class="relative flex h-2 w-2">
            <span class="animate-ping absolute inline-flex h-full w-full rounded-full
                         bg-brand-400 opacity-60"></span>
            <span class="relative inline-flex rounded-full h-2 w-2 bg-brand-500"></span>
        </span>
        iAAWG · Template <span class="text-brand-600 font-semibold ml-0.5">Prestige</span>
    </div>

    <!-- Navbar -->
    <nav class="bg-white border-b border-slate-200 sticky top-0 z-40">
        <div class="max-w-7xl mx-auto px-6 h-16 flex items-center justify-between">
            <div class="flex items-center gap-3 cursor-pointer" onclick="switchTab('home')">
                <div class="w-8 h-8 bg-brand-600 rounded-lg flex items-center justify-center
                            text-white font-bold text-xs">
                    {brand[:2].upper()}
                </div>
                <span class="font-semibold text-slate-900 text-base">{brand.capitalize()} Indonesia</span>
            </div>
            <div class="hidden md:flex items-center gap-0.5">
                <button onclick="switchTab('home')" id="btn-home"
                    class="tab-btn px-4 py-2 rounded-lg text-sm transition-all
                           text-brand-600 font-semibold bg-brand-50"
                    data-active="true">Beranda</button>
                <button onclick="switchTab('produk')" id="btn-produk"
                    class="tab-btn px-4 py-2 rounded-lg text-sm transition-all
                           text-slate-500 hover:text-slate-900 hover:bg-slate-50"
                    data-active="false">Produk</button>
                <button onclick="switchTab('solusi')" id="btn-solusi"
                    class="tab-btn px-4 py-2 rounded-lg text-sm transition-all
                           text-slate-500 hover:text-slate-900 hover:bg-slate-50"
                    data-active="false">Solusi</button>
            </div>
            <button onclick="switchTab('contact')" id="btn-contact"
                class="tab-btn bg-brand-600 hover:bg-brand-700 text-white px-5 py-2.5
                       rounded-lg text-sm font-semibold transition-colors shadow-sm
                       shadow-brand-600/20">
                Hubungi Kami
            </button>
        </div>
    </nav>

    <main>
        <!-- ====== TAB BERANDA ====== -->
        <section id="tab-home" class="tab-content active">

            <div class="bg-white border-b border-slate-100">
                <div class="max-w-7xl mx-auto px-6 py-20 md:py-28">
                    <div class="grid grid-cols-1 md:grid-cols-2 gap-14 items-center">
                        <div>
                            <h1 class="text-4xl md:text-5xl font-bold text-slate-900
                                       leading-tight tracking-tight mb-5">
                                {home.get("hero_headline", "Solusi IT Terpercaya untuk Bisnis Anda")}
                            </h1>
                            <p class="text-lg text-slate-500 leading-relaxed mb-8">
                                {home.get("hero_subheadline", "")}
                            </p>
                            <div class="flex flex-wrap gap-3">
                                <button onclick="switchTab('contact')"
                                    class="bg-brand-600 hover:bg-brand-700 text-white font-semibold
                                           px-7 py-3.5 rounded-xl transition-colors flex items-center
                                           gap-2 shadow-md shadow-brand-600/20">
                                    {home.get("cta_button_text", "Konsultasi Sekarang")}
                                    <i data-lucide="arrow-right" class="w-4 h-4"></i>
                                </button>
                                <button onclick="switchTab('produk')"
                                    class="bg-slate-100 hover:bg-slate-200 text-slate-700
                                           font-semibold px-7 py-3.5 rounded-xl transition-colors">
                                    Lihat Produk
                                </button>
                            </div>
                        </div>
                        <div class="relative h-80 rounded-2xl overflow-hidden shadow-xl
                                    border border-slate-100">
                            <img src="{_asset(brand_lower, 'home', 'banner')}"
                                 class="w-full h-full object-cover"
                                 onerror="this.parentElement.style.background='#f1f5f9'; this.style.display='none'">
                        </div>
                    </div>
                </div>
            </div>

            <div class="bg-slate-50 py-20 px-6 border-b border-slate-100">
                <div class="max-w-7xl mx-auto">
                    <div class="text-center mb-14 max-w-2xl mx-auto">
                        <h2 class="text-2xl md:text-3xl font-bold text-slate-900 mb-3">
                            Mengapa {brand.capitalize()}?
                        </h2>
                        <p class="text-slate-500">
                            {home.get("closing_statement", "Dipercaya untuk melindungi dan mengelola infrastruktur IT bisnis Anda.")}
                        </p>
                    </div>
                    <div class="grid grid-cols-1 md:grid-cols-3 gap-6">{vp_html}</div>
                </div>
            </div>

            <div class="bg-white py-20 px-6">
                <div class="max-w-7xl mx-auto grid grid-cols-1 md:grid-cols-2 gap-14 items-center">
                    <div>
                        <span class="text-xs font-semibold text-brand-600 uppercase
                                     tracking-widest block mb-3">Tentang {brand.capitalize()}</span>
                        <h3 class="text-2xl font-bold text-slate-900 mb-5 leading-tight">
                            {home.get("title", f"Tentang {brand.capitalize()}")}
                        </h3>
                        <div class="border-l-4 border-brand-600 pl-5 space-y-3 text-sm
                                    text-slate-600 leading-relaxed">
                            {_paras(home.get("about_summary", ""))}
                        </div>
                    </div>
                    <div class="relative h-72 rounded-2xl overflow-hidden shadow-xl
                                border border-slate-100">
                        <img src="{_asset(brand_lower, 'home', 'stock')}"
                             class="w-full h-full object-cover"
                             onerror="this.parentElement.style.background='#e2e8f0'; this.style.display='none'">
                    </div>
                </div>
            </div>
        </section>

        <!-- ====== TAB PRODUK ====== -->
        <section id="tab-produk" class="tab-content" style="display:none">

            <!-- Header band -->
            <div class="bg-white border-b border-slate-100 py-12 px-6">
                <div class="max-w-7xl mx-auto">
                    <span class="text-xs font-semibold text-brand-600 uppercase tracking-widest
                                 block mb-2">Portofolio</span>
                    <h2 class="text-2xl font-bold text-slate-900 mb-1">
                        {data.get("produk", {}).get("intro_page_title", "Produk & Solusi")}
                    </h2>
                    <p class="text-slate-500 text-sm max-w-2xl">
                        {data.get("produk", {}).get("intro_page_description", "")}
                    </p>
                </div>
            </div>

            <div class="max-w-7xl mx-auto px-6 py-12">

                <!-- ── CATALOG OVERVIEW (default) ── -->
                <div id="catalog-overview">
                    {catalog_html or '<p class="text-slate-400 text-sm py-16 text-center">Belum ada produk.</p>'}
                </div>

                <!-- ── DETAIL VIEW (tersembunyi, muncul setelah klik card) ── -->
                <div id="catalog-detail" style="display:none">

                    <!-- Tombol kembali ke catalog -->
                    <div class="mb-8">
                        <button onclick="showCatalog()"
                            class="inline-flex items-center gap-2 text-sm font-medium
                                   text-slate-500 hover:text-slate-800 transition-colors
                                   bg-white border border-slate-200 rounded-xl px-4 py-2.5
                                   hover:border-slate-300">
                            <i data-lucide="arrow-left" class="w-4 h-4"></i>
                            Kembali ke Katalog
                        </button>
                    </div>

                    <!-- Panel detail produk -->
                    {prod_content or '<div class="py-16 text-center text-slate-400 text-sm">Data produk belum tersedia.</div>'}
                </div>

            </div>
        </section>

        <!-- ====== TAB SOLUSI ====== -->
        <section id="tab-solusi" class="tab-content" style="display:none">

            <div class="bg-slate-900 py-14 px-6">
                <div class="max-w-7xl mx-auto flex flex-col md:flex-row items-center gap-10">
                    <div class="flex-1 min-w-0">
                        <span class="text-xs font-bold text-brand-400 uppercase
                                     tracking-widest block mb-4">Solusi</span>
                        <h2 class="text-4xl font-bold text-white mb-5 leading-tight">
                            {data.get("solusi", {}).get("title", "Solusi & Implementasi")}
                        </h2>
                        <p class="text-slate-300 text-base leading-relaxed">
                            {data.get("solusi", {}).get("intro", "")}
                        </p>
                    </div>
                    <div class="w-full md:w-2/5 flex-shrink-0">
                        <img src="{_asset(brand_lower, 'solusi', 'banner')}"
                             class="w-full h-56 md:h-64 object-cover rounded-xl"
                             onerror="this.parentElement.style.background='#1e293b'; this.style.display='none'">
                    </div>
                </div>
            </div>

            <div class="bg-white py-10 px-6 text-center border-b border-slate-100">
                <div class="max-w-xl mx-auto">
                    <span class="text-xs font-bold text-brand-600 uppercase
                                 tracking-widest block mb-2">Implementasi &amp; Industri</span>
                    <h3 class="text-2xl font-bold text-slate-900 mb-1.5">
                        Bagaimana {brand.capitalize()} Membantu Bisnis Anda?
                    </h3>
                    <p class="text-slate-500 text-sm">
                        {data.get("solusi", {}).get("intro", "Solusi terstruktur untuk setiap industri dan kebutuhan IT Anda.")}
                    </p>
                </div>
            </div>

            <div class="bg-slate-50 py-12 px-6">
                <div class="max-w-7xl mx-auto grid grid-cols-1 md:grid-cols-2 gap-5">
                    {sol_html or '<p class="text-slate-400 text-sm">Data solusi belum tersedia.</p>'}
                </div>
            </div>

            <div class="py-14 px-6" style="background: var(--brand-600);">
                <div class="max-w-2xl mx-auto text-center">
                    <h3 class="text-2xl font-bold text-white mb-2">
                        {data.get("solusi", {}).get("cta_headline", "Siap Transformasikan Infrastruktur IT Anda?")}
                    </h3>
                    <p class="text-sm mb-7" style="color: rgba(255,255,255,0.82);">
                        {data.get("solusi", {}).get("cta_subheadline", "Konsultasikan kebutuhan IT Anda langsung dengan tim ahli kami.")}
                    </p>
                    <button onclick="switchTab('contact')"
                            class="bg-white font-bold text-sm px-8 py-3 rounded-lg
                                   hover:bg-slate-50 transition-colors"
                            style="color: var(--brand-700);">
                        {data.get("solusi", {}).get("cta_button_text", "Hubungi Kami Sekarang")} &rarr;
                    </button>
                </div>
            </div>
        </section>

        <!-- ====== TAB CONTACT ====== -->
        <section id="tab-contact" class="tab-content" style="display:none">
            <div class="bg-slate-50 min-h-screen py-20 px-6">
                <div class="max-w-5xl mx-auto">
                    <div class="text-center mb-14">
                        <span class="text-xs font-semibold text-brand-600 uppercase tracking-widest
                                     block mb-3">Kontak</span>
                        <h2 class="text-3xl font-bold text-slate-900 mb-2">
                            {data.get("contact", {}).get("title", "Hubungi Kami")}
                        </h2>
                        <p class="text-slate-500 text-sm max-w-md mx-auto">
                            {data.get("contact", {}).get("headline", "")}
                        </p>
                    </div>
                    <div class="grid grid-cols-1 md:grid-cols-5 gap-8">
                        <div class="md:col-span-2 bg-brand-600 rounded-2xl p-8 text-white">
                            <h3 class="font-bold text-lg mb-2">
                                {data.get("contact", {}).get("title", "Terhubung dengan Kami")}
                            </h3>
                            <p class="text-brand-100 text-sm leading-relaxed mb-8">
                                {data.get("contact", {}).get("cta_text", "")}
                            </p>
                            <div class="space-y-4 text-sm border-t border-brand-500 pt-6">
                                <div class="flex items-center gap-3 text-white/80">
                                    <i data-lucide="mail" class="w-4 h-4 text-brand-200"></i>
                                    {brand.lower()}@ilogoindonesia.com
                                </div>
                                <div class="flex items-start gap-3 text-white/80">
                                    <i data-lucide="map-pin" class="w-4 h-4 text-brand-200 mt-0.5"></i>
                                    <span>AKR Tower – 9th Floor<br>Jl. Panjang No. 5, Kebon Jeruk, Jakarta</span>
                                </div>
                            </div>
                        </div>
                        <div class="md:col-span-3 bg-white rounded-2xl p-8 border border-slate-100 shadow-sm">
                            <form class="space-y-5" onsubmit="event.preventDefault()">
                                <div class="space-y-1.5">
                                    <label class="text-xs font-semibold text-slate-500 uppercase tracking-wide">Nama Lengkap</label>
                                    <input type="text" placeholder="John Doe"
                                        class="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 text-sm focus:outline-none focus:border-brand-500 transition-all">
                                </div>
                                <div class="space-y-1.5">
                                    <label class="text-xs font-semibold text-slate-500 uppercase tracking-wide">Email Perusahaan</label>
                                    <input type="email" placeholder="john@company.com"
                                        class="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 text-sm focus:outline-none focus:border-brand-500 transition-all">
                                </div>
                                <div class="space-y-1.5">
                                    <label class="text-xs font-semibold text-slate-500 uppercase tracking-wide">Kebutuhan IT Anda</label>
                                    <textarea rows="5" placeholder="Ceritakan kebutuhan infrastruktur Anda..."
                                        class="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 text-sm focus:outline-none focus:border-brand-500 transition-all resize-none"></textarea>
                                </div>
                                <button type="submit"
                                    class="w-full bg-brand-600 hover:bg-brand-700 text-white font-semibold
                                           py-3.5 rounded-xl transition-colors flex items-center
                                           justify-center gap-2 text-sm">
                                    Kirim Pesan
                                    <i data-lucide="send" class="w-4 h-4"></i>
                                </button>
                            </form>
                        </div>
                    </div>
                </div>
            </div>
        </section>
    </main>

    {_footer_html(brand)}
    {_shared_scripts()}
</body>
</html>"""


# =============================================================================
# TEMPLATE 2: CLARITY
# Cocok: Cloud, SaaS, ERP, Backup, Analytics, Software Enterprise
# Karakter: Modern, spacious, efisien — whitespace sangat lega, tipografi bersih
#   - Hero: dua kolom, headline dengan number/stats accent, gambar dengan card overlay
#   - Produk: catalog grid card → klik → detail produk (horizontal tabs diganti grid)
#   - Solusi: dua kolom list, nomor aksen brand
# =============================================================================

def render_clarity(brand: str, data: dict, primary_color: str, max_products: int) -> str:
    h, s, l = _hex_to_hsl(primary_color)
    brand_lower = brand.lower()
    products_list = data.get("produk", {}).get("products_list", [])[:max_products]
    home = data.get("home", {})
    vps  = home.get("value_propositions", [])

    vp_icons = ["trending-up", "layers", "zap", "bar-chart-3", "refresh-cw", "users"]
    vp_html = ""
    for i, vp in enumerate(vps):
        icon = vp_icons[i % len(vp_icons)]
        vp_html += f"""
        <div class="flex gap-5 items-start py-6 border-b border-slate-100 last:border-0
                    group hover:pl-2 transition-all duration-300">
            <div class="w-10 h-10 bg-brand-50 rounded-xl flex items-center justify-center
                        text-brand-600 flex-shrink-0 mt-0.5 group-hover:bg-brand-600
                        group-hover:text-white transition-colors">
                <i data-lucide="{icon}" class="w-5 h-5"></i>
            </div>
            <div>
                <h3 class="text-sm font-semibold text-slate-900 mb-1.5">
                    {vp.get("title", f"Keunggulan {i+1}")}
                </h3>
                <p class="text-slate-500 text-sm leading-relaxed">{vp.get("description", "")}</p>
            </div>
        </div>"""
    if not vp_html:
        vp_html = "<p class='text-slate-400 text-sm'>Data keunggulan belum tersedia.</p>"

    # --- Catalog grid ---
    catalog_html = _catalog_grid_html(products_list, brand_lower, "clarity")

    # --- Product detail panels ---
    prod_content = ""
    for i, prod in enumerate(products_list):
        name = prod.get("name", f"Produk {i+1}")
        slug = prod.get("slug", f"produk-{i+1}")
        feats = "".join([
            f"""<li class="flex items-start gap-2.5 py-2.5 border-b border-slate-100 last:border-0">
                <i data-lucide="check-circle" class="w-4 h-4 text-brand-500 flex-shrink-0 mt-0.5"></i>
                <span class="text-slate-600 text-sm leading-relaxed">{f}</span>
            </li>""" for f in prod.get("key_features", [])
        ])
        ucs = "".join([
            f'<div class="flex items-center gap-2 bg-slate-50 rounded-lg px-3 py-2 text-sm text-slate-600 border border-slate-100">'
            f'<i data-lucide="arrow-right" class="w-3.5 h-3.5 text-brand-500 flex-shrink-0"></i>{u}</div>'
            for u in prod.get("use_cases", [])
        ])
        desc = _paras(prod.get("description", ""), "text-slate-600 text-sm leading-relaxed mb-3")
        display = "block" if i == 0 else "none"

        prod_content += f"""
        <div id="produk-tab-{slug}" class="produk-tab-content" style="display:{display}">
            <div class="grid grid-cols-1 md:grid-cols-2 gap-8 mb-8 items-start">
                <div>
                    <h2 class="text-2xl font-bold text-slate-900 mb-1 leading-tight">{name}</h2>
                    <p class="text-brand-600 font-medium text-sm mb-5">
                        {prod.get("tagline", "")}
                    </p>
                    <div class="rounded-xl overflow-hidden h-52 bg-slate-100 mb-6">
                        <img src="{_prod_asset(brand_lower, slug, 'banner')}"
                             class="w-full h-full object-cover"
                             onerror="this.parentElement.style.background='#f1f5f9'; this.style.display='none'">
                    </div>
                    <div>{desc}</div>
                </div>
                <div class="space-y-5">
                    <div class="bg-slate-50 rounded-2xl p-6 border border-slate-100">
                        <h4 class="text-sm font-semibold text-slate-900 mb-3">Fitur Utama</h4>
                        <ul>{feats}</ul>
                    </div>
                    {f'<div class="space-y-2"><h4 class="text-sm font-semibold text-slate-900 mb-3">Digunakan Untuk</h4><div class="grid grid-cols-1 gap-2">{ucs}</div></div>' if ucs else ""}
                </div>
            </div>
            <div class="bg-brand-50 border border-brand-100 rounded-2xl p-6
                        flex flex-col md:flex-row items-start md:items-center gap-5
                        justify-between">
                <div class="flex-1">
                    <h4 class="text-sm font-semibold text-slate-900 mb-1.5">
                        Mengapa {name}?
                    </h4>
                    <p class="text-slate-600 text-sm leading-relaxed">
                        {prod.get("why_choose", "")}
                    </p>
                </div>
                <button onclick="switchTab('contact')"
                    class="bg-brand-600 hover:bg-brand-700 text-white font-semibold px-6 py-3
                           rounded-xl transition-colors text-sm flex items-center gap-2
                           whitespace-nowrap flex-shrink-0">
                    Jadwalkan Demo
                    <i data-lucide="calendar" class="w-4 h-4"></i>
                </button>
            </div>
        </div>"""

    solutions = data.get("solusi", {}).get("solutions_list", [])
    sol_html = ""
    for i, s_item in enumerate(solutions):
        sol_html += f"""
        <div class="group bg-white rounded-2xl p-6 border border-slate-100 shadow-sm
                    hover:border-brand-200 hover:shadow-md transition-all">
            <div class="flex items-center gap-3 mb-3">
                <span class="text-2xl font-bold text-brand-100 leading-none select-none">
                    {str(i+1).zfill(2)}
                </span>
                <h4 class="font-semibold text-slate-900 text-sm leading-snug">
                    {s_item.get("target", "")}
                </h4>
            </div>
            <p class="text-slate-500 text-sm leading-relaxed">{s_item.get("benefit", "")}</p>
        </div>"""

    return f"""<!DOCTYPE html>
<html lang="id" class="scroll-smooth">
<head>
    {_shared_head_meta(brand, "Cloud & Enterprise Software")}
    <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700;800&display=swap" rel="stylesheet">
    <style>
        {_css_vars(h, s)}
        body {{ font-family: 'Plus Jakarta Sans', sans-serif; }}
        .tab-content {{ display: none; }}
        .tab-content.active {{ display: block; }}
        .line-clamp-2 {{ display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }}
    </style>
    {_tailwind_config_script()}
</head>
<body class="bg-white text-slate-800 antialiased">

    <!-- Preview badge -->
    <div class="fixed bottom-5 right-5 z-50 flex items-center gap-2.5 bg-white text-slate-600
                px-4 py-2.5 rounded-xl border border-slate-200 shadow-lg text-xs font-medium">
        <span class="relative flex h-2 w-2">
            <span class="animate-ping absolute inline-flex h-full w-full rounded-full
                         bg-brand-400 opacity-60"></span>
            <span class="relative inline-flex rounded-full h-2 w-2 bg-brand-500"></span>
        </span>
        iAAWG · Template <span class="text-brand-600 font-semibold ml-0.5">Clarity</span>
    </div>

    <!-- Navbar -->
    <nav class="bg-white border-b border-slate-100 sticky top-0 z-40">
        <div class="max-w-7xl mx-auto px-6 h-16 flex items-center justify-between">
            <div class="flex items-center gap-3 cursor-pointer" onclick="switchTab('home')">
                <div class="w-8 h-8 bg-brand-600 rounded-lg flex items-center justify-center
                            text-white font-bold text-xs">
                    {brand[:2].upper()}
                </div>
                <span class="font-bold text-slate-900">{brand.capitalize()}</span>
            </div>
            <div class="hidden md:flex items-center gap-1">
                <button onclick="switchTab('home')" id="btn-home"
                    class="tab-btn px-4 py-2 rounded-lg text-sm font-medium transition-all
                           text-brand-600 bg-brand-50" data-active="true">Beranda</button>
                <button onclick="switchTab('produk')" id="btn-produk"
                    class="tab-btn px-4 py-2 rounded-lg text-sm font-medium transition-all
                           text-slate-500 hover:text-slate-900 hover:bg-slate-50"
                    data-active="false">Produk</button>
                <button onclick="switchTab('solusi')" id="btn-solusi"
                    class="tab-btn px-4 py-2 rounded-lg text-sm font-medium transition-all
                           text-slate-500 hover:text-slate-900 hover:bg-slate-50"
                    data-active="false">Solusi</button>
            </div>
            <button onclick="switchTab('contact')" id="btn-contact"
                class="bg-brand-600 hover:bg-brand-700 text-white px-5 py-2.5 rounded-xl
                       text-sm font-semibold transition-colors">
                Hubungi Kami
            </button>
        </div>
    </nav>

    <main>
        <!-- ====== TAB BERANDA ====== -->
        <section id="tab-home" class="tab-content active">

            <div class="bg-slate-50 border-b border-slate-100">
                <div class="max-w-7xl mx-auto px-6 py-20 md:py-28
                            grid grid-cols-1 md:grid-cols-2 gap-14 items-center">
                    <div class="relative order-2 md:order-1 h-80 md:h-96 rounded-3xl
                                overflow-hidden shadow-2xl">
                        <img src="{_asset(brand_lower, 'home', 'banner')}"
                             class="w-full h-full object-cover"
                             onerror="this.parentElement.style.background='#e2e8f0'; this.style.display='none'">
                    </div>
                    <div class="order-1 md:order-2">
                        <h1 class="text-4xl md:text-5xl font-bold text-slate-900 leading-tight
                                   tracking-tight mb-5">
                            {home.get("hero_headline", "Platform Terbaik untuk Bisnis Anda")}
                        </h1>
                        <p class="text-slate-500 text-base leading-relaxed mb-8">
                            {home.get("hero_subheadline", "")}
                        </p>
                        <div class="flex flex-wrap gap-3">
                            <button onclick="switchTab('contact')"
                                class="bg-brand-600 hover:bg-brand-700 text-white font-semibold
                                       px-7 py-3.5 rounded-xl transition-colors shadow-md
                                       shadow-brand-600/20 flex items-center gap-2">
                                {home.get("cta_button_text", "Mulai Sekarang")}
                                <i data-lucide="arrow-right" class="w-4 h-4"></i>
                            </button>
                            <button onclick="switchTab('produk')"
                                class="bg-white hover:bg-slate-50 text-slate-700 font-semibold
                                       px-7 py-3.5 rounded-xl transition-colors border
                                       border-slate-200 hover:border-slate-300">
                                Eksplorasi Produk
                            </button>
                        </div>
                    </div>
                </div>
            </div>

            <div class="bg-white py-20 px-6">
                <div class="max-w-7xl mx-auto grid grid-cols-1 md:grid-cols-2 gap-14 items-start">
                    <div>
                        <span class="text-xs font-semibold text-brand-600 uppercase tracking-widest
                                     block mb-3">Keunggulan</span>
                        <h2 class="text-2xl md:text-3xl font-bold text-slate-900 mb-3 leading-tight">
                            Mengapa Memilih {brand.capitalize()}?
                        </h2>
                        <p class="text-slate-500 text-sm leading-relaxed">
                            Kami menghadirkan teknologi enterprise-grade yang mudah
                            diadopsi dan memberikan ROI nyata bagi bisnis Anda.
                        </p>
                    </div>
                    <div class="divide-y divide-slate-100">{vp_html}</div>
                </div>
            </div>

            <div class="bg-slate-50 py-20 px-6 border-t border-slate-100">
                <div class="max-w-7xl mx-auto grid grid-cols-1 md:grid-cols-2 gap-14 items-center">
                    <div>
                        <span class="text-xs font-semibold text-brand-600 uppercase tracking-widest
                                     block mb-3">Tentang {brand.capitalize()}</span>
                        <h3 class="text-2xl font-bold text-slate-900 mb-4 leading-tight">
                            {home.get("title", f"Tentang {brand.capitalize()}")}
                        </h3>
                        <div class="w-10 h-0.5 bg-brand-600 rounded-full mb-5"></div>
                        <div class="space-y-3 text-sm text-slate-600 leading-relaxed">
                            {_paras(home.get("about_summary", ""))}
                        </div>
                    </div>
                    <div class="relative h-72 rounded-2xl overflow-hidden shadow-xl
                                border border-slate-100">
                        <img src="{_asset(brand_lower, 'home', 'stock')}"
                             class="w-full h-full object-cover"
                             onerror="this.parentElement.style.background='#e2e8f0'; this.style.display='none'">
                    </div>
                </div>
            </div>
        </section>

        <!-- ====== TAB PRODUK ====== -->
        <section id="tab-produk" class="tab-content" style="display:none">

            <div class="bg-white border-b border-slate-100 py-10 px-6">
                <div class="max-w-7xl mx-auto">
                    <h2 class="text-2xl font-bold text-slate-900 mb-1">
                        {data.get("produk", {}).get("intro_page_title", "Produk & Solusi")}
                    </h2>
                    <p class="text-slate-500 text-sm">
                        {data.get("produk", {}).get("intro_page_description", "")}
                    </p>
                </div>
            </div>

            <div class="max-w-7xl mx-auto px-6 py-10">

                <!-- ── CATALOG OVERVIEW ── -->
                <div id="catalog-overview">
                    {catalog_html or '<p class="text-slate-400 text-sm py-16 text-center">Belum ada produk.</p>'}
                </div>

                <!-- ── DETAIL VIEW ── -->
                <div id="catalog-detail" style="display:none">
                    <div class="mb-8">
                        <button onclick="showCatalog()"
                            class="inline-flex items-center gap-2 text-sm font-medium
                                   text-brand-600 hover:text-brand-700 transition-colors">
                            <i data-lucide="arrow-left" class="w-4 h-4"></i>
                            Kembali ke Katalog Produk
                        </button>
                    </div>
                    {prod_content or '<div class="py-16 text-center text-slate-400 text-sm">Data produk belum tersedia.</div>'}
                </div>

            </div>
        </section>

        <!-- ====== TAB SOLUSI ====== -->
        <section id="tab-solusi" class="tab-content" style="display:none">
            <div class="relative h-60 overflow-hidden">
                <img src="{_asset(brand_lower, 'solusi', 'banner')}"
                     class="w-full h-full object-cover"
                     onerror="this.style.display='none'">
                <div class="absolute inset-0 bg-gradient-to-b from-slate-900/70
                            to-slate-900/90 flex items-center px-6">
                    <div class="max-w-7xl mx-auto w-full">
                        <h2 class="text-3xl font-bold text-white mb-2">
                            {data.get("solusi", {}).get("title", "Solusi")}
                        </h2>
                        <p class="text-slate-300 text-sm max-w-xl">
                            {data.get("solusi", {}).get("intro", "")}
                        </p>
                    </div>
                </div>
            </div>
            <div class="bg-slate-50 py-16 px-6">
                <div class="max-w-7xl mx-auto grid grid-cols-1 md:grid-cols-2 gap-5">
                    {sol_html or '<p class="text-slate-400 text-sm">Data solusi belum tersedia.</p>'}
                </div>
            </div>
            <div class="py-14 px-6" style="background: var(--brand-50); border-top: 1px solid var(--brand-100);">
                <div class="max-w-2xl mx-auto text-center">
                    <h3 class="text-2xl font-bold text-slate-900 mb-2">
                        {data.get("solusi", {}).get("cta_headline", "Siap Transformasikan Infrastruktur IT Anda?")}
                    </h3>
                    <p class="text-slate-500 text-sm mb-7">
                        {data.get("solusi", {}).get("cta_subheadline", "Konsultasikan kebutuhan IT Anda langsung dengan tim ahli kami.")}
                    </p>
                    <button onclick="switchTab('contact')"
                            class="font-bold text-sm px-8 py-3 rounded-lg
                                   text-white hover:opacity-90 transition-opacity"
                            style="background: var(--brand-600);">
                        {data.get("solusi", {}).get("cta_button_text", "Hubungi Kami Sekarang")} &rarr;
                    </button>
                </div>
            </div>
        </section>

        <!-- ====== TAB CONTACT ====== -->
        <section id="tab-contact" class="tab-content" style="display:none">
            <div class="bg-slate-50 min-h-screen py-20 px-6">
                <div class="max-w-4xl mx-auto">
                    <div class="text-center mb-12">
                        <h2 class="text-3xl font-bold text-slate-900 mb-2">
                            {data.get("contact", {}).get("title", "Hubungi Kami")}
                        </h2>
                        <p class="text-slate-500 text-sm">
                            {data.get("contact", {}).get("headline", "")}
                        </p>
                    </div>
                    <div class="bg-white rounded-3xl border border-slate-100 shadow-sm
                                overflow-hidden grid grid-cols-1 md:grid-cols-2">
                        <div class="p-10" style="background: var(--brand-600);">
                            <h3 class="text-white font-bold text-lg mb-2">
                                {data.get("contact", {}).get("title", "Terhubung dengan Kami")}
                            </h3>
                            <p class="text-white/70 text-sm leading-relaxed mb-8">
                                {data.get("contact", {}).get("cta_text", "")}
                            </p>
                            <div class="space-y-4 text-sm">
                                <div class="flex items-center gap-3 text-white/80">
                                    <i data-lucide="mail" class="w-4 h-4 text-white/50"></i>
                                    {brand.lower()}@ilogoindonesia.com
                                </div>
                                <div class="flex items-start gap-3 text-white/80">
                                    <i data-lucide="map-pin" class="w-4 h-4 text-white/50 mt-0.5"></i>
                                    <span>AKR Tower – 9th Floor<br>Jl. Panjang No. 5, Jakarta</span>
                                </div>
                            </div>
                        </div>
                        <div class="p-10">
                            <form class="space-y-5" onsubmit="event.preventDefault()">
                                <div class="space-y-1.5">
                                    <label class="text-xs font-semibold text-slate-500">Nama Lengkap</label>
                                    <input type="text" placeholder="John Doe"
                                        class="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 text-sm focus:outline-none focus:border-brand-500 transition-all">
                                </div>
                                <div class="space-y-1.5">
                                    <label class="text-xs font-semibold text-slate-500">Email Perusahaan</label>
                                    <input type="email" placeholder="john@company.com"
                                        class="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 text-sm focus:outline-none focus:border-brand-500 transition-all">
                                </div>
                                <div class="space-y-1.5">
                                    <label class="text-xs font-semibold text-slate-500">Pesan</label>
                                    <textarea rows="4" placeholder="Ceritakan kebutuhan Anda..."
                                        class="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 text-sm focus:outline-none focus:border-brand-500 transition-all resize-none"></textarea>
                                </div>
                                <button type="submit"
                                    class="w-full text-white font-semibold py-3.5 rounded-xl
                                           transition-colors flex items-center justify-center
                                           gap-2 text-sm hover:opacity-90"
                                    style="background: var(--brand-600);">
                                    Kirim Pesan
                                    <i data-lucide="send" class="w-4 h-4"></i>
                                </button>
                            </form>
                        </div>
                    </div>
                </div>
            </div>
        </section>
    </main>

    {_footer_html(brand)}
    {_shared_scripts()}
</body>
</html>"""


# =============================================================================
# TEMPLATE 3: MOMENTUM
# Cocok: Network, SD-WAN, Monitoring, AV, Infrastruktur
# Karakter: Berenergi, teknis, infrastruktur
#   - Hero: full-width dark dengan overlay warna brand, CTA besar
#   - Produk: catalog grid card → klik → detail produk (sidebar diganti grid)
#   - Solusi: bento-grid asimetris
# =============================================================================

def render_momentum(brand: str, data: dict, primary_color: str, max_products: int) -> str:
    h, s, l = _hex_to_hsl(primary_color)
    brand_lower = brand.lower()
    products_list = data.get("produk", {}).get("products_list", [])[:max_products]
    home = data.get("home", {})
    vps  = home.get("value_propositions", [])

    vp_icons = ["wifi", "activity", "server", "monitor", "network", "radio"]
    vp_html = ""
    for i, vp in enumerate(vps):
        icon = vp_icons[i % len(vp_icons)]
        vp_html += f"""
        <div class="text-center px-6 {'' if i == len(vps)-1 else 'border-r border-slate-200'}
                    py-4 group">
            <div class="w-12 h-12 bg-brand-50 rounded-2xl flex items-center justify-center
                        text-brand-600 mx-auto mb-4 group-hover:bg-brand-600
                        group-hover:text-white transition-colors">
                <i data-lucide="{icon}" class="w-6 h-6"></i>
            </div>
            <h3 class="text-sm font-semibold text-slate-900 mb-2">
                {vp.get("title", f"Keunggulan {i+1}")}
            </h3>
            <p class="text-slate-500 text-xs leading-relaxed">{vp.get("description", "")}</p>
        </div>"""
    if not vp_html:
        vp_html = "<p class='text-slate-400 text-sm col-span-3 text-center py-4'>Data keunggulan belum tersedia.</p>"

    # --- Catalog grid ---
    catalog_html = _catalog_grid_html(products_list, brand_lower, "momentum")

    # --- Product detail panels ---
    prod_content = ""
    for i, prod in enumerate(products_list):
        name = prod.get("name", f"Produk {i+1}")
        slug = prod.get("slug", f"produk-{i+1}")
        feats = "".join([
            f"""<li class="flex items-start gap-3 py-2.5 border-b border-slate-100 last:border-0">
                <i data-lucide="zap" class="w-4 h-4 text-brand-500 flex-shrink-0 mt-0.5"></i>
                <span class="text-slate-600 text-sm leading-relaxed">{f}</span>
            </li>""" for f in prod.get("key_features", [])
        ])
        ucs = "".join([
            f'<span class="inline-block bg-slate-100 text-slate-600 text-xs '
            f'px-3 py-1.5 rounded-lg font-medium">{u}</span>'
            for u in prod.get("use_cases", [])
        ])
        desc = _paras(prod.get("description", ""), "text-slate-600 text-sm leading-relaxed mb-3")
        display = "block" if i == 0 else "none"

        prod_content += f"""
        <div id="produk-tab-{slug}" class="produk-tab-content" style="display:{display}">
            <div class="flex items-start gap-4 mb-6">
                <div class="w-12 h-12 bg-brand-50 rounded-xl flex items-center justify-center
                            text-brand-600 flex-shrink-0">
                    <i data-lucide="box" class="w-6 h-6"></i>
                </div>
                <div>
                    <h2 class="text-xl font-bold text-slate-900 leading-tight">{name}</h2>
                    <p class="text-brand-600 text-sm font-medium mt-0.5">
                        {prod.get("tagline", "")}
                    </p>
                </div>
            </div>

            <div class="relative h-52 rounded-2xl overflow-hidden mb-7 bg-slate-100">
                <img src="{_prod_asset(brand_lower, slug, 'banner')}"
                     class="w-full h-full object-cover"
                     onerror="this.parentElement.style.background='#e2e8f0'; this.style.display='none'">
                <div class="absolute inset-0 bg-gradient-to-r from-brand-800/30 to-transparent"></div>
            </div>

            <div class="grid grid-cols-1 md:grid-cols-2 gap-6 mb-6">
                <div>{desc}</div>
                <div class="bg-slate-50 rounded-xl p-5 border border-slate-100">
                    <h4 class="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-3">
                        Fitur Utama
                    </h4>
                    <ul>{feats}</ul>
                </div>
            </div>

            {f'<div class="mb-6"><h4 class="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2.5">Digunakan Untuk</h4><div class="flex flex-wrap gap-2">{ucs}</div></div>' if ucs else ""}

            <div class="bg-slate-900 rounded-2xl p-6 flex flex-col md:flex-row items-start
                        md:items-center justify-between gap-5">
                <div>
                    <h4 class="text-white font-semibold mb-1.5 text-sm">
                        Mengapa {name}?
                    </h4>
                    <p class="text-slate-400 text-sm leading-relaxed">
                        {prod.get("why_choose", "")}
                    </p>
                </div>
                <button onclick="switchTab('contact')"
                    class="bg-brand-500 hover:bg-brand-400 text-white font-semibold px-6 py-3
                           rounded-xl transition-colors text-sm whitespace-nowrap flex-shrink-0">
                    Jadwalkan Demo
                </button>
            </div>
        </div>"""

    # Solusi: bento-style
    solutions = data.get("solusi", {}).get("solutions_list", [])
    sol_left = ""
    sol_right = ""
    for i, s_item in enumerate(solutions):
        card = f"""
        <div class="bg-white rounded-2xl p-6 border border-slate-100 shadow-sm
                    hover:border-brand-200 hover:shadow-md transition-all h-full">
            <div class="w-10 h-10 bg-brand-50 rounded-xl flex items-center justify-center
                        text-brand-600 mb-4">
                <i data-lucide="layers" class="w-5 h-5"></i>
            </div>
            <h4 class="font-semibold text-slate-900 text-sm mb-2">
                {s_item.get("target", "")}
            </h4>
            <p class="text-slate-500 text-sm leading-relaxed">{s_item.get("benefit", "")}</p>
        </div>"""
        if i % 3 == 2:
            sol_right += card
        else:
            sol_left += card

    return f"""<!DOCTYPE html>
<html lang="id" class="scroll-smooth">
<head>
    {_shared_head_meta(brand, "Network & Infrastructure Solutions")}
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700;800&display=swap" rel="stylesheet">
    <style>
        {_css_vars(h, s)}
        body {{ font-family: 'Outfit', sans-serif; }}
        .tab-content {{ display: none; }}
        .tab-content.active {{ display: block; }}
        .line-clamp-2 {{ display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }}
    </style>
    {_tailwind_config_script()}
</head>
<body class="bg-slate-50 text-slate-800 antialiased">

    <!-- Preview badge -->
    <div class="fixed bottom-5 right-5 z-50 flex items-center gap-2.5 bg-white text-slate-600
                px-4 py-2.5 rounded-xl border border-slate-200 shadow-lg text-xs font-medium">
        <span class="relative flex h-2 w-2">
            <span class="animate-ping absolute inline-flex h-full w-full rounded-full
                         bg-brand-400 opacity-60"></span>
            <span class="relative inline-flex rounded-full h-2 w-2 bg-brand-500"></span>
        </span>
        iAAWG · Template <span class="text-brand-600 font-semibold ml-0.5">Momentum</span>
    </div>

    <!-- Navbar -->
    <nav class="bg-white border-b border-slate-200 sticky top-0 z-40">
        <div class="max-w-7xl mx-auto px-6 h-16 flex items-center justify-between">
            <div class="flex items-center gap-3 cursor-pointer" onclick="switchTab('home')">
                <div class="w-8 h-8 rounded-lg flex items-center justify-center text-white
                            font-bold text-xs bg-brand-600">
                    {brand[:2].upper()}
                </div>
                <span class="font-bold text-slate-900 text-base">{brand.capitalize()}</span>
            </div>
            <div class="hidden md:flex items-center gap-1">
                <button onclick="switchTab('home')" id="btn-home"
                    class="tab-btn px-4 py-2 rounded-xl text-sm font-medium transition-all
                           text-brand-600 bg-brand-50" data-active="true">Beranda</button>
                <button onclick="switchTab('produk')" id="btn-produk"
                    class="tab-btn px-4 py-2 rounded-xl text-sm font-medium transition-all
                           text-slate-500 hover:text-slate-900 hover:bg-slate-100"
                    data-active="false">Produk</button>
                <button onclick="switchTab('solusi')" id="btn-solusi"
                    class="tab-btn px-4 py-2 rounded-xl text-sm font-medium transition-all
                           text-slate-500 hover:text-slate-900 hover:bg-slate-100"
                    data-active="false">Solusi</button>
            </div>
            <button onclick="switchTab('contact')" id="btn-contact"
                class="tab-btn bg-brand-600 hover:bg-brand-700 text-white px-5 py-2.5
                       rounded-xl text-sm font-semibold transition-colors">
                Hubungi Kami
            </button>
        </div>
    </nav>

    <main>
        <!-- ====== TAB BERANDA ====== -->
        <section id="tab-home" class="tab-content active">

            <div class="relative overflow-hidden bg-slate-900 min-h-[88vh] flex items-center">
                <div class="absolute inset-0">
                    <img src="{_asset(brand_lower, 'home', 'banner')}"
                         class="w-full h-full object-cover opacity-25"
                         onerror="this.style.display='none'">
                    <div class="absolute inset-0"
                         style="background: linear-gradient(135deg, hsl({h},{max(40,min(s,75))}%,20%) 0%, hsl({h},{max(40,min(s,75))}%,12%) 60%, rgba(0,0,0,0.2) 100%);"></div>
                </div>
                <div class="relative max-w-7xl mx-auto px-6 py-24 w-full">
                    <div class="max-w-2xl">
                        <h1 class="text-4xl md:text-6xl font-bold text-white leading-tight
                                   tracking-tight mb-6">
                            {home.get("hero_headline", "Infrastruktur Canggih untuk Bisnis")}
                        </h1>
                        <p class="text-white/70 text-lg leading-relaxed mb-10">
                            {home.get("hero_subheadline", "")}
                        </p>
                        <div class="flex flex-wrap gap-4">
                            <button onclick="switchTab('contact')"
                                class="bg-brand-500 hover:bg-brand-400 text-white font-semibold
                                       px-8 py-4 rounded-xl transition-colors shadow-lg
                                       flex items-center gap-2">
                                {home.get("cta_button_text", "Konsultasi Sekarang")}
                                <i data-lucide="arrow-right" class="w-5 h-5"></i>
                            </button>
                            <button onclick="switchTab('produk')"
                                class="bg-white/10 hover:bg-white/20 text-white font-semibold
                                       px-8 py-4 rounded-xl transition-colors border
                                       border-white/20 backdrop-blur-sm">
                                Lihat Solusi
                            </button>
                        </div>
                    </div>
                </div>
            </div>

            <div class="bg-white border-b border-slate-100 py-14 px-6">
                <div class="max-w-7xl mx-auto">
                    <div class="grid grid-cols-1 md:grid-cols-3 divide-y md:divide-y-0
                                md:divide-x divide-slate-200">
                        {vp_html}
                    </div>
                </div>
            </div>

            <div class="bg-slate-50 py-20 px-6">
                <div class="max-w-7xl mx-auto grid grid-cols-1 md:grid-cols-2 gap-12 items-center">
                    <div>
                        <span class="text-xs font-semibold text-brand-600 uppercase tracking-widest
                                     block mb-3">Tentang {brand.capitalize()}</span>
                        <h3 class="text-2xl font-bold text-slate-900 mb-5 leading-tight">
                            {home.get("title", f"Tentang {brand.capitalize()}")}
                        </h3>
                        <div class="border-l-4 border-brand-500 pl-5 space-y-3 text-sm
                                    text-slate-600 leading-relaxed">
                            {_paras(home.get("about_summary", ""))}
                        </div>
                        <button onclick="switchTab('contact')"
                            class="mt-8 inline-flex items-center gap-2 text-brand-600
                                   font-semibold text-sm hover:text-brand-700 transition-colors">
                            Konsultasi Gratis
                            <i data-lucide="arrow-right" class="w-4 h-4"></i>
                        </button>
                    </div>
                    <div class="relative h-72 rounded-2xl overflow-hidden shadow-xl">
                        <img src="{_asset(brand_lower, 'home', 'stock')}"
                             class="w-full h-full object-cover"
                             onerror="this.parentElement.style.background='#e2e8f0'; this.style.display='none'">
                        <div class="absolute bottom-0 left-0 right-0 h-1/2"
                             style="background: linear-gradient(to top, hsl({h},{max(40,min(s,75))}%,20%,0.3), transparent)">
                        </div>
                    </div>
                </div>
            </div>
        </section>

        <!-- ====== TAB PRODUK ====== -->
        <section id="tab-produk" class="tab-content" style="display:none">

            <div class="py-12 px-6" style="background: var(--brand-700);">
                <div class="max-w-7xl mx-auto">
                    <h2 class="text-2xl font-bold text-white mb-1">
                        {data.get("produk", {}).get("intro_page_title", "Portofolio Produk")}
                    </h2>
                    <p class="text-sm" style="color: var(--brand-200);">
                        {data.get("produk", {}).get("intro_page_description", "")}
                    </p>
                </div>
            </div>

            <div class="max-w-7xl mx-auto px-6 py-10">

                <!-- ── CATALOG OVERVIEW ── -->
                <div id="catalog-overview">
                    {catalog_html or '<p class="text-slate-400 text-sm py-16 text-center">Belum ada produk.</p>'}
                </div>

                <!-- ── DETAIL VIEW ── -->
                <div id="catalog-detail" style="display:none">
                    <div class="mb-8">
                        <button onclick="showCatalog()"
                            class="inline-flex items-center gap-2 text-sm font-semibold
                                   text-white rounded-xl px-4 py-2.5 transition-colors"
                            style="background: var(--brand-600);">
                            <i data-lucide="arrow-left" class="w-4 h-4"></i>
                            Kembali ke Katalog
                        </button>
                    </div>
                    <div class="bg-white rounded-2xl border border-slate-100 p-8 shadow-sm">
                        {prod_content or '<div class="py-16 text-center text-slate-400 text-sm">Data produk belum tersedia.</div>'}
                    </div>
                </div>

            </div>
        </section>

        <!-- ====== TAB SOLUSI ====== -->
        <section id="tab-solusi" class="tab-content" style="display:none">
            <div class="relative h-60 overflow-hidden">
                <img src="{_asset(brand_lower, 'solusi', 'banner')}"
                     class="w-full h-full object-cover"
                     onerror="this.style.display='none'">
                <div class="absolute inset-0 flex items-center px-6"
                     style="background: linear-gradient(to right, hsl({h},{max(40,min(s,75))}%,20%) 0%, hsl({h},{max(40,min(s,75))}%,20%) 50%, transparent 100%); opacity: 0.92;">
                    <div class="max-w-7xl mx-auto w-full">
                        <h2 class="text-3xl font-bold text-white mb-2">
                            {data.get("solusi", {}).get("title", "Solusi & Implementasi")}
                        </h2>
                        <p class="text-white/70 text-sm max-w-xl">
                            {data.get("solusi", {}).get("intro", "")}
                        </p>
                    </div>
                </div>
            </div>
            <div class="bg-slate-50 py-16 px-6">
                <div class="max-w-7xl mx-auto">
                    {"<p class='text-slate-400 text-sm'>Data solusi belum tersedia.</p>" if not solutions else f'''
                    <div class="grid grid-cols-1 md:grid-cols-3 gap-5">
                        <div class="md:col-span-2 grid grid-cols-1 md:grid-cols-2 gap-5">
                            {sol_left}
                        </div>
                        <div class="grid grid-cols-1 gap-5">
                            {sol_right if sol_right else ""}
                        </div>
                    </div>'''}
                </div>
            </div>
            <div class="py-14 px-6" style="background: var(--brand-700);">
                <div class="max-w-2xl mx-auto text-center">
                    <h3 class="text-2xl font-bold text-white mb-2">
                        {data.get("solusi", {}).get("cta_headline", "Siap Transformasikan Infrastruktur IT Anda?")}
                    </h3>
                    <p class="text-sm mb-7" style="color: rgba(255,255,255,0.75);">
                        {data.get("solusi", {}).get("cta_subheadline", "Konsultasikan kebutuhan IT Anda langsung dengan tim ahli kami.")}
                    </p>
                    <button onclick="switchTab('contact')"
                            class="bg-white font-bold text-sm px-8 py-3 rounded-lg
                                   hover:bg-slate-50 transition-colors"
                            style="color: var(--brand-700);">
                        {data.get("solusi", {}).get("cta_button_text", "Hubungi Kami Sekarang")} &rarr;
                    </button>
                </div>
            </div>
        </section>

        <!-- ====== TAB CONTACT ====== -->
        <section id="tab-contact" class="tab-content" style="display:none">
            <div class="bg-slate-50 min-h-screen py-20 px-6">
                <div class="max-w-5xl mx-auto">
                    <div class="grid grid-cols-1 md:grid-cols-2 gap-8">
                        <div class="rounded-2xl p-10 text-white" style="background: var(--brand-700);">
                            <h2 class="text-2xl font-bold mb-2">
                                {data.get("contact", {}).get("title", "Hubungi Kami")}
                            </h2>
                            <p class="font-medium mb-6" style="color: var(--brand-200);">
                                {data.get("contact", {}).get("headline", "")}
                            </p>
                            <p class="text-white/70 text-sm leading-relaxed mb-10">
                                {data.get("contact", {}).get("cta_text", "")}
                            </p>
                            <div class="space-y-4 text-sm border-t pt-8" style="border-color: var(--brand-600);">
                                <div class="flex items-center gap-3 text-white/80">
                                    <i data-lucide="mail" class="w-4 h-4" style="color: var(--brand-300);"></i>
                                    {brand.lower()}@ilogoindonesia.com
                                </div>
                                <div class="flex items-start gap-3 text-white/80">
                                    <i data-lucide="map-pin" class="w-4 h-4 mt-0.5" style="color: var(--brand-300);"></i>
                                    <span>AKR Tower – 9th Floor<br>Jl. Panjang No. 5, Kebon Jeruk, Jakarta</span>
                                </div>
                            </div>
                        </div>
                        <div class="bg-white rounded-2xl p-10 border border-slate-100 shadow-sm">
                            <form class="space-y-5" onsubmit="event.preventDefault()">
                                <div class="space-y-1.5">
                                    <label class="text-xs font-semibold text-slate-500">Nama Lengkap</label>
                                    <input type="text" placeholder="John Doe"
                                        class="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 text-sm focus:outline-none focus:border-brand-500 transition-all">
                                </div>
                                <div class="space-y-1.5">
                                    <label class="text-xs font-semibold text-slate-500">Email Perusahaan</label>
                                    <input type="email" placeholder="john@company.com"
                                        class="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 text-sm focus:outline-none focus:border-brand-500 transition-all">
                                </div>
                                <div class="space-y-1.5">
                                    <label class="text-xs font-semibold text-slate-500">Kebutuhan IT Anda</label>
                                    <textarea rows="5" placeholder="Ceritakan kebutuhan infrastruktur Anda..."
                                        class="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 text-sm focus:outline-none focus:border-brand-500 transition-all resize-none"></textarea>
                                </div>
                                <button type="submit"
                                    class="w-full text-white font-semibold py-3.5 rounded-xl
                                           transition-colors flex items-center justify-center
                                           gap-2 text-sm hover:opacity-90"
                                    style="background: var(--brand-600);">
                                    Kirim Pesan
                                    <i data-lucide="send" class="w-4 h-4"></i>
                                </button>
                            </form>
                        </div>
                    </div>
                </div>
            </div>
        </section>
    </main>

    {_footer_html(brand)}
    {_shared_scripts()}
</body>
</html>"""


# =============================================================================
# ENTRY POINT UTAMA
# =============================================================================

def generate_preview_html(brand: str, data: dict, primary_color: str,
                          max_products: int = 5, template_name: str = "") -> str:
    """
    Entry point utama.

    Jika template_name kosong atau 'auto', sistem memilih template otomatis
    berdasarkan keyword konten brand (select_template).

    Args:
        brand         : nama brand (lowercase)
        data          : dict lengkap hasil generate pipeline
                        (keys: home, produk, solusi, contact)
        primary_color : hex warna brand (contoh: "#1E7E34")
        max_products  : batas maksimum produk yang ditampilkan
        template_name : "prestige" | "clarity" | "momentum" | "" / "auto"

    Returns:
        HTML string lengkap siap ditulis ke file preview_lokal.html
    """
    resolved = (template_name or "").strip().lower()
    if resolved not in {"prestige", "clarity", "momentum"}:
        resolved = select_template(data, brand)
        print(f"[Preview] Template otomatis dipilih: '{resolved}'")
    else:
        print(f"[Preview] Template manual: '{resolved}'")

    if resolved == "clarity":
        return render_clarity(brand, data, primary_color, max_products)
    elif resolved == "momentum":
        return render_momentum(brand, data, primary_color, max_products)
    else:
        return render_prestige(brand, data, primary_color, max_products)