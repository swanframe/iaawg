"""
wordpress/elementor_builder.py  (v3 — clean, Elementor-native)
==============================================================
Key architectural changes from v2:

1. ALIGNMENT via Elementor widget settings, not inline CSS
   - heading widget has its own `align` setting — use it, never inline style
   - text-editor widget respects text-align in the editor HTML

2. FOOTER rebuilt as a proper 3-column Elementor section
   - no more flex HTML injected into text-editor
   - each column is a native Elementor column widget

3. IMAGE height controlled via Elementor image widget settings only
   - consistent 380px hero banner, 300px stock photo, 340px product banner

4. SECTION PADDING explicit and template-aware
   - Elementor adds ~20px default padding; our values account for that

5. TEMPLATE DIFFERENTIATION via hero background colour
   - prestige  → white hero, left-aligned split layout
   - clarity   → white hero, centered with brand accent band
   - momentum  → brand-dark hero, full-width dramatic

Templates:
  prestige  — white bg, authority, left-aligned, trusted enterprise
  clarity   — clean white, spacious, centered, SaaS/Cloud
  momentum  — brand-coloured dark hero, energetic, infrastructure
"""

import json
import uuid


# ─────────────────────────────────────────────────────────────────────────────
# Colour utilities
# ─────────────────────────────────────────────────────────────────────────────

def _hex_to_rgb(h):
    h = h.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _darken(hex_color, pct=0.25):
    r, g, b = _hex_to_rgb(hex_color)
    return "#{:02x}{:02x}{:02x}".format(
        max(0, int(r * (1 - pct))),
        max(0, int(g * (1 - pct))),
        max(0, int(b * (1 - pct))),
    )


