# -*- coding: utf-8 -*-
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
        "_column_size": width_pct,
        "column_width": {"unit": "%", "size": width_pct},
    }
    if extra_settings:
        s.update(extra_settings)
    return {"id": _id(), "elType": "column", "settings": s, "elements": elements}


def _widget(wtype, settings):
    return {"id": _id(), "elType": "widget", "widgetType": wtype, "settings": settings}


def _heading(text, tag="h2", align="center", color="#1A1A2E",
             size_px=36, weight="700"):
    return _widget("heading", {
        "title": text,
        "header_size": tag,
        "align": align,
        "title_color": color,
        "typography_font_size": {"unit": "px", "size": size_px},
        "typography_font_weight": weight,
    })


def _text(html, color="#555555", size_px=16):
    return _widget("text-editor", {
        "editor": html,
        "text_color": color,
        "typography_font_size": {"unit": "px", "size": size_px},
    })


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
        f"margin-top:1px;font-size:{size}px;'>&#10003;</span>"
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
# Header — global sticky navbar (deployed once via ElementsKit template)
# ─────────────────────────────────────────────────────────────────────────────

def _header_section(brand_name: str = "", primary_color: str = "#1E7E34"):
    """
    Sticky top navigation bar.
    Kolom kiri: nama brand sebagai link ke homepage.
    Kolom kanan: link navigasi (Beranda | Solusi | Produk | Kontak).
    Dideploy SEKALI via ElementsKit template — berlaku global di seluruh situs.
    """
    name = brand_name.capitalize() if brand_name else "Brand"

    logo_col = _column(30, [
        _widget("heading", {
            "title": (
                f"<a href='/' style='text-decoration:none;"
                f"color:{primary_color};font-weight:800;font-size:20px;"
                f"letter-spacing:-0.3px;'>{name} Indonesia</a>"
            ),
            "header_size": "p",
            "align": "left",
        })
    ])

    nav_html = " &nbsp;&nbsp;|&nbsp;&nbsp; ".join([
        "<a href='/beranda' style='color:#1E293B;font-weight:600;"
        "font-size:14px;text-decoration:none;'>Beranda</a>",
        "<a href='/solusi' style='color:#1E293B;font-weight:600;"
        "font-size:14px;text-decoration:none;'>Solusi</a>",
        "<a href='/produk' style='color:#1E293B;font-weight:600;"
        "font-size:14px;text-decoration:none;'>Produk</a>",
        "<a href='/kontak' style='color:#1E293B;font-weight:600;"
        "font-size:14px;text-decoration:none;'>Kontak</a>",
    ])

    nav_col = _column(70, [
        _widget("text-editor", {
            "editor": f"<p style='text-align:right;margin:0;'>{nav_html}</p>",
            "text_color": "#1E293B",
            "typography_font_size": {"unit": "px", "size": 14},
        })
    ])

    return [
        _section(
            {
                "background_background": "classic",
                "background_color":      "#FFFFFF",
                "border_bottom_border":  "solid",
                "border_bottom_width": {
                    "unit": "px",
                    "top": "0", "right": "0", "bottom": "1", "left": "0",
                    "isLinked": False,
                },
                "border_color": "#E2E8F0",
                "padding": {
                    "unit": "px",
                    "top": "14", "right": "40", "bottom": "14", "left": "40",
                    "isLinked": False,
                },
                "sticky":                "top",
                "sticky_offset":         0,
                "sticky_effects_offset": 0,
                "z_index":               999,
                "_element_width":        "full",
            },
            [logo_col, nav_col],
        )
    ]


# ─────────────────────────────────────────────────────────────────────────────
# Footer — rebuilt as a proper 3-column Elementor section (not HTML injection)
# ─────────────────────────────────────────────────────────────────────────────

