class PageBuilder:
    @staticmethod
    def build_html_content(page_type: str, data: dict, banner_url: str = "", stock_image_url: str = "") -> tuple[str, str, str]:
        # Judul pendek untuk Menu Navigasi WordPress
        short_titles = {
            "home":    "Beranda",
            "produk":  "Produk",
            "solusi":  "Solusi",
            "contact": "Kontak"
        }
        title        = short_titles.get(page_type, page_type.capitalize())
        ai_long_title = data.get("title", title)
        footer       = data.get("standard_footer", "© 2026 PT. iLogo Infralogy Indonesia. All Rights Reserved.")

        html    = ""
        excerpt = ""

        # --- Banner AI ---
        if banner_url:
            html += (
                f"<div class='page-banner' style='margin-bottom:30px;'>"
                f"  <img src='{banner_url}' alt='{title} Banner'"
                f"       style='width:100%; max-height:400px; object-fit:cover; border-radius:8px;' />"
                f"</div>"
            )

        # =====================================================================
        # HOME
        # =====================================================================
        if page_type == "home":
            hero_headline    = data.get("hero_headline", "")
            hero_subheadline = data.get("hero_subheadline", "")
            cta_button_text  = data.get("cta_button_text", "Hubungi Kami")
            about_summary    = data.get("about_summary", "")
            value_props      = data.get("value_propositions", [])
            closing          = data.get("closing_statement", "")

            # Hero Section
            html += (
                "<div class='hero-section' style='"
                "padding:50px 30px; background:linear-gradient(135deg,#0d1b2a 0%,#1b3a5c 100%);"
                "color:#fff; text-align:center; margin-bottom:40px; border-radius:8px;'>"
                f"  <h1 style='font-size:2.6em; margin-bottom:16px; line-height:1.25;'>{hero_headline}</h1>"
                f"  <p style='font-size:1.2em; color:#cce0f5; max-width:700px; margin:0 auto 28px;'>{hero_subheadline}</p>"
                f"  <a href='#contact' style='"
                f"     display:inline-block; background:#1E7E34; color:#fff; padding:14px 32px;"
                f"     border-radius:6px; font-weight:700; font-size:1em; text-decoration:none;'>"
                f"    {cta_button_text}"
                f"  </a>"
                "</div>"
            )

            # Stock Photo
            if stock_image_url:
                html += (
                    "<div class='featured-image' style='margin:30px 0;'>"
                    f"  <img src='{stock_image_url}'"
                    "       style='width:100%; max-height:380px; object-fit:cover; border-radius:8px;' />"
                    "</div>"
                )

            # About Section — render setiap paragraf terpisah
            if about_summary:
                html += (
                    "<div class='about-section' style='margin:40px 0; padding:30px;"
                    "background:#f9f9f9; border-radius:8px;'>"
                    f"  <h2 style='margin-bottom:20px; color:#1a1a2e;'>Tentang {ai_long_title}</h2>"
                )
                for para in about_summary.split("\n"):
                    para = para.strip()
                    if para:
                        html += f"<p style='line-height:1.8; color:#444; margin-bottom:14px;'>{para}</p>"
                html += "</div>"

            # Value Propositions — grid card
            if value_props:
                html += (
                    "<div class='value-props' style='margin:40px 0;'>"
                    "<h2 style='text-align:center; margin-bottom:30px; color:#1a1a2e;'>Mengapa Memilih Kami?</h2>"
                    "<div style='display:grid; grid-template-columns:repeat(auto-fit,minmax(240px,1fr)); gap:24px;'>"
                )
                for vp in value_props:
                    icon_label  = vp.get("icon_label", "")
                    vp_title    = vp.get("title", "")
                    vp_desc     = vp.get("description", "")
                    html += (
                        "<div style='background:#fff; border:1px solid #e2e8f0; border-radius:8px;"
                        "padding:24px; box-shadow:0 2px 6px rgba(0,0,0,.06);'>"
                        f"  <p style='font-size:0.75em; font-weight:700; color:#1E7E34;"
                        f"     text-transform:uppercase; letter-spacing:.08em; margin-bottom:8px;'>{icon_label}</p>"
                        f"  <h3 style='font-size:1.1em; color:#1a1a2e; margin-bottom:10px;'>{vp_title}</h3>"
                        f"  <p style='color:#555; line-height:1.7; font-size:0.95em;'>{vp_desc}</p>"
                        "</div>"
                    )
                html += "</div></div>"

            # Closing Statement
            if closing:
                html += (
                    "<div class='closing-section' style='"
                    "margin:40px 0; padding:30px; background:#1E7E34; color:#fff;"
                    "border-radius:8px; text-align:center;'>"
                    f"  <p style='font-size:1.15em; line-height:1.7; margin:0;'>{closing}</p>"
                    "</div>"
                )

        # =====================================================================
        # PRODUK (Halaman Induk)
        # =====================================================================
        elif page_type == "produk":
            intro_title = data.get("intro_page_title", "Produk & Solusi Kami")
            intro_desc  = data.get("intro_page_description", data.get("intro", ""))
            products    = data.get("products_list", [])

            html += (
                f"<h1 style='font-size:2.5em; margin-bottom:15px; color:#1a1a2e;'>{intro_title}</h1>"
                f"<p style='font-size:1.1em; color:#555; margin-bottom:30px; line-height:1.7;'>{intro_desc}</p>"
            )
            if stock_image_url:
                html += (
                    "<div style='margin:20px 0;'>"
                    f"  <img src='{stock_image_url}' style='width:100%; max-height:320px; object-fit:cover; border-radius:8px;' />"
                    "</div>"
                )

            if products:
                html += "<div class='products-grid' style='margin-top:40px;'>"
                for prod in products:
                    prod_name    = prod.get("name", "")
                    prod_slug    = prod.get("slug", "")
                    prod_tagline = prod.get("tagline", "")
                    prod_desc    = prod.get("description", "")
                    key_features = prod.get("key_features", [])
                    use_cases    = prod.get("use_cases", [])

                    # Ringkasan deskripsi: ambil paragraf pertama saja untuk kartu induk
                    first_para = ""
                    for p in prod_desc.split("\n"):
                        p = p.strip()
                        if p:
                            first_para = p
                            break

                    html += (
                        "<div class='product-card' style='"
                        "border:1px solid #dde3ea; padding:28px; margin-bottom:28px;"
                        "border-radius:10px; background:#fff; box-shadow:0 2px 8px rgba(0,0,0,.05);'>"
                        f"  <h3 style='font-size:1.4em; color:#1a1a2e; margin-bottom:8px;'>{prod_name}</h3>"
                        f"  <p style='color:#1E7E34; font-weight:600; font-style:italic; margin-bottom:14px;'>{prod_tagline}</p>"
                        f"  <p style='color:#444; line-height:1.75; margin-bottom:16px;'>{first_para}</p>"
                    )

                    # Fitur ringkas (maks 3 item di halaman induk)
                    if key_features:
                        html += "<ul style='list-style:none; padding:0; margin-bottom:16px;'>"
                        for feat in key_features[:3]:
                            html += (
                                f"<li style='padding:5px 0; color:#555; font-size:0.92em;'>"
                                f"&#10003;&nbsp; {feat}</li>"
                            )
                        html += "</ul>"

                    # Use Cases ringkas
                    if use_cases:
                        html += (
                            "<p style='font-size:0.82em; font-weight:700; color:#1E7E34;"
                            "text-transform:uppercase; letter-spacing:.06em; margin-bottom:6px;'>Digunakan Untuk:</p>"
                            "<ul style='list-style:disc; padding-left:18px; margin-bottom:0;'>"
                        )
                        for uc in use_cases:
                            html += f"<li style='color:#555; font-size:0.92em; margin-bottom:4px;'>{uc}</li>"
                        html += "</ul>"

                    html += "</div>"
                html += "</div>"

        # =====================================================================
        # SOLUSI
        # =====================================================================
        elif page_type == "solusi":
            html += (
                f"<h1 style='font-size:2.5em; margin-bottom:15px; color:#1a1a2e;'>{ai_long_title}</h1>"
                f"<p style='font-size:1.1em; color:#555; line-height:1.7;'>{data.get('intro', '')}</p>"
            )
            if stock_image_url:
                html += (
                    "<div style='margin:24px 0;'>"
                    f"  <img src='{stock_image_url}' style='width:100%; max-height:320px; object-fit:cover; border-radius:8px;' />"
                    "</div>"
                )
            html += "<div class='solutions-list' style='margin-top:30px;'>"
            for sol in data.get("solutions_list", []):
                html += (
                    "<div style='margin-bottom:22px; padding:20px 20px 20px 24px;"
                    "border-left:4px solid #1E7E34; background:#f9f9f9; border-radius:0 8px 8px 0;'>"
                    f"  <h4 style='margin-bottom:8px; color:#1a1a2e;'>{sol.get('target', '')}</h4>"
                    f"  <p style='color:#555; line-height:1.75; margin:0;'>{sol.get('benefit', '')}</p>"
                    "</div>"
                )
            html += "</div>"

        # =====================================================================
        # CONTACT
        # =====================================================================
        elif page_type == "contact":
            html += (
                f"<h1 style='font-size:2.5em; margin-bottom:16px; color:#1a1a2e;'>{ai_long_title}</h1>"
                f"<h2 style='color:#1E7E34; margin-bottom:20px;'>{data.get('headline', '')}</h2>"
                f"<p style='font-size:1.05em; line-height:1.8; color:#444;'>{data.get('cta_text', '')}</p>"
                "<div style='background:#f9f9f9; border:2px dashed #ccc; padding:30px;"
                "text-align:center; margin-top:24px; border-radius:8px;'>"
                "  <p style='color:#888;'>[Formulir Kontak Standard Hubungi Kami iLogo]</p>"
                "</div>"
            )

        # --- Standard Footer ---
        html += (
            "<hr style='margin-top:50px; border:none; border-top:1px solid #e2e8f0;' />"
            "<footer class='ilogo-standard-footer' style='font-size:0.88em; color:#777; padding:20px 0;'>"
            f"  <p>{footer}</p>"
            "</footer>"
        )

        return title, html, excerpt

    # =========================================================================
    # Halaman Produk Individual
    # =========================================================================
    @staticmethod
    def build_product_page_html(product_data: dict, banner_url: str = "", stock_image_url: str = "", footer_text: str = "") -> tuple[str, str, str]:
        """
        Membangun HTML untuk satu halaman produk individual.
        Mengembalikan (nav_title, html_content, excerpt).
        """
        product_name    = product_data.get("name", "Produk")
        product_tagline = product_data.get("tagline", "")
        product_desc    = product_data.get("description", "")
        key_features    = product_data.get("key_features", [])
        use_cases       = product_data.get("use_cases", [])
        why_choose      = product_data.get("why_choose", "")
        target_user     = product_data.get("target_user", "")
        footer          = footer_text or "© 2026 PT. iLogo Infralogy Indonesia. All Rights Reserved."

        nav_title = product_name
        excerpt   = product_tagline or (product_desc[:150] + "..." if len(product_desc) > 150 else product_desc)
        html      = ""

        # Banner AI
        if banner_url:
            html += (
                "<div class='page-banner' style='margin-bottom:30px;'>"
                f"  <img src='{banner_url}' alt='{product_name} Banner'"
                "       style='width:100%; max-height:400px; object-fit:cover; border-radius:8px;' />"
                "</div>"
            )

        # Judul & Tagline
        html += f"<h1 style='font-size:2.5em; margin-bottom:10px; color:#1a1a2e;'>{product_name}</h1>"
        if product_tagline:
            html += (
                f"<p style='font-size:1.2em; color:#1E7E34; font-weight:700; margin-bottom:24px;'>{product_tagline}</p>"
            )

        # Stock Photo
        if stock_image_url:
            html += (
                "<div style='margin:20px 0;'>"
                f"  <img src='{stock_image_url}' style='width:100%; max-height:380px; object-fit:cover; border-radius:8px;' />"
                "</div>"
            )

        # Deskripsi — render per paragraf
        if product_desc:
            html += "<div class='product-description' style='margin-top:28px; line-height:1.85;'>"
            for para in product_desc.split("\n"):
                para = para.strip()
                if para:
                    html += f"<p style='margin-bottom:16px; color:#333;'>{para}</p>"
            html += "</div>"

        # Fitur Utama
        if key_features:
            html += (
                "<div class='key-features' style='"
                "margin-top:32px; background:#f4f8fc; padding:24px 28px; border-radius:8px;'>"
                "<h2 style='margin-bottom:18px; color:#1a1a2e;'>Fitur Utama</h2>"
                "<ul style='list-style:none; padding:0; margin:0;'>"
            )
            for feat in key_features:
                html += (
                    "<li style='display:flex; align-items:flex-start; gap:10px; margin-bottom:12px;'>"
                    "  <span style='color:#1E7E34; font-weight:700; flex-shrink:0; margin-top:2px;'>&#10003;</span>"
                    f"  <span style='color:#333; line-height:1.7;'>{feat}</span>"
                    "</li>"
                )
            html += "</ul></div>"

        # Use Cases
        if use_cases:
            html += (
                "<div class='use-cases' style='margin-top:28px;'>"
                "<h2 style='margin-bottom:16px; color:#1a1a2e;'>Cocok Digunakan Untuk</h2>"
                "<div style='display:grid; grid-template-columns:repeat(auto-fit,minmax(220px,1fr)); gap:16px;'>"
            )
            for uc in use_cases:
                html += (
                    "<div style='background:#fff; border:1px solid #dde3ea; border-radius:8px;"
                    "padding:18px 20px; box-shadow:0 1px 4px rgba(0,0,0,.05);'>"
                    f"  <p style='margin:0; color:#333; line-height:1.7; font-size:0.95em;'>{uc}</p>"
                    "</div>"
                )
            html += "</div></div>"

        # Mengapa Memilih Produk Ini
        if why_choose:
            html += (
                "<div class='why-choose' style='"
                "margin-top:32px; padding:24px 28px; background:#1E7E34; color:#fff; border-radius:8px;'>"
                "<h2 style='color:#fff; margin-bottom:14px;'>Mengapa Memilih Produk Ini?</h2>"
            )
            for para in why_choose.split("\n"):
                para = para.strip()
                if para:
                    html += f"<p style='line-height:1.8; margin-bottom:12px; color:#e8f4fd;'>{para}</p>"
            html += "</div>"

        # Target User
        if target_user:
            html += (
                "<div class='target-user' style='"
                "margin-top:28px; border-left:4px solid #1E7E34; padding:16px 20px;"
                "background:#f9f9f9; border-radius:0 8px 8px 0;'>"
                "<h3 style='margin-bottom:8px; color:#1a1a2e;'>Untuk Siapa?</h3>"
                f"<p style='color:#555; line-height:1.75; margin:0;'>{target_user}</p>"
                "</div>"
            )

        # Footer iLogo
        html += (
            "<hr style='margin-top:50px; border:none; border-top:1px solid #e2e8f0;' />"
            "<footer class='ilogo-standard-footer' style='font-size:0.88em; color:#777; padding:20px 0;'>"
            f"  <p>{footer}</p>"
            "</footer>"
        )

        return nav_title, html, excerpt