def _lighten(hex_color, pct=0.88):
    r, g, b = _hex_to_rgb(hex_color)
    return "#{:02x}{:02x}{:02x}".format(
        min(255, int(r + (255 - r) * pct)),
        min(255, int(g + (255 - g) * pct)),
        min(255, int(b + (255 - b) * pct)),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Elementor node primitives
# ─────────────────────────────────────────────────────────────────────────────

def _id():
    return uuid.uuid4().hex[:8]


def _section(settings, columns):
    return {"id": _id(), "elType": "section",
            "settings": settings, "elements": columns, "isInner": False}


def _column(width_pct, elements, extra_settings=None):
    s = {
        "_column_size": width_pct,                          # Elementor internal sizing field
        "column_width": {"unit": "%", "size": width_pct},  # Responsive width control
    }
    if extra_settings:
        s.update(extra_settings)
    return {"id": _id(), "elType": "column", "settings": s, "elements": elements}


def _widget(wtype, settings):
    return {"id": _id(), "elType": "widget", "widgetType": wtype, "settings": settings}


# ── Heading widget — uses Elementor's own align setting, not inline CSS ───────
def _heading(text, tag="h2", align="center", color="#1A1A2E",
             size_px=36, weight="700"):
    return _widget("heading", {
        "title": text,
        "header_size": tag,
        "align": align,                    # ← Elementor native, not inline style
        "title_color": color,
        "typography_font_size": {"unit": "px", "size": size_px},
        "typography_font_weight": weight,
    })


# ── Text editor — align handled via HTML inside the editor field ──────────────
def _text(html, color="#555555", size_px=16):
    return _widget("text-editor", {
        "editor": html,
        "text_color": color,
        "typography_font_size": {"unit": "px", "size": size_px},
    })


# ── Button — Elementor native alignment ───────────────────────────────────────
def _button(label, align="center", bg="#1E7E34", size_px=16, pad_v=14, pad_h=36):
    return _widget("button", {
        "text": label,
        "align": align,
        "background_color": bg,
        "button_text_color": "#FFFFFF",
        "border_radius": {"unit": "px", "top": "6", "right": "6",
                          "bottom": "6", "left": "6", "isLinked": True},
        "typography_font_size": {"unit": "px", "size": size_px},
        "typography_font_weight": "600",
        "padding": {"unit": "px", "top": str(pad_v), "right": str(pad_h),
                    "bottom": str(pad_v), "left": str(pad_h), "isLinked": False},
    })


# ── Image — consistent height via Elementor settings ─────────────────────────
def _image(url, alt="", height_px=360, border_radius=8):
    return _widget("image", {
        "image": {"url": url, "alt": alt},
        "image_size": "full",
        "width": {"unit": "%", "size": 100},
        "height": {"unit": "px", "size": height_px},
        "object_fit": "cover",
        "border_radius": {"unit": "px", "top": str(border_radius),
                          "right": str(border_radius), "bottom": str(border_radius),
                          "left": str(border_radius), "isLinked": True},
    })


def _spacer(h=24):
    return _widget("spacer", {"space": {"unit": "px", "size": h}})


def _divider(color="#E2E8F0"):
    return _widget("divider", {"color": color, "gap": {"unit": "px", "size": 0}})


# ─────────────────────────────────────────────────────────────────────────────
# Section settings helpers
# ─────────────────────────────────────────────────────────────────────────────

def _sec(bg="#FFFFFF", pt=60, pr=60, pb=60, pl=60):
    return {
        "background_background": "classic",
        "background_color": bg,
        "padding": {"unit": "px", "top": str(pt), "right": str(pr),
                    "bottom": str(pb), "left": str(pl), "isLinked": False},
    }


def _card_col_settings(bg="#FFFFFF"):
    return {
        "background_background": "classic",
        "background_color": bg,
        "border_border": "solid",
        "border_width": {"unit": "px", "top": "1", "right": "1",
                         "bottom": "1", "left": "1", "isLinked": True},
        "border_color": "#E2E8F0",
        "border_radius": {"unit": "px", "top": "10", "right": "10",
                          "bottom": "10", "left": "10", "isLinked": True},
        "box_shadow_box_shadow_type": "yes",
        "box_shadow_box_shadow": {
            "horizontal": 0, "vertical": 4, "blur": 18,
            "spread": 0, "color": "rgba(0,0,0,0.07)",
        },
        "padding": {"unit": "px", "top": "32", "right": "28",
                    "bottom": "32", "left": "28", "isLinked": False},
    }


def _to_json(sections):
    return json.dumps(sections, ensure_ascii=False)


# ─────────────────────────────────────────────────────────────────────────────
# HTML content helpers — inline styles that WORK inside text-editor
# ─────────────────────────────────────────────────────────────────────────────

def _paras(text, color="#475569", size=15, align="left"):
    parts = [p.strip() for p in text.split("\n") if p.strip()]
    return "".join(
        f"<p style='color:{color};font-size:{size}px;line-height:1.85;"
        f"margin-bottom:14px;text-align:{align};'>{p}</p>"
        for p in parts
    )


def _features_html(features, accent, size=14):
    items = "".join(
        f"<li style='display:flex;align-items:flex-start;gap:10px;"
        f"margin-bottom:10px;list-style:none;'>"
        f"<span style='color:{accent};font-weight:700;flex-shrink:0;"
        f"margin-top:1px;font-size:{size}px;'>✓</span>"
        f"<span style='color:#374151;line-height:1.7;font-size:{size}px;'>{f}</span>"
        f"</li>"
        for f in features
    )
    return f"<ul style='padding:0;margin:0;'>{items}</ul>"


def _uc_html(use_cases, size=13):
    items = "".join(
        f"<div style='background:#F8FAFC;border:1px solid #E2E8F0;"
        f"border-radius:6px;padding:10px 14px;margin-bottom:8px;"
        f"color:#374151;font-size:{size}px;line-height:1.6;'>{u}</div>"
        for u in use_cases
    )
    return items


# ─────────────────────────────────────────────────────────────────────────────
# Footer — rebuilt as a proper 3-column Elementor section (not HTML injection)
# ─────────────────────────────────────────────────────────────────────────────

def _footer_section(brand_name=""):
    """
    iLogo footer as a native 3-column Elementor section.
    Each column uses stacked heading + text-editor widgets (not a single
    HTML blob) so Elementor's CSS regeneration applies uniformly.
    """
    name  = brand_name.capitalize() if brand_name else "Brand"
    email = brand_name.lower() if brand_name else "brand"

    # Column wrapper — equal thirds, consistent padding
    def _footer_col(widgets, right_pad="20", left_pad="0"):
        return _column(33, widgets, extra_settings={
            "padding": {"unit": "px", "top": "0", "right": right_pad,
                        "bottom": "0", "left": left_pad, "isLinked": False},
        })

    # Section label — subtle uppercase, muted but visible on dark bg
    def _footer_label(text):
        return _widget("heading", {
            "title": text,
            "header_size": "h6",
            "align": "left",
            "title_color": "#94A3B8",
            "typography_font_size": {"unit": "px", "size": 10},
            "typography_font_weight": "700",
            "typography_text_transform": "uppercase",
            "typography_letter_spacing": {"unit": "px", "size": 2},
        })

    # Body text wrapper — always light on dark bg
    def _footer_text(html):
        return _widget("text-editor", {
            "editor": html,
            "text_color": "#E2E8F0",
            "typography_font_size": {"unit": "px", "size": 13},
        })

    # SVG icon pill — consistent with social icon style
    def _icon_pill(svg_path, stroke=True):
        stroke_attrs = "fill='none' stroke='#94A3B8' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'" if stroke else "fill='#94A3B8'"
        return (
            f"<span style='display:inline-flex;align-items:center;justify-content:center;"
            f"width:28px;height:28px;border-radius:6px;background:#1E293B;"
            f"border:1px solid #334155;flex-shrink:0;'>"
            f"<svg xmlns='http://www.w3.org/2000/svg' width='13' height='13' "
            f"viewBox='0 0 24 24' {stroke_attrs}>{svg_path}</svg></span>"
        )

    # Contact row — icon pill + text side by side
    def _contact_row(svg_path, text, stroke=True, align_start=False):
        valign = "flex-start" if align_start else "center"
        margin_top = "margin-top:2px;" if align_start else ""
        return (
            f"<div style='display:flex;align-items:{valign};gap:10px;margin-bottom:10px;'>"
            f"<span style='display:inline-flex;align-items:center;justify-content:center;"
            f"width:28px;height:28px;border-radius:6px;background:#1E293B;"
            f"border:1px solid #334155;flex-shrink:0;{margin_top}'>"
            + (
                f"<svg xmlns='http://www.w3.org/2000/svg' width='13' height='13' viewBox='0 0 24 24' "
                + ("fill='none' stroke='#94A3B8' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'" if stroke else "fill='#94A3B8'")
                + f">{svg_path}</svg>"
            )
            + f"</span>"
            f"<span style='font-size:13px;color:#E2E8F0;line-height:1.6;'>{text}</span>"
            f"</div>"
        )

    # ── COL 1: Brand description ──────────────────────────────────────────────
    col1 = _footer_col([
        _widget("heading", {
            "title": f"{name} Indonesia",
            "header_size": "h5",
            "align": "left",
            "title_color": "#F8FAFC",
            "typography_font_size": {"unit": "px", "size": 15},
            "typography_font_weight": "700",
        }),
        _footer_text(
            f"<p style='font-size:13px;color:#CBD5E1;line-height:1.75;margin:8px 0 0;'>"
            f"<strong style='color:#F1F5F9;'>{name} Indonesia</strong> merupakan "
            f"bagian dari PT. iLogo Infralogy Indonesia, yang bertindak sebagai "
            f"partner resmi <strong style='color:#F1F5F9;'>{name}</strong>. "
            f"Penyedia layanan Infrastruktur IT dan Cybersecurity terbaik di Indonesia.</p>"
        ),
    ])

    # ── COL 2: Sales & Marketing contact ─────────────────────────────────────
    pin_svg    = "<path d='M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z'/><circle cx='12' cy='10' r='3'/>"
    mail_svg   = "<path d='M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z'/><polyline points='22,6 12,13 2,6'/>"

    col2 = _footer_col([
        _footer_label("Sales &amp; Marketing"),
        _footer_text(
            f"<p style='font-size:13px;color:#F1F5F9;font-weight:600;margin:8px 0 12px;'>"
            f"PT iLogo Indonesia</p>"
            + _contact_row(pin_svg,   "Jl. Kebon Jeruk Raya<br>Villa Kebon Jeruk Office F1", align_start=True)
            + _contact_row(mail_svg,  f"{email}@ilogoindonesia.com")
        ),
    ])

    # ── COL 3: Support Center + Social ───────────────────────────────────────
    building_svg = "<rect x='2' y='7' width='20' height='14' rx='2' ry='2'/><path d='M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16'/>"

    col3 = _column(34, [
        _footer_label("Support Center"),
        _footer_text(
            _contact_row(building_svg, "AKR Tower – 9th Floor<br>Jl. Panjang No. 5, Kebon Jeruk, Jakarta", align_start=True)
        ),
    ], extra_settings={
        "padding": {"unit": "px", "top": "0", "right": "0",
                    "bottom": "0", "left": "20", "isLinked": False},
    })

    # ── Copyright bar ─────────────────────────────────────────────────────────
    copyright_html = (
        "<p style='text-align:center;font-size:12px;color:#94A3B8;margin:0;'>"
        "© 2026 <strong style='color:#CBD5E1;'>PT. iLogo Infralogy Indonesia</strong>"
        " &nbsp;·&nbsp; All Rights Reserved."
        " &nbsp;·&nbsp; <a href='https://ilogoindonesia.com' target='_blank' "
        "style='color:#CBD5E1;text-decoration:none;'>ilogoindonesia.com</a></p>"
    )

    return [
        _section(
            _sec("#0F172A", pt=48, pr=50, pb=48, pl=50),
            [col1, col2, col3]
        ),
        _section(
            _sec("#020617", pt=16, pr=50, pb=16, pl=50),
            [_column(100, [_footer_text(copyright_html)])]
        ),
    ]


# ─────────────────────────────────────────────────────────────────────────────
# ── TEMPLATE: PRESTIGE ───────────────────────────────────────────────────────
# White hero, 2-col split, left-border accents, authority enterprise feel
# ─────────────────────────────────────────────────────────────────────────────

def _prestige_home(data, banner_url, stock_url, pc):
    vps   = data.get("value_propositions", [])
    brand = data.get("_brand_name", "Brand").capitalize()
    sections = []

    # ── Hero — white, 2-col split (text left, image right) ───────────────────
    text_col = _column(50, [
        _heading(data.get("hero_headline", ""), tag="h1", align="left",
                 color="#0F172A", size_px=44, weight="700"),
        _spacer(16),
        _text(
            f"<p style='color:#475569;font-size:17px;line-height:1.75;'>"
            f"{data.get('hero_subheadline', '')}</p>",
            color="#475569", size_px=17
        ),
        _spacer(24),
        _button(data.get("cta_button_text", "Hubungi Kami"),
                align="left", bg=pc, size_px=16, pad_v=14, pad_h=32),
    ])
    img_col = _column(50, [
        _image(banner_url, "Hero", 380, border_radius=16) if banner_url else _spacer(10)
    ])
    sections.append(_section(_sec("#FFFFFF", pt=80, pr=60, pb=80, pl=60),
                              [text_col, img_col]))

    # ── Value Props — "Mengapa {brand}?" header + 3 cards ────────────────────
    if vps:
        # Header row (slate-50 bg, top padding only)
        sections.append(_section(_sec("#F8FAFC", pt=60, pr=60, pb=0, pl=60), [
            _column(100, [
                _heading(f"Mengapa {brand}?", tag="h2", align="center",
                         color="#0F172A", size_px=30, weight="700"),
                _spacer(12),
                _text(
                    "<p style='text-align:center;color:#64748B;font-size:15px;"
                    "line-height:1.7;'>"
                    "Dipercaya oleh ratusan perusahaan di Indonesia untuk melindungi "
                    "dan mengelola infrastruktur IT mereka.</p>",
                    color="#64748B", size_px=15
                ),
            ])
        ]))
        # Cards row (same slate-50 bg, bottom padding only)
        cols = []
        vp_list = vps[:3]
        for i, vp in enumerate(vp_list):
            label = vp.get("icon_label", "").upper()
            html = (
                f"<p style='font-size:11px;font-weight:700;color:{pc};"
                f"text-transform:uppercase;letter-spacing:2px;"
                f"margin-bottom:10px;'>{label}</p>"
                f"<h3 style='font-size:18px;font-weight:600;color:#0F172A;"
                f"margin-bottom:10px;line-height:1.35;'>{vp.get('title', '')}</h3>"
                f"<p style='font-size:14px;color:#64748B;line-height:1.7;"
                f"margin:0;'>{vp.get('description', '')}</p>"
            )
            w = 33.34 if i == len(vp_list) - 1 else 33.33
            cols.append(_column(w, [_text(html)], _card_col_settings()))
        sections.append(_section(_sec("#F8FAFC", pt=32, pr=40, pb=60, pl=40), cols))

    # ── About — 2-col: stock image left, text right (matching mockup) ─────────
    about = data.get("about_summary", "")
    if about:
        title = data.get("title", f"Tentang {brand}")
        # Use inline HTML img so width:100% + object-fit:cover is guaranteed,
        # regardless of whether stock_url has a WP attachment ID.
        _about_img_html = (
            f"<div style='width:100%;height:340px;overflow:hidden;"
            f"border-radius:16px;box-shadow:0 4px 24px rgba(0,0,0,.10);'>"
            f"<img src='{stock_url}' alt='Tentang Kami' "
            f"style='width:100%;height:100%;object-fit:cover;display:block;'>"
            f"</div>"
        ) if stock_url else ""
        about_img_col = _column(50, [
            _widget("text-editor", {"editor": _about_img_html})
            if stock_url else _spacer(10)
        ])
        about_txt_col = _column(50, [
            _text(
                f"<p style='font-size:11px;font-weight:700;color:{pc};"
                f"text-transform:uppercase;letter-spacing:2px;margin:0 0 12px;'>"
                f"Tentang Kami</p>",
                size_px=11
            ),
            _heading(title, tag="h3", align="left",
                     color="#0F172A", size_px=28, weight="700"),
            _spacer(8),
            _text(
                f"<div style='width:48px;height:4px;background:{pc};"
                f"border-radius:2px;margin-bottom:20px;'></div>",
                size_px=14
            ),
            _text(_paras(about, "#475569", 15, "left"),
                  color="#475569", size_px=15),
        ])
        sections.append(_section(_sec("#FFFFFF", pt=70, pr=60, pb=70, pl=60),
                                  [about_img_col, about_txt_col]))

    # ── Closing CTA strip — brand color bg, white text + button ──────────────
    closing = data.get("closing_statement", "")
    if closing:
        sections.append(_section(_sec(pc, pt=60, pr=60, pb=60, pl=60), [
            _column(100, [
                _text(
                    f"<p style='text-align:center;font-size:17px;font-weight:500;"
                    f"color:#FFFFFF;line-height:1.8;margin-bottom:24px;'>{closing}</p>",
                    color="#FFFFFF", size_px=17
                ),
                _widget("button", {
                    "text": data.get("cta_button_text", "Hubungi Tim Kami"),
                    "align": "center",
                    "background_color": "#FFFFFF",
                    "button_text_color": pc,
                    "border_radius": {"unit": "px", "top": "10", "right": "10",
                                      "bottom": "10", "left": "10", "isLinked": True},
                    "typography_font_size": {"unit": "px", "size": 15},
                    "typography_font_weight": "600",
                    "padding": {"unit": "px", "top": "14", "right": "32",
                                "bottom": "14", "left": "32", "isLinked": False},
                }),
            ])
        ]))

    return sections


def _prestige_solusi(data, banner_url, stock_url, pc):
    lite = _lighten(pc, 0.90)
    sections = []

    sections.append(_section(_sec("#FFFFFF", pt=70, pr=60, pb=40, pl=60), [
        _column(100, [
            _heading(data.get("title", "Solusi Kami"), tag="h1",
                     align="left", color="#0F172A", size_px=40, weight="700"),
            _spacer(10),
            _text(
                f"<p style='font-size:16px;color:#475569;line-height:1.75;'>"
                f"{data.get('intro', '')}</p>",
                color="#475569", size_px=16
            ),
        ])
    ]))

    if banner_url:
        sections.append(_section(_sec("#F8FAFC", pt=0, pb=0, pr=60, pl=60),
                                 [_column(100, [_image(banner_url, "", 320)])]))
    if stock_url:
        sections.append(_section(_sec("#F8FAFC", pt=16, pb=0, pr=60, pl=60),
                                 [_column(100, [_image(stock_url, "", 280)])]))

    for i, sol in enumerate(data.get("solutions_list", [])):
        num_html = (
            f"<p style='font-size:30px;font-weight:800;color:{_lighten(pc, 0.6)};"
            f"line-height:1;margin:0;'>{str(i+1).zfill(2)}</p>"
        )
        sections.append(_section(
            _sec("#FFFFFF", pt=0, pr=60, pb=20, pl=60),
            [
                _column(8, [_text(num_html, size_px=30)]),
                _column(92, [
                    _heading(sol.get("target", ""), tag="h4", align="left",
                             color="#0F172A", size_px=17, weight="600"),
                    _spacer(6),
                    _text(
                        f"<p style='font-size:14px;color:#475569;line-height:1.8;'>"
                        f"{sol.get('benefit', '')}</p>",
                        color="#475569", size_px=14
                    ),
                ], extra_settings={
                    "border_left_width": {"unit": "px", "size": 3},
                    "border_color": pc,
                    "background_background": "classic",
                    "background_color": "#F8FAFC",
                    "padding": {"unit": "px", "top": "18", "right": "20",
                                "bottom": "18", "left": "20", "isLinked": False},
                }),
            ]
        ))

    return sections


def _prestige_contact(data, pc):
    return [
        _section(_sec("#FFFFFF", pt=80, pr=60, pb=40, pl=60), [
            _column(100, [
                _heading(data.get("title", "Hubungi Kami"), tag="h1",
                         align="left", color="#0F172A", size_px=40, weight="700"),
                _spacer(10),
                _heading(data.get("headline", ""), tag="h2",
                         align="left", color=pc, size_px=22, weight="600"),
                _spacer(14),
                _text(
                    f"<p style='font-size:15px;color:#475569;line-height:1.8;'>"
                    f"{data.get('cta_text', '')}</p>",
                    color="#475569", size_px=15
                ),
            ])
        ]),
        _section(_sec("#F8FAFC", pt=24, pr=60, pb=70, pl=60), [
            _column(100, [
                _text(
                    "<div style='background:#fff;border:2px dashed #CBD5E1;"
                    "padding:48px;text-align:center;border-radius:12px;'>"
                    "<p style='color:#94A3B8;margin:0;font-size:15px;'>"
                    "[Formulir Kontak Standard Hubungi Kami iLogo]</p></div>",
                    color="#888", size_px=15
                )
            ])
        ]),
    ]


def _prestige_product(prod, banner_url, stock_url, pc):
    lite  = _lighten(pc, 0.90)
    name  = prod.get("name", "Produk")
    tag_  = prod.get("tagline", "")
    desc  = prod.get("description", "")
    feats = prod.get("key_features", [])
    ucs   = prod.get("use_cases", [])
    why   = prod.get("why_choose", "")
    tu    = prod.get("target_user", "")
    sections = []

    # ── Hero — 2-col: label + name + tagline left | banner image right ────────
    sections.append(_section(_sec("#FFFFFF", pt=70, pr=60, pb=60, pl=60), [
        _column(55, [
            _text(
                f"<p style='font-size:11px;font-weight:700;color:{pc};"
                f"text-transform:uppercase;letter-spacing:2px;margin:0 0 14px;'>"
                f"Produk Unggulan</p>",
                size_px=11
            ),
            _heading(name, tag="h1", align="left",
                     color="#0F172A", size_px=38, weight="700"),
            _spacer(10),
            _text(
                f"<p style='font-size:16px;font-weight:600;color:{pc};"
                f"margin:0;line-height:1.5;'>{tag_}</p>",
                color=pc, size_px=16
            ),
        ]),
        _column(45, [
            _image(banner_url, name, 340, border_radius=12) if banner_url else _spacer(10)
        ]),
    ]))

    # ── Main content — 2-col: description left | features+UCs sidebar right ───
    if desc or feats or ucs:
        # Features card — brand-tinted bg, rounded, check icon per item
        feats_card = ""
        if feats:
            feat_items = "".join(
                f"<li style='display:flex;align-items:flex-start;gap:10px;"
                f"margin-bottom:10px;list-style:none;'>"
                f"<span style='color:{pc};font-weight:700;flex-shrink:0;"
                f"font-size:14px;margin-top:1px;'>✓</span>"
                f"<span style='color:#374151;line-height:1.7;font-size:13px;'>{f}</span>"
                f"</li>"
                for f in feats
            )
            feats_card = (
                f"<div style='background:{lite};border:1px solid #E2E8F0;"
                f"border-radius:12px;padding:20px 22px;margin-bottom:16px;'>"
                f"<p style='font-size:11px;font-weight:700;color:#64748B;"
                f"text-transform:uppercase;letter-spacing:1px;margin:0 0 14px;'>"
                f"Fitur Utama</p>"
                f"<ul style='padding:0;margin:0;'>{feat_items}</ul>"
                f"</div>"
            )

        # Use case rows — left-border accent, reliable for long text in Elementor
        ucs_html = ""
        if ucs:
            uc_rows = "".join(
                f"<div style='display:flex;align-items:flex-start;gap:10px;"
                f"padding:8px 0;border-bottom:1px solid #E2E8F0;'>"
                f"<span style='width:3px;align-self:stretch;"
                f"background:{pc};border-radius:2px;flex-shrink:0;'></span>"
                f"<span style='font-size:12px;color:#374151;line-height:1.6;'>{u}</span>"
                f"</div>"
                for u in ucs
            )
            ucs_html = (
                f"<div style='background:#FFFFFF;border:1px solid #E2E8F0;"
                f"border-radius:10px;padding:16px 18px;'>"
                f"<p style='font-size:11px;font-weight:700;color:#64748B;"
                f"text-transform:uppercase;letter-spacing:1px;margin:0 0 8px;'>"
                f"Cocok untuk</p>"
                f"{uc_rows}"
                f"</div>"
            )

        desc_col = _column(60, [
            _text(_paras(desc, "#475569", 15, "left"), color="#475569", size_px=15)
        ]) if desc else None

        sidebar_col = _column(40, [
            _widget("text-editor", {"editor": feats_card + ucs_html})
        ]) if (feats_card or ucs_html) else None

        cols = [c for c in [desc_col, sidebar_col] if c]
        if cols:
            sections.append(_section(_sec("#FFFFFF", pt=50, pr=60, pb=50, pl=60), cols))

    # ── Bottom: "Mengapa" + "Untuk Siapa" — 2-col if both, single col if one ──
    if why or tu:
        mengapa_html = (
            f"<div style='border-left:4px solid {pc};padding:24px 28px;"
            f"border-radius:0 12px 12px 0;background:{lite};'>"
            f"<p style='font-size:11px;font-weight:700;color:#64748B;"
            f"text-transform:uppercase;letter-spacing:1px;margin:0 0 10px;'>"
            f"Mengapa {name}?</p>"
            f"<p style='font-size:14px;color:#374151;line-height:1.8;"
            f"margin:0 0 18px;'>{why}</p>"
            f"<span style='font-size:13px;font-weight:600;color:{pc};"
            f"border-bottom:1px solid {pc};padding-bottom:1px;'>"
            f"Jadwalkan Demo &rarr;</span>"
            f"</div>"
        ) if why else ""

        untuk_html = (
            f"<div style='background:#F8FAFC;border:1px solid #E2E8F0;"
            f"border-radius:12px;padding:24px 26px;'>"
            f"<p style='font-size:11px;font-weight:700;color:#64748B;"
            f"text-transform:uppercase;letter-spacing:1px;margin:0 0 10px;'>"
            f"Untuk Siapa?</p>"
            f"<p style='font-size:14px;color:#475569;line-height:1.8;margin:0;'>{tu}</p>"
            f"</div>"
        ) if tu else ""

        if why and tu:
            sections.append(_section(_sec("#F8FAFC", pt=50, pr=60, pb=50, pl=60), [
                _column(60, [_widget("text-editor", {"editor": mengapa_html})]),
                _column(40, [_widget("text-editor", {"editor": untuk_html})]),
            ]))
        elif why:
            sections.append(_section(_sec("#F8FAFC", pt=50, pr=60, pb=50, pl=60), [
                _column(100, [_widget("text-editor", {"editor": mengapa_html})])
            ]))
        elif tu:
            sections.append(_section(_sec("#F8FAFC", pt=50, pr=60, pb=50, pl=60), [
                _column(100, [_widget("text-editor", {"editor": untuk_html})])
            ]))

    return sections


# ─────────────────────────────────────────────────────────────────────────────
# ── TEMPLATE: CLARITY ────────────────────────────────────────────────────────
# Pure white, very spacious, centered hero with brand band, numbered solutions
# ─────────────────────────────────────────────────────────────────────────────

def _clarity_home(data, banner_url, stock_url, pc):
    lite = _lighten(pc, 0.90)
    vps  = data.get("value_propositions", [])
    sections = []

    # Hero — centered, brand accent line at top
    accent_bar = (
        f"<div style='width:56px;height:4px;background:{pc};"
        f"border-radius:2px;margin:0 auto 32px;'></div>"
    )
    sections.append(_section(_sec("#FFFFFF", pt=90, pr=80, pb=70, pl=80), [
        _column(100, [
            _text(accent_bar, size_px=14),
            _heading(data.get("hero_headline", ""), tag="h1", align="center",
                     color="#0F172A", size_px=48, weight="800"),
            _spacer(16),
            _text(
                f"<p style='text-align:center;font-size:18px;color:#64748B;"
                f"line-height:1.75;max-width:680px;margin:0 auto;'>"
                f"{data.get('hero_subheadline', '')}</p>",
                color="#64748B", size_px=18
            ),
            _spacer(28),
            _button(data.get("cta_button_text", "Mulai Sekarang"),
                    align="center", bg=pc, size_px=16, pad_v=14, pad_h=40),
        ])
    ]))

    if banner_url:
        sections.append(_section(_sec("#F8FAFC", pt=0, pb=0, pr=60, pl=60),
                                 [_column(100, [_image(banner_url, "", 360)])]))
    if stock_url:
        sections.append(_section(_sec("#F8FAFC", pt=16, pb=0, pr=60, pl=60),
                                 [_column(100, [_image(stock_url, "", 300)])]))

    # About — centered
    about = data.get("about_summary", "")
    if about:
        sections.append(_section(_sec("#FFFFFF", pt=70, pr=80, pb=60, pl=80), [
            _column(100, [
                _heading("Tentang Kami", tag="h2", align="center",
                         color="#0F172A", size_px=32, weight="800"),
                _spacer(20),
                _text(_paras(about, "#64748B", 15, "left"),
                      color="#64748B", size_px=15),
            ])
        ]))

    # Value props — numbered
    if vps:
        cols = []
        for i, vp in enumerate(vps[:3]):
            num_color = _lighten(pc, 0.65)
            html = (
                f"<p style='font-size:34px;font-weight:800;color:{num_color};"
                f"line-height:1;margin-bottom:12px;'>{str(i+1).zfill(2)}</p>"
                f"<h3 style='font-size:17px;font-weight:600;color:#0F172A;"
                f"margin-bottom:8px;'>{vp.get('title', '')}</h3>"
                f"<p style='font-size:13px;color:#64748B;line-height:1.7;"
                f"margin:0;'>{vp.get('description', '')}</p>"
            )
            col_extra = {
                "padding": {"unit": "px", "top": "28", "right": "24",
                            "bottom": "28", "left": "24", "isLinked": False},
            }
            if i < 2:
                col_extra["border_right_width"] = {"unit": "px", "size": 1}
                col_extra["border_color"] = "#E2E8F0"
            w = 33.34 if i == len(vps[:3]) - 1 else 33.33
            cols.append(_column(w, [_text(html)], extra_settings=col_extra))
        sections.append(_section(_sec("#F8FAFC", pt=60, pr=40, pb=60, pl=40), cols))

    closing = data.get("closing_statement", "")
    if closing:
        sections.append(_section(_sec(lite, pt=50, pb=50), [
            _column(100, [
                _text(
                    f"<p style='text-align:center;font-size:18px;font-weight:500;"
                    f"color:#0F172A;line-height:1.8;'>{closing}</p>",
                    color="#0F172A", size_px=18
                )
            ])
        ]))

    return sections


def _clarity_solusi(data, banner_url, stock_url, pc):
    sections = []
    lite_num = _lighten(pc, 0.65)

    sections.append(_section(_sec("#FFFFFF", pt=70, pr=80, pb=40, pl=80), [
        _column(100, [
            _heading(data.get("title", "Solusi"), tag="h1",
                     align="center", color="#0F172A", size_px=42, weight="800"),
            _spacer(12),
            _text(
                f"<p style='text-align:center;font-size:16px;color:#64748B;"
                f"line-height:1.75;'>{data.get('intro', '')}</p>",
                color="#64748B", size_px=16
            ),
        ])
    ]))

    if banner_url:
        sections.append(_section(_sec("#F8FAFC", pt=0, pb=0, pr=60, pl=60),
                                 [_column(100, [_image(banner_url, "", 320)])]))
    if stock_url:
        sections.append(_section(_sec("#F8FAFC", pt=16, pb=0, pr=60, pl=60),
                                 [_column(100, [_image(stock_url, "", 280)])]))

    solutions = data.get("solutions_list", [])
    half = (len(solutions) + 1) // 2
    left_html = right_html = ""
    for i, sol in enumerate(solutions):
        card = (
            f"<div style='background:#fff;border:1px solid #E2E8F0;"
            f"border-radius:10px;padding:22px;margin-bottom:16px;'>"
            f"<p style='font-size:28px;font-weight:800;color:{lite_num};"
            f"line-height:1;margin-bottom:8px;'>{str(i+1).zfill(2)}</p>"
            f"<h4 style='font-size:15px;font-weight:600;color:#0F172A;"
            f"margin-bottom:6px;'>{sol.get('target', '')}</h4>"
            f"<p style='font-size:13px;color:#64748B;line-height:1.75;margin:0;'>"
            f"{sol.get('benefit', '')}</p></div>"
        )
        if i < half:
            left_html += card
        else:
            right_html += card

    sections.append(_section(_sec("#F8FAFC", pt=40, pr=50, pb=60, pl=50), [
        _column(50, [_text(left_html)]),
        _column(50, [_text(right_html)]),
    ]))
    return sections


def _clarity_contact(data, pc):
    return [
        _section(_sec("#FFFFFF", pt=80, pr=80, pb=40, pl=80), [
            _column(100, [
                _heading(data.get("title", "Hubungi Kami"), tag="h1",
                         align="center", color="#0F172A", size_px=42, weight="800"),
                _spacer(10),
                _heading(data.get("headline", ""), tag="h2",
                         align="center", color=pc, size_px=22, weight="600"),
                _spacer(14),
                _text(
                    f"<p style='text-align:center;font-size:15px;color:#64748B;"
                    f"line-height:1.8;max-width:600px;margin:0 auto;'>"
                    f"{data.get('cta_text', '')}</p>",
                    color="#64748B", size_px=15
                ),
            ])
        ]),
        _section(_sec("#F8FAFC", pt=24, pr=80, pb=70, pl=80), [
            _column(100, [
                _text(
                    "<div style='background:#fff;border:2px dashed #CBD5E1;"
                    "padding:48px;text-align:center;border-radius:14px;'>"
                    "<p style='color:#94A3B8;margin:0;font-size:15px;'>"
                    "[Formulir Kontak Standard Hubungi Kami iLogo]</p></div>",
                    color="#888", size_px=15
                )
            ])
        ]),
    ]


def _clarity_product(prod, banner_url, stock_url, pc):
    lite = _lighten(pc, 0.90)
    name  = prod.get("name", "Produk")
    tag_  = prod.get("tagline", "")
    desc  = prod.get("description", "")
    feats = prod.get("key_features", [])
    ucs   = prod.get("use_cases", [])
    why   = prod.get("why_choose", "")
    tu    = prod.get("target_user", "")
    sections = []

    # Centered hero with accent bar
    accent_bar = (
        f"<div style='width:48px;height:4px;background:{pc};"
        f"border-radius:2px;margin:0 auto 24px;'></div>"
    )
    sections.append(_section(_sec("#FFFFFF", pt=80, pr=80, pb=60, pl=80), [
        _column(100, [
            _text(accent_bar, size_px=14),
            _heading(name, tag="h1", align="center",
                     color="#0F172A", size_px=42, weight="800"),
            _spacer(10),
            _text(f"<p style='text-align:center;font-size:17px;font-weight:600;"
                  f"color:{pc};'>{tag_}</p>", color=pc, size_px=17),
        ])
    ]))

    if banner_url:
        sections.append(_section(_sec("#F8FAFC", pt=0, pb=0, pr=60, pl=60),
                                 [_column(100, [_image(banner_url, name, 360)])]))
    if stock_url:
        sections.append(_section(_sec("#F8FAFC", pt=16, pb=0, pr=60, pl=60),
                                 [_column(100, [_image(stock_url, "", 300)])]))

    if desc:
        sections.append(_section(_sec("#FFFFFF", pt=50, pr=80, pb=40, pl=80), [
            _column(100, [
                _text(_paras(desc, "#64748B", 15, "left"), color="#64748B", size_px=15)
            ])
        ]))

    if feats or ucs:
        left = _column(60, [
            _heading("Fitur Utama", tag="h3", align="left",
                     color="#0F172A", size_px=20, weight="700"),
            _spacer(14),
            _text(_features_html(feats, pc, 14)),
        ]) if feats else None
        right = _column(40, [
            _heading("Cocok Untuk", tag="h3", align="left",
                     color="#0F172A", size_px=20, weight="700"),
            _spacer(14),
            _text(_uc_html(ucs, 13)),
        ]) if ucs else None
        cols = [c for c in [left, right] if c]
        if cols:
            sections.append(_section(_sec("#F8FAFC", pt=50, pr=60, pb=50, pl=60), cols))

    if why:
        sections.append(_section(_sec(lite, pt=50, pr=80, pb=50, pl=80), [
            _column(80, [
                _heading("Mengapa Memilih Produk Ini?", tag="h3",
                         align="left", color="#0F172A", size_px=20),
                _spacer(10),
                _text(_paras(why, "#0F172A", 15, "left"), color="#0F172A", size_px=15),
            ]),
            _column(20, [_spacer(10)]),
        ]))

    if tu:
        sections.append(_section(_sec("#FFFFFF", pt=40, pr=80, pb=50, pl=80), [
            _column(100, [
                _heading("Untuk Siapa?", tag="h3", align="left",
                         color="#0F172A", size_px=20),
                _spacer(8),
                _text(f"<p style='font-size:15px;color:#64748B;line-height:1.8;'>{tu}</p>",
                      color="#64748B", size_px=15),
            ])
        ]))

    return sections


# ─────────────────────────────────────────────────────────────────────────────
# ── TEMPLATE: MOMENTUM ───────────────────────────────────────────────────────
# Brand-dark hero, energetic, infrastructure feel, 3-col icon VPs
# ─────────────────────────────────────────────────────────────────────────────

def _momentum_home(data, banner_url, stock_url, pc):
    dark = _darken(pc, 0.35)
    vps  = data.get("value_propositions", [])
    sections = []

    # Brand-dark hero — full width, centered
    hero_elements = [
        _heading(data.get("hero_headline", ""), tag="h1", align="center",
                 color="#FFFFFF", size_px=48, weight="700"),
        _spacer(16),
        _text(
            f"<p style='text-align:center;font-size:18px;"
            f"color:rgba(255,255,255,0.82);line-height:1.7;'>"
            f"{data.get('hero_subheadline', '')}</p>",
            color="#FFFFFF", size_px=18
        ),
        _spacer(28),
        _button(data.get("cta_button_text", "Lihat Produk Kami"),
                align="center", bg=pc, size_px=16, pad_v=15, pad_h=42),
    ]
    if banner_url:
        sections.append(_section(
            {**_sec(dark, pt=0, pr=60, pb=70, pl=60)},
            [_column(100, [
                _image(banner_url, "Hero", 380),
                _spacer(32),
                *hero_elements,
            ])]
        ))
    else:
        sections.append(_section(
            {**_sec(dark, pt=90, pr=80, pb=80, pl=80)},
            [_column(100, hero_elements)]
        ))

    if stock_url:
        sections.append(_section(_sec("#F1F5F9", pt=0, pb=0, pr=60, pl=60),
                                 [_column(100, [_image(stock_url, "", 300)])]))

    # About — centered on light bg
    about = data.get("about_summary", "")
    if about:
        sections.append(_section(_sec("#FFFFFF", pt=70, pr=70, pb=60, pl=70), [
            _column(100, [
                _heading("Tentang Kami", tag="h2", align="center",
                         color="#0F172A", size_px=32, weight="700"),
                _spacer(20),
                _text(_paras(about, "#475569", 15, "left"), color="#475569", size_px=15),
            ])
        ]))

    # Value props — 3-col with vertical dividers
    if vps:
        cols = []
        for i, vp in enumerate(vps[:3]):
            num = str(i + 1)
            lite_num = _lighten(pc, 0.80)
            html = (
                f"<div style='text-align:center;padding:8px 16px;'>"
                f"<div style='width:48px;height:48px;border-radius:12px;"
                f"background:{lite_num};display:flex;align-items:center;"
                f"justify-content:center;margin:0 auto 14px;'>"
                f"<span style='font-size:20px;font-weight:800;color:{pc};'>{num}</span></div>"
                f"<h3 style='font-size:17px;font-weight:700;color:#0F172A;"
                f"margin-bottom:8px;text-align:center;'>{vp.get('title', '')}</h3>"
                f"<p style='font-size:13px;color:#64748B;line-height:1.7;"
                f"text-align:center;margin:0;'>{vp.get('description', '')}</p></div>"
            )
            col_extra = {
                "padding": {"unit": "px", "top": "0", "right": "0",
                            "bottom": "0", "left": "0", "isLinked": False},
            }
            if i < 2:
                col_extra["border_right_width"] = {"unit": "px", "size": 1}
                col_extra["border_color"] = "#E2E8F0"
            w = 33.34 if i == len(vps[:3]) - 1 else 33.33
            cols.append(_column(w, [_text(html)], extra_settings=col_extra))
        sections.append(_section(_sec("#F8FAFC", pt=60, pr=40, pb=60, pl=40), cols))

    closing = data.get("closing_statement", "")
    if closing:
        sections.append(_section({**_sec(dark, pt=50, pb=50)}, [
            _column(100, [
                _text(
                    f"<p style='text-align:center;font-size:17px;"
                    f"line-height:1.8;color:rgba(255,255,255,0.9);'>{closing}</p>",
                    color="#FFFFFF", size_px=17
                )
            ])
        ]))

    return sections


def _momentum_solusi(data, banner_url, stock_url, pc):
    dark = _darken(pc, 0.35)
    sections = []

    sections.append(_section({**_sec(dark, pt=70, pr=80, pb=50, pl=80)}, [
        _column(100, [
            _heading(data.get("title", "Solusi"), tag="h1",
                     align="center", color="#FFFFFF", size_px=42, weight="700"),
            _spacer(12),
            _text(
                f"<p style='text-align:center;font-size:16px;"
                f"color:rgba(255,255,255,0.82);line-height:1.75;'>"
                f"{data.get('intro', '')}</p>",
                color="#FFFFFF", size_px=16
            ),
        ])
    ]))

    if banner_url:
        sections.append(_section(_sec("#F1F5F9", pt=0, pb=0, pr=60, pl=60),
                                 [_column(100, [_image(banner_url, "", 320)])]))
    if stock_url:
        sections.append(_section(_sec("#F1F5F9", pt=16, pb=0, pr=60, pl=60),
                                 [_column(100, [_image(stock_url, "", 280)])]))

    solutions = data.get("solutions_list", [])
    left_html = right_html = ""
    for i, sol in enumerate(solutions):
        card = (
            f"<div style='background:#fff;border:1px solid #E2E8F0;"
            f"border-radius:10px;padding:22px;margin-bottom:16px;'>"
            f"<h4 style='font-size:15px;font-weight:700;color:#0F172A;"
            f"margin-bottom:8px;'>{sol.get('target', '')}</h4>"
            f"<p style='font-size:13px;color:#64748B;line-height:1.75;margin:0;'>"
            f"{sol.get('benefit', '')}</p></div>"
        )
        if i % 3 == 2:
            right_html += card
        else:
            left_html += card

    sections.append(_section(_sec("#F8FAFC", pt=40, pr=50, pb=60, pl=50), [
        _column(65, [_text(left_html)]),
        _column(35, [_text(right_html)]),
    ]))
    return sections


def _momentum_contact(data, pc):
    dark  = _darken(pc, 0.35)
    light = _lighten(pc, 0.55)
    return [
        _section({**_sec(dark, pt=80, pr=80, pb=50, pl=80)}, [
            _column(100, [
                _heading(data.get("title", "Hubungi Kami"), tag="h1",
                         align="center", color="#FFFFFF", size_px=42, weight="700"),
                _spacer(10),
                _heading(data.get("headline", ""), tag="h2",
                         align="center", color=light, size_px=22, weight="600"),
                _spacer(14),
                _text(
                    f"<p style='text-align:center;font-size:15px;"
                    f"color:rgba(255,255,255,0.82);line-height:1.8;'>"
                    f"{data.get('cta_text', '')}</p>",
                    color="#FFFFFF", size_px=15
                ),
            ])
        ]),
        _section(_sec("#F8FAFC", pt=30, pr=80, pb=70, pl=80), [
            _column(100, [
                _text(
                    "<div style='background:#fff;border:2px dashed #CBD5E1;"
                    "padding:48px;text-align:center;border-radius:14px;'>"
                    "<p style='color:#94A3B8;margin:0;font-size:15px;'>"
                    "[Formulir Kontak Standard Hubungi Kami iLogo]</p></div>",
                    color="#888", size_px=15
                )
            ])
        ]),
    ]


def _momentum_product(prod, banner_url, stock_url, pc):
    dark  = _darken(pc, 0.35)
    light = _lighten(pc, 0.55)
    name  = prod.get("name", "Produk")
    tag_  = prod.get("tagline", "")
    desc  = prod.get("description", "")
    feats = prod.get("key_features", [])
    ucs   = prod.get("use_cases", [])
    why   = prod.get("why_choose", "")
    tu    = prod.get("target_user", "")
    sections = []

    # Brand-dark 2-col hero
    sections.append(_section({**_sec(dark, pt=80, pr=60, pb=60, pl=60)}, [
        _column(55, [
            _heading(name, tag="h1", align="left",
                     color="#FFFFFF", size_px=40, weight="700"),
            _spacer(10),
            _text(f"<p style='font-size:17px;font-weight:600;color:{light};'>"
                  f"{tag_}</p>", color="#FFFFFF", size_px=17),
        ]),
        _column(45, [
            _image(banner_url, name, 360) if banner_url else _spacer(10)
        ]),
    ]))

    if stock_url:
        sections.append(_section(_sec("#F1F5F9", pt=0, pb=0, pr=60, pl=60),
                                 [_column(100, [_image(stock_url, "", 300)])]))

    if desc:
        sections.append(_section(_sec("#FFFFFF", pt=50, pr=60, pb=40, pl=60), [
            _column(100, [
                _text(_paras(desc, "#475569", 15, "left"), color="#475569", size_px=15)
            ])
        ]))

    if feats or ucs:
        left = _column(60, [
            _heading("Fitur Utama", tag="h3", align="left",
                     color="#0F172A", size_px=20, weight="700"),
            _spacer(14),
            _text(_features_html(feats, pc, 14)),
        ]) if feats else None
        right = _column(40, [
            _heading("Digunakan Untuk", tag="h3", align="left",
                     color="#0F172A", size_px=20, weight="700"),
            _spacer(14),
            _text(_uc_html(ucs, 13)),
        ]) if ucs else None
        cols = [c for c in [left, right] if c]
        if cols:
            sections.append(_section(_sec("#F8FAFC", pt=50, pr=60, pb=50, pl=60), cols))

    if why:
        sections.append(_section({**_sec("#1E293B", pt=50, pr=60, pb=50, pl=60)}, [
            _column(100, [
                _heading("Mengapa Memilih Produk Ini?", tag="h3",
                         align="left", color="#FFFFFF", size_px=20),
                _spacer(10),
                _text(_paras(why, "rgba(255,255,255,0.85)", 15, "left"),
                      color="#FFFFFF", size_px=15),
            ])
        ]))

    if tu:
        sections.append(_section(_sec("#FFFFFF", pt=40, pr=60, pb=50, pl=60), [
            _column(100, [
                _heading("Untuk Siapa?", tag="h3", align="left",
                         color="#0F172A", size_px=20),
                _spacer(8),
                _text(f"<p style='font-size:15px;color:#475569;line-height:1.8;'>{tu}</p>",
                      color="#475569", size_px=15),
            ])
        ]))

    return sections


# ─────────────────────────────────────────────────────────────────────────────
# Shared produk index builder
# ─────────────────────────────────────────────────────────────────────────────

def _produk_index_sections(data, banner_url, stock_url, pc, t):
    dark = _darken(pc, 0.35)

    if t == "prestige":
        hero_bg   = _sec("#FFFFFF", pt=80, pr=60, pb=60, pl=60)
        h_color   = "#0F172A"
        sub_color = "#475569"
        sub_align = "left"
    elif t == "clarity":
        hero_bg   = _sec("#FFFFFF", pt=90, pr=80, pb=60, pl=80)
        h_color   = "#0F172A"
        sub_color = "#64748B"
        sub_align = "center"
    else:
        hero_bg   = {**_sec(dark, pt=80, pr=80, pb=60, pl=80)}
        h_color   = "#FFFFFF"
        sub_color = "rgba(255,255,255,0.82)"
        sub_align = "center"

    h_align = "left" if t == "prestige" else "center"

    sections = [
        _section(hero_bg, [_column(100, [
            _heading(data.get("intro_page_title", "Produk & Solusi Kami"),
                     tag="h1", align=h_align, color=h_color,
                     size_px=42, weight="700"),
            _spacer(12),
            _text(
                f"<p style='text-align:{sub_align};font-size:16px;"
                f"color:{sub_color};line-height:1.75;'>"
                f"{data.get('intro_page_description', '')}</p>",
                color=sub_color, size_px=16
            ),
        ])])
    ]

    if banner_url:
        sections.append(_section(_sec("#F8FAFC", pt=0, pb=0, pr=60, pl=60),
                                 [_column(100, [_image(banner_url, "", 340)])]))
    if stock_url:
        sections.append(_section(_sec("#F8FAFC", pt=16, pb=0, pr=60, pl=60),
                                 [_column(100, [_image(stock_url, "", 290)])]))

    for prod in data.get("products_list", []):
        name    = prod.get("name", "")
        tagline = prod.get("tagline", "")
        desc    = prod.get("description", "")
        first   = next((p.strip() for p in desc.split("\n") if p.strip()), desc)
        feats   = prod.get("key_features", [])[:3]
        ucs     = prod.get("use_cases", [])

        card_html = (
            f"<h3 style='font-size:20px;font-weight:700;color:#0F172A;"
            f"margin-bottom:6px;'>{name}</h3>"
            f"<p style='font-size:14px;font-weight:600;color:{pc};"
            f"font-style:italic;margin-bottom:12px;'>{tagline}</p>"
            f"<p style='font-size:14px;color:#475569;line-height:1.8;"
            f"margin-bottom:14px;'>{first}</p>"
            + (_features_html(feats, pc, 13) if feats else "")
            + (_uc_html(ucs, 12) if ucs else "")
        )
        sections.append(_section(
            _sec("#FFFFFF", pt=0, pr=60, pb=24, pl=60),
            [_column(100, [_text(card_html)], _card_col_settings())]
        ))

    return sections


# ─────────────────────────────────────────────────────────────────────────────
# ── PUBLIC API ───────────────────────────────────────────────────────────────
# ─────────────────────────────────────────────────────────────────────────────

VALID = {"prestige", "clarity", "momentum"}


def _t(template):
    v = (template or "prestige").lower().strip()
    return v if v in VALID else "prestige"


def _append_footer(sections, brand_name=""):
    sections.extend(_footer_section(brand_name))
    return sections


def build_home(data, banner_url="", stock_url="",
               primary_color="#1E7E34", template="prestige"):
    t = _t(template)
    brand = data.get("_brand_name", "")
    if t == "prestige":
        s = _prestige_home(data, banner_url, stock_url, primary_color)
    elif t == "clarity":
        s = _clarity_home(data, banner_url, stock_url, primary_color)
    else:
        s = _momentum_home(data, banner_url, stock_url, primary_color)
    return _to_json(_append_footer(s, brand))


def build_produk_index(data, banner_url="", stock_url="",
                       primary_color="#1E7E34", template="prestige"):
    t = _t(template)
    brand = data.get("_brand_name", "")
    s = _produk_index_sections(data, banner_url, stock_url, primary_color, t)
    return _to_json(_append_footer(s, brand))


def build_solusi(data, banner_url="", stock_url="",
                 primary_color="#1E7E34", template="prestige"):
    t = _t(template)
    brand = data.get("_brand_name", "")
    if t == "prestige":
        s = _prestige_solusi(data, banner_url, stock_url, primary_color)
    elif t == "clarity":
        s = _clarity_solusi(data, banner_url, stock_url, primary_color)
    else:
        s = _momentum_solusi(data, banner_url, stock_url, primary_color)
    return _to_json(_append_footer(s, brand))


def build_contact(data, primary_color="#1E7E34", template="prestige"):
    t = _t(template)
    brand = data.get("_brand_name", "")
    if t == "prestige":
        s = _prestige_contact(data, primary_color)
    elif t == "clarity":
        s = _clarity_contact(data, primary_color)
    else:
        s = _momentum_contact(data, primary_color)
    return _to_json(_append_footer(s, brand))


def build_product_page(product_data, banner_url="", stock_url="",
                       footer_text="", primary_color="#1E7E34",
                       template="prestige"):
    t = _t(template)
    brand = product_data.get("_brand_name", "")
    if t == "prestige":
        s = _prestige_product(product_data, banner_url, stock_url, primary_color)
    elif t == "clarity":
        s = _clarity_product(product_data, banner_url, stock_url, primary_color)
    else:
        s = _momentum_product(product_data, banner_url, stock_url, primary_color)
    return _to_json(_append_footer(s, brand))