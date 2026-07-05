class PageBuilder:
    @staticmethod
    def build_html_content(page_type: str, data: dict) -> tuple[str, str, str]:
        """
        Mengubah struktur data JSON mentah menjadi markup HTML standar WordPress.
        Mengembalikan tuple: (Title, Content HTML, Excerpt/Slug jika ada)
        """
        title = data.get("title", page_type.capitalize())
        footer = data.get("standard_footer", "© 2026 PT. iLogo Infralogy Indonesia. All Rights Reserved.")
        
        html = ""
        excerpt = ""

        if page_type == "home":
            html += f"<div class='hero-section' style='padding:40px 20px; background:#f4f4f4; margin-bottom:20px;'>"
            html += f"  <h1>{data.get('hero_headline', '')}</h1>"
            html += f"  <p style='font-size:1.2em; color:#555;'>{data.get('hero_subheadline', '')}</p>"
            html += f"</div>"
            html += f"<div class='about-section'>"
            html += f"  <h2>Tentang Kami</h2>"
            html += f"  <p>{data.get('about_summary', '')}</p>"
            html += f"</div>"

        elif page_type == "produk":
            html += f"<p class='lead'>{data.get('intro', '')}</p>"
            html += f"<div class='products-grid' style='margin-top:30px;'>"
            for prod in data.get("products_list", []):
                html += f"  <div class='product-card' style='border:1px solid #ddd; padding:15px; margin-bottom:15px; border-radius:5px;'>"
                html += f"    <h3>{prod.get('name', '')}</h3>"
                html += f"    <p>{prod.get('description', '')}</p>"
                html += f"  </div>"
            html += f"</div>"

        elif page_type == "solusi":
            html += f"<p class='lead'>{data.get('intro', '')}</p>"
            html += f"<div class='solutions-list' style='margin-top:30px;'>"
            for sol in data.get("solutions_list", []):
                html += f"  <div class='solution-item' style='margin-bottom:20px; padding-left:15px; border-left:4px solid #0073aa;'>"
                html += f"    <h4>{sol.get('target', '')}</h4>"
                html += f"    <p>{sol.get('benefit', '')}</p>"
                html += f"  </div>"
            html += f"</div>"

        elif page_type == "contact":
            html += f"<h2>{data.get('headline', '')}</h2>"
            html += f"<p>{data.get('cta_text', '')}</p>"
            html += f"<div class='contact-form-placeholder' style='background:#f9f9f9; border:2px dashed #ccc; padding:30px; text-align:center; margin-top:20px;'>"
            html += f"  <p>[Formulir Kontak Standard Hubungi Kami iLogo]</p>"
            html += f"</div>"

        elif page_type == "blog":
            excerpt = data.get("excerpt", "")
            # Mengubah newline teks artikel blog menjadi tag paragraf HTML agar rapi
            paragraphs = data.get("content", "").split("\n\n")
            for p in paragraphs:
                if p.strip():
                    html += f"<p>{p.strip()}</p>"

        # Selalu injeksikan standard footer iLogo di bagian paling bawah konten halaman
        html += f"<hr style='margin-top:50px;' />"
        html += f"<footer class='ilogo-standard-footer' style='font-size:0.9em; color:#777; padding:20px 0;'>"
        html += f"  <p>{footer}</p>"
        html += f"</footer>"

        return title, html, excerpt