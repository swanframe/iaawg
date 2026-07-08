class PageBuilder:
    @staticmethod
    def build_html_content(page_type: str, data: dict, banner_url: str = "", stock_image_url: str = "") -> tuple[str, str, str]:
        # 1. Kunci judul pendek untuk Menu Navigasi WordPress
        short_titles = {
            "home": "Beranda",
            "produk": "Produk",
            "solusi": "Solusi",
            "contact": "Kontak"
        }
        
        # Ini yang dikirim ke WordPress API agar Menu Navigasi di atas jadi pendek & rapi
        title = short_titles.get(page_type, page_type.capitalize())
        
        # Ini mengambil judul panjang asli dari AI untuk ditaruh di dalam isi halaman
        ai_long_title = data.get("title", title)
        footer = data.get("standard_footer", "© 2026 PT. iLogo Infralogy Indonesia. All Rights Reserved.")
        
        html = ""
        excerpt = ""

        # Suntik Banner Utama jika tersedia
        if banner_url:
            html += f"<div class='page-banner' style='margin-bottom:30px;'>"
            html += f"  <img src='{banner_url}' alt='{title} Banner' style='width:100%; max-height:400px; object-fit:cover; border-radius:8px;' />"
            html += f"</div>"

        if page_type == "home":
            html += f"<div class='hero-section' style='padding:40px 20px; background:#f4f4f4; margin-bottom:20px;'>"
            html += f"  <h1 style='font-size:2.5em; margin-bottom:15px;'>{ai_long_title}</h1>"
            html += f"  <h2>{data.get('hero_headline', '')}</h2>"
            html += f"  <p style='font-size:1.2em; color:#555;'>{data.get('hero_subheadline', '')}</p>"
            html += f"</div>"
            if stock_image_url:
                html += f"<div class='featured-image' style='margin:20px 0;'><img src='{stock_image_url}' style='width:100%; max-height:350px; object-fit:cover;' /></div>"
            html += f"<div class='about-section'>"
            html += f"  <h2>Tentang Kami</h2>"
            html += f"  <p>{data.get('about_summary', '')}</p>"
            html += f"</div>"

        elif page_type == "produk":
            # Halaman induk Produk — menampilkan intro dan daftar ringkas semua produk
            intro_title = data.get("intro_page_title", "Produk & Solusi Kami")
            intro_desc  = data.get("intro_page_description", data.get("intro", ""))
            html += f"<h1 style='font-size:2.5em; margin-bottom:15px;'>{intro_title}</h1>"
            html += f"<p class='lead' style='font-size:1.1em; color:#555; margin-bottom:30px;'>{intro_desc}</p>"
            if stock_image_url:
                html += f"<div style='margin:20px 0; text-align:center;'><img src='{stock_image_url}' style='max-width:100%; height:auto;' /></div>"
            html += f"<div class='products-grid' style='margin-top:30px;'>"
            for prod in data.get("products_list", []):
                html += f"  <div class='product-card' style='border:1px solid #ddd; padding:20px; margin-bottom:20px; border-radius:8px;'>"
                html += f"    <h3 style='margin-bottom:8px;'>{prod.get('name', '')}</h3>"
                html += f"    <p style='color:#555; font-style:italic; margin-bottom:10px;'>{prod.get('tagline', '')}</p>"
                html += f"    <p>{prod.get('description', '')[:200]}...</p>"
                html += f"  </div>"
            html += f"</div>"

        elif page_type.startswith("produk_"):
            # Halaman produk individual
            product_name    = data.get("name", ai_long_title)
            product_tagline = data.get("tagline", "")
            product_desc    = data.get("description", "")
            key_features    = data.get("key_features", [])
            target_user     = data.get("target_user", "")

            html += f"<h1 style='font-size:2.5em; margin-bottom:10px;'>{product_name}</h1>"
            if product_tagline:
                html += f"<p style='font-size:1.2em; color:#0073aa; font-weight:600; margin-bottom:20px;'>{product_tagline}</p>"
            if stock_image_url:
                html += f"<div style='margin:20px 0; text-align:center;'><img src='{stock_image_url}' style='max-width:100%; height:auto; border-radius:8px;' /></div>"
            html += f"<div class='product-description' style='margin-top:20px; line-height:1.8;'>"
            # Tampilkan deskripsi (pisahkan per paragraf jika ada newline)
            for para in product_desc.split("\n"):
                para = para.strip()
                if para:
                    html += f"<p style='margin-bottom:15px;'>{para}</p>"
            html += f"</div>"
            if key_features:
                html += f"<div class='key-features' style='margin-top:30px; background:#f4f4f4; padding:20px; border-radius:8px;'>"
                html += f"  <h2 style='margin-bottom:15px;'>Fitur Utama</h2>"
                html += f"  <ul style='list-style:disc; padding-left:20px;'>"
                for feat in key_features:
                    html += f"    <li style='margin-bottom:8px;'>{feat}</li>"
                html += f"  </ul>"
                html += f"</div>"
            if target_user:
                html += f"<div class='target-user' style='margin-top:25px; border-left:4px solid #0073aa; padding-left:15px;'>"
                html += f"  <h3>Cocok Untuk</h3>"
                html += f"  <p>{target_user}</p>"
                html += f"</div>"

        elif page_type == "solusi":
            html += f"<h1 style='font-size:2.5em; margin-bottom:15px;'>{ai_long_title}</h1>"
            html += f"<p class='lead'>{data.get('intro', '')}</p>"
            html += f"<div class='solutions-list' style='margin-top:30px;'>"
            for sol in data.get("solutions_list", []):
                html += f"  <div class='solution-item' style='margin-bottom:20px; padding-left:15px; border-left:4px solid #0073aa;'>"
                html += f"    <h4>{sol.get('target', '')}</h4>"
                html += f"    <p>{sol.get('benefit', '')}</p>"
                html += f"  </div>"
            html += f"</div>"

        elif page_type == "contact":
            html += f"<h1>{ai_long_title}</h1>"
            html += f"<h2>{data.get('headline', '')}</h2>"
            html += f"<p>{data.get('cta_text', '')}</p>"
            html += f"<div class='contact-form-placeholder' style='background:#f9f9f9; border:2px dashed #ccc; padding:30px; text-align:center; margin-top:20px;'>"
            html += f"  <p>[Formulir Kontak Standard Hubungi Kami iLogo]</p>"
            html += f"</div>"

        # Selalu injeksikan standard footer iLogo di bagian paling bawah konten halaman
        html += f"<hr style='margin-top:50px;' />"
        html += f"<footer class='ilogo-standard-footer' style='font-size:0.9em; color:#777; padding:20px 0;'>"
        html += f"  <p>{footer}</p>"
        html += f"</footer>"

        return title, html, excerpt

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
        target_user     = product_data.get("target_user", "")
        footer          = footer_text or "© 2026 PT. iLogo Infralogy Indonesia. All Rights Reserved."

        # Judul navigasi = nama produk (digunakan sebagai judul halaman WordPress)
        nav_title = product_name

        html = ""
        excerpt = product_tagline or (product_desc[:150] + "..." if len(product_desc) > 150 else product_desc)

        # Banner AI
        if banner_url:
            html += f"<div class='page-banner' style='margin-bottom:30px;'>"
            html += f"  <img src='{banner_url}' alt='{product_name} Banner' style='width:100%; max-height:400px; object-fit:cover; border-radius:8px;' />"
            html += f"</div>"

        html += f"<h1 style='font-size:2.5em; margin-bottom:10px;'>{product_name}</h1>"
        if product_tagline:
            html += f"<p style='font-size:1.2em; color:#0073aa; font-weight:600; margin-bottom:20px;'>{product_tagline}</p>"

        if stock_image_url:
            html += f"<div style='margin:20px 0; text-align:center;'>"
            html += f"  <img src='{stock_image_url}' style='max-width:100%; height:auto; border-radius:8px;' />"
            html += f"</div>"

        html += f"<div class='product-description' style='margin-top:20px; line-height:1.8;'>"
        for para in product_desc.split("\n"):
            para = para.strip()
            if para:
                html += f"<p style='margin-bottom:15px;'>{para}</p>"
        html += f"</div>"

        if key_features:
            html += f"<div class='key-features' style='margin-top:30px; background:#f4f4f4; padding:20px; border-radius:8px;'>"
            html += f"  <h2 style='margin-bottom:15px;'>Fitur Utama</h2>"
            html += f"  <ul style='list-style:disc; padding-left:20px;'>"
            for feat in key_features:
                html += f"    <li style='margin-bottom:8px;'>{feat}</li>"
            html += f"  </ul>"
            html += f"</div>"

        if target_user:
            html += f"<div class='target-user' style='margin-top:25px; border-left:4px solid #0073aa; padding-left:15px;'>"
            html += f"  <h3>Cocok Untuk</h3>"
            html += f"  <p>{target_user}</p>"
            html += f"</div>"

        # Footer iLogo
        html += f"<hr style='margin-top:50px;' />"
        html += f"<footer class='ilogo-standard-footer' style='font-size:0.9em; color:#777; padding:20px 0;'>"
        html += f"  <p>{footer}</p>"
        html += f"</footer>"

        return nav_title, html, excerpt