def _footer_section(brand_name=""):
    name  = brand_name.capitalize() if brand_name else "Brand"
    email = brand_name.lower() if brand_name else "brand"

    def _footer_col(widgets, right_pad="20", left_pad="0"):
        return _column(33, widgets, extra_settings={
            "padding": {"unit": "px", "top": "0", "right": right_pad,
                        "bottom": "0", "left": left_pad, "isLinked": False},
        })

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

    def _footer_text(html):
        return _widget("text-editor", {
            "editor": html,
            "text_color": "#E2E8F0",
            "typography_font_size": {"unit": "px", "size": 13},
        })

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

    pin_svg  = "<path d='M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z'/><circle cx='12' cy='10' r='3'/>"
    mail_svg = "<path d='M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z'/><polyline points='22,6 12,13 2,6'/>"

    col2 = _footer_col([
        _footer_label("Sales &amp; Marketing"),
        _footer_text(
            f"<p style='font-size:13px;color:#F1F5F9;font-weight:600;margin:8px 0 12px;'>"
            f"PT iLogo Indonesia</p>"
            + _contact_row(pin_svg,  "Jl. Kebon Jeruk Raya<br>Villa Kebon Jeruk Office F1", align_start=True)
            + _contact_row(mail_svg, f"{email}@ilogoindonesia.com")
        ),
    ])

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

    copyright_html = (
        f"<p style='text-align:center;font-size:12px;color:#94A3B8;margin:0;'>"
        f"© 2026 <strong style='color:#CBD5E1;'>{name} Indonesia</strong>."
        f" All Rights Reserved</p>"
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

    # ── About — 2-col: stock image left, text right ───────────────────────────
    about = data.get("about_summary", "")
    if about:
        title = data.get("title", f"Tentang {brand}")
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
                f"Tentang {brand}</p>",
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
    sections = []
    solutions = data.get("solutions_list", [])

    # ── Hero — dark 2-col: label + title + intro left | banner image right ────
    label_html = (
        f"<p style='font-size:11px;font-weight:700;color:{pc};"
        f"text-transform:uppercase;letter-spacing:2px;margin:0 0 16px;'>Solusi</p>"
    )
    text_col = _column(55, [
        _text(label_html, size_px=11),
        _heading(data.get("title", "Solusi Kami"), tag="h1",
                 align="left", color="#FFFFFF", size_px=40, weight="700"),
        _spacer(16),
        _text(
            f"<p style='color:#CBD5E1;font-size:16px;line-height:1.75;'>"
            f"{data.get('intro', '')}</p>",
            color="#CBD5E1", size_px=16
        ),
    ])
    # Image contained with border-radius + padding — not flush/edge-to-edge
    img_col = _column(45, [
        _image(banner_url, "Solusi", 360, border_radius=14) if banner_url else _spacer(10)
    ], extra_settings={
        "padding": {"unit": "px", "top": "16", "right": "40",
                    "bottom": "16", "left": "16", "isLinked": False},
    })
    sections.append(_section(
        _sec("#0F172A", pt=70, pr=20, pb=70, pl=60),
        [text_col, img_col]
    ))

    # ── Intro band — white, centered ──────────────────────────────────────────
    # pb 40→24: closes the gap between intro band and first card row
    sections.append(_section(_sec("#FFFFFF", pt=48, pr=60, pb=24, pl=60), [
        _column(100, [
            _text(
                f"<p style='font-size:11px;font-weight:700;color:{pc};"
                f"text-transform:uppercase;letter-spacing:2px;text-align:center;"
                f"margin:0 0 10px;'>Implementasi &amp; Industri</p>",
                size_px=11
            ),
            _heading("Bagaimana Kami Membantu Anda?", tag="h2",
                     align="center", color="#0F172A", size_px=28, weight="700"),
            _spacer(6),
            _text(
                "<p style='font-size:15px;color:#64748B;line-height:1.7;"
                "text-align:center;max-width:560px;margin:0 auto;'>"
                "Solusi terstruktur untuk setiap industri dan kebutuhan IT Anda</p>",
                color="#64748B", size_px=15
            ),
        ])
    ]))

    # ── Solution cards — 2-col, brand-accented ────────────────────────────────
    if solutions:
        indexed = list(enumerate(solutions))
        rows    = [indexed[i:i + 2] for i in range(0, len(indexed), 2)]
        for r_idx, row in enumerate(rows):
            is_first = r_idx == 0
            is_last  = r_idx == len(rows) - 1
            pt = 24 if is_first else 10
            pb = 20 if is_last  else 10
            cols = []
            for i_abs, sol in row:
                num     = str(i_abs + 1).zfill(2)
                target  = sol.get("target", "")
                benefit = sol.get("benefit", "")
                card_html = (
                    f"<div style='background:#FFFFFF;border:0.5px solid #E2E8F0;"
                    f"border-top:3px solid {pc};border-radius:12px;"
                    f"padding:20px 22px;'>"
                    f"<div style='display:inline-flex;align-items:center;"
                    f"justify-content:center;width:28px;height:28px;background:{pc};"
                    f"border-radius:7px;font-size:11px;font-weight:800;color:#FFFFFF;"
                    f"line-height:1;margin-bottom:10px;'>{num}</div>"
                    f"<p style='font-size:16px;font-weight:700;color:#0F172A;"
                    f"margin:0 0 8px;line-height:1.3;'>{target}</p>"
                    f"<p style='font-size:13px;color:#475569;line-height:1.75;"
                    f"margin:0;'>{benefit}</p>"
                    f"</div>"
                )
                cols.append(
                    _column(50, [_widget("text-editor", {"editor": card_html})])
                )
            if len(cols) == 1:
                cols.append(_column(50, [_spacer(10)]))
            sections.append(
                _section(_sec("#F8FAFC", pt=pt, pr=50, pb=pb, pl=50), cols)
            )

    # ── CTA band ──────────────────────────────────────────────────────────────
    cta_head_html = (
        "<p style='font-size:28px;font-weight:700;color:#FFFFFF;"
        "text-align:center;margin:0 0 10px;line-height:1.35;'>"
        "Siap Melindungi Infrastruktur IT Anda?</p>"
    )
    cta_sub_html = (
        "<p style='font-size:15px;color:rgba(255,255,255,0.82);"
        "text-align:center;margin:0;line-height:1.7;'>"
        "Konsultasikan kebutuhan IT Anda dengan tim ahli iLogo Indonesia</p>"
    )
    cta_btn = _widget("button", {
        "text":                   "Hubungi Kami Sekarang",
        "align":                  "center",
        "background_color":       "#FFFFFF",
        "button_text_color":      pc,
        "border_radius":          {"unit": "px", "top": "8", "right": "8",
                                   "bottom": "8", "left": "8", "isLinked": True},
        "typography_font_size":   {"unit": "px", "size": 15},
        "typography_font_weight": "700",
        "padding":                {"unit": "px", "top": "14", "right": "36",
                                   "bottom": "14", "left": "36", "isLinked": False},
    })
    sections.append(_section(_sec(pc, pt=44, pr=60, pb=52, pl=60), [
        _column(100, [
            _text(cta_head_html, color="#FFFFFF", size_px=28),
            _spacer(8),
            _text(cta_sub_html, color="rgba(255,255,255,0.82)", size_px=15),
            _spacer(22),
            cta_btn,
        ])
    ]))

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
    """
    IMPROVED: Matches the new local preview layout —
      1. Full-width banner hero with gradient overlay + text
      2. Full-width description (white bg)
      3. 2-col feature icon cards (slate-50 bg)
      4. Full-width brand-color "Mengapa?" band
      5. Side-by-side "Untuk Siapa?" + "Cocok Untuk" cards (white bg)
    """
    lite = _lighten(pc, 0.90)
    name = prod.get("name", "Produk")
    tag_ = prod.get("tagline", "")
    desc = prod.get("description", "")
    feats = prod.get("key_features", [])
    ucs   = prod.get("use_cases", [])
    why   = prod.get("why_choose", "")
    tu    = prod.get("target_user", "")
    sections = []

    # Derive a lighter variant of pc for text on dark/brand backgrounds
    r, g, b = _hex_to_rgb(pc)
    pc_light = "#{:02x}{:02x}{:02x}".format(
        min(255, int(r + (255 - r) * 0.55)),
        min(255, int(g + (255 - g) * 0.55)),
        min(255, int(b + (255 - b) * 0.55)),
    )

    # ── 1. Full-width product hero — Elementor native background image ─────────
    if banner_url:
        hero_section_settings = {
            "background_background": "classic",
            "background_image": {
                "url": banner_url,
                "id": "",
                "size": "",
                "alt": name,
                "source": "library",
            },
            "background_size": "cover",
            "background_position": "center center",
            "background_repeat": "no-repeat",
            "background_attachment": "scroll",
            "background_overlay_background": "classic",
            "background_overlay_color": "rgba(15,23,42,0.72)",
            "padding": {
                "unit": "px",
                "top": "80", "right": "60",
                "bottom": "80", "left": "60",
                "isLinked": False,
            },
        }
    else:
        hero_section_settings = _sec("#0F172A", pt=80, pr=60, pb=80, pl=60)

    sections.append(_section(hero_section_settings, [
        _column(100, [
            _text(
                f"<p style='font-size:11px;font-weight:700;color:{pc_light};"
                f"text-transform:uppercase;letter-spacing:2px;margin:0 0 12px;'>"
                f"Produk Unggulan</p>",
                size_px=11
            ),
            _heading(name, tag="h1", align="left",
                     color="#FFFFFF", size_px=38, weight="700"),
            _spacer(10),
            _text(
                f"<p style='font-size:16px;font-weight:500;color:{pc_light};'>"
                f"{tag_}</p>",
                color=pc_light, size_px=16
            ),
        ])
    ]))

    # ── 2. Description — full width, white bg ─────────────────────────────────
    if desc:
        sections.append(_section(_sec("#FFFFFF", pt=32, pr=60, pb=40, pl=60), [
            _column(100, [
                _text(_paras(desc, "#475569", 15, "left"), color="#475569", size_px=15)
            ])
        ]))

    # ── 3. Key Features — 2-col grid of icon cards, slate-50 bg ──────────────
    if feats:
        half        = (len(feats) + 1) // 2
        left_feats  = feats[:half]
        right_feats = feats[half:]

        def _feat_cards(feat_list):
            return "".join(
                f"<div style='display:flex;align-items:flex-start;gap:12px;"
                f"background:#FFFFFF;border:1px solid #E2E8F0;border-radius:10px;"
                f"padding:14px 16px;margin-bottom:10px;'>"
                f"<span style='display:inline-flex;align-items:center;"
                f"justify-content:center;width:26px;height:26px;border-radius:6px;"
                f"background:{lite};flex-shrink:0;margin-top:1px;'>"
                f"<span style='color:{pc};font-weight:700;font-size:13px;'>&#10003;</span>"
                f"</span>"
                f"<span style='color:#374151;line-height:1.7;font-size:13px;'>{feat}</span>"
                f"</div>"
                for feat in feat_list
            )

        label_html = (
            f"<p style='font-size:11px;font-weight:700;color:#64748B;"
            f"text-transform:uppercase;letter-spacing:1.5px;margin:0;'>"
            f"Fitur Utama</p>"
        )
        sections.append(_section(_sec("#F8FAFC", pt=40, pr=60, pb=8, pl=60), [
            _column(100, [_widget("text-editor", {"editor": label_html})])
        ]))
        sections.append(_section(_sec("#F8FAFC", pt=16, pr=60, pb=40, pl=60), [
            _column(50, [_widget("text-editor", {"editor": _feat_cards(left_feats)})]),
            _column(50, [_widget("text-editor", {"editor": _feat_cards(right_feats)})]),
        ]))

    # ── 4. Why Choose — full-width brand-color band ───────────────────────────
    if why:
        why_inner = (
            f"<div style='display:flex;align-items:flex-start;gap:20px;'>"
            f"<div style='width:42px;height:42px;border-radius:10px;"
            f"background:rgba(255,255,255,0.18);display:inline-flex;"
            f"align-items:center;justify-content:center;flex-shrink:0;'>"
            f"<span style='color:#FFFFFF;font-size:20px;line-height:1;'>&#9733;</span>"
            f"</div>"
            f"<div style='flex:1;'>"
            f"<p style='font-size:11px;font-weight:700;color:{pc_light};"
            f"text-transform:uppercase;letter-spacing:1.5px;margin:0 0 10px;'>"
            f"Mengapa {name}?</p>"
            f"<p style='font-size:14px;color:#FFFFFF;line-height:1.8;margin:0 0 22px;'>"
            f"{why}</p>"
            f"<span style='display:inline-block;background:#FFFFFF;color:{pc};"
            f"font-weight:600;font-size:14px;padding:10px 24px;border-radius:8px;'>"
            f"Jadwalkan Demo &rarr;</span>"
            f"</div></div>"
        )
        sections.append(_section(_sec(pc, pt=48, pr=60, pb=48, pl=60), [
            _column(100, [_widget("text-editor", {"editor": why_inner})])
        ]))

    # ── 5. Target User + Use Cases — side-by-side icon header cards ──────────
    if tu or ucs:
        tu_html = ""
        if tu:
            tu_html = (
                f"<div style='background:#FFFFFF;border:1px solid #E2E8F0;"
                f"border-radius:12px;padding:24px 26px;'>"
                f"<div style='display:flex;align-items:center;gap:10px;margin-bottom:12px;'>"
                f"<span style='display:inline-flex;align-items:center;"
                f"justify-content:center;width:28px;height:28px;border-radius:6px;"
                f"background:{lite};flex-shrink:0;'>"
                f"<span style='color:{pc};font-weight:700;font-size:12px;'>U</span>"
                f"</span>"
                f"<p style='font-size:11px;font-weight:700;color:#64748B;"
                f"text-transform:uppercase;letter-spacing:1px;margin:0;'>"
                f"Untuk Siapa?</p>"
                f"</div>"
                f"<p style='font-size:14px;color:#475569;line-height:1.8;margin:0;'>{tu}</p>"
                f"</div>"
            )

        ucs_html = ""
        if ucs:
            uc_rows = "".join(
                f"<div style='display:flex;align-items:flex-start;gap:10px;"
                f"padding:8px 0;border-bottom:1px solid #E2E8F0;'>"
                f"<span style='color:{pc};font-size:13px;flex-shrink:0;margin-top:3px;'>"
                f"&rarr;</span>"
                f"<span style='font-size:13px;color:#374151;line-height:1.6;'>{u}</span>"
                f"</div>"
                for u in ucs
            )
            ucs_html = (
                f"<div style='background:#FFFFFF;border:1px solid #E2E8F0;"
                f"border-radius:12px;padding:24px 26px;'>"
                f"<div style='display:flex;align-items:center;gap:10px;margin-bottom:12px;'>"
                f"<span style='display:inline-flex;align-items:center;"
                f"justify-content:center;width:28px;height:28px;border-radius:6px;"
                f"background:{lite};flex-shrink:0;'>"
                f"<span style='color:{pc};font-weight:700;font-size:12px;'>&#9783;</span>"
                f"</span>"
                f"<p style='font-size:11px;font-weight:700;color:#64748B;"
                f"text-transform:uppercase;letter-spacing:1px;margin:0;'>"
                f"Cocok Untuk</p>"
                f"</div>"
                f"{uc_rows}"
                f"</div>"
            )

        cols = []
        if tu_html:
            cols.append(_column(50, [_widget("text-editor", {"editor": tu_html})]))
        if ucs_html:
            cols.append(_column(50, [_widget("text-editor", {"editor": ucs_html})]))

        if len(cols) == 1:
            cols = [_column(100, cols[0]["elements"])]

        if cols:
            sections.append(_section(_sec("#FFFFFF", pt=40, pr=60, pb=50, pl=60), cols))

    return sections


# ─────────────────────────────────────────────────────────────────────────────
# ── TEMPLATE: CLARITY ────────────────────────────────────────────────────────
# Pure white, very spacious, centered hero with brand band, numbered solutions
# ─────────────────────────────────────────────────────────────────────────────

def _clarity_home(data, banner_url, stock_url, pc):
    lite  = _lighten(pc, 0.90)
    brand = data.get("_brand_name", "Brand").capitalize()
    vps   = data.get("value_propositions", [])
    sections = []

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

    about = data.get("about_summary", "")
    if about:
        sections.append(_section(_sec("#FFFFFF", pt=70, pr=80, pb=60, pl=80), [
            _column(100, [
                _heading(f"Tentang {brand}", tag="h2", align="center",
                         color="#0F172A", size_px=32, weight="800"),
                _spacer(20),
                _text(_paras(about, "#64748B", 15, "left"),
                      color="#64748B", size_px=15),
            ])
        ]))

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
    dark  = _darken(pc, 0.35)
    brand = data.get("_brand_name", "Brand").capitalize()
    vps   = data.get("value_propositions", [])

    sections = []

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

    about = data.get("about_summary", "")
    if about:
        sections.append(_section(_sec("#FFFFFF", pt=70, pr=70, pb=60, pl=70), [
            _column(100, [
                _heading(f"Tentang {brand}", tag="h2", align="center",
                         color="#0F172A", size_px=32, weight="700"),
                _spacer(20),
                _text(_paras(about, "#475569", 15, "left"), color="#475569", size_px=15),
            ])
        ]))

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
    # Footer sekarang dideploy SEKALI secara global via ElementsKit template.
    # Tidak lagi disuntikkan ke setiap halaman secara individual.
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


# ─────────────────────────────────────────────────────────────────────────────
# Global Header & Footer — dideploy SEKALI per brand via ElementsKit template
# ─────────────────────────────────────────────────────────────────────────────

def build_global_header(brand_name: str = "", primary_color: str = "#1E7E34") -> str:
    """
    Mengembalikan Elementor JSON untuk navbar sticky global.
    Panggil sekali, deploy via WordPressClient.create_elementskit_template("header", ...).
    Mengubah header = cukup update satu template ElementsKit, berlaku di seluruh halaman.
    """
    return _to_json(_header_section(brand_name, primary_color))


def build_global_footer(brand_name: str = "") -> str:
    """
    Mengembalikan Elementor JSON untuk footer global 3-kolom.
    Panggil sekali, deploy via WordPressClient.create_elementskit_template("footer", ...).
    Mengubah footer = cukup update satu template ElementsKit, berlaku di seluruh halaman.
    """
    return _to_json(_footer_section(brand_name))