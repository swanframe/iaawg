"""
wordpress/client.py  (iAAWG — Elementor-compatible version)
------------------------------------------------------------
Identical API to the original, with two additions:
  1. create_page() now accepts an optional `elementor_json` parameter.
     When provided, it injects the four Elementor meta fields so the page
     is immediately editable inside Elementor (Free or Pro).
  2. create_elementskit_template() deploys a global header or footer
     via ElementsKit Free (CPT: elementskit_template), applied site-wide.

No other behaviour changes — existing callers with no `elementor_json`
argument continue to work exactly as before (plain HTML fallback).
"""

import base64
import json
import httpx
from config.settings import settings


class WordPressClient:
    def __init__(self, url: str = None, username: str = None, app_password: str = None):
        """
        Inisialisasi klien WordPress.
        Menerima input dinamis dari parameter fungsi atau fallback ke file .env.
        """
        self.base_url    = (url or settings.WP_URL).rstrip('/')
        self.username    = username or settings.WP_USERNAME
        self.app_password = app_password or settings.WP_APPLICATION_PASSWORD

        if not self.base_url or not self.username or not self.app_password:
            raise ValueError(
                "Konfigurasi WordPress REST API (URL, Username, atau "
                "Application Password) belum lengkap!"
            )

        # Basic Auth token dari Application Password
        credential   = f"{self.username}:{self.app_password}"
        encoded_cred = base64.b64encode(credential.encode('utf-8')).decode('utf-8')

        self.headers = {
            "Authorization": f"Basic {encoded_cred}",
            "Content-Type": "application/json"
        }

    # ─────────────────────────────────────────────────────────────────────────
    # Pages
    # ─────────────────────────────────────────────────────────────────────────

    async def create_page(
        self,
        title: str,
        content: str,
        status: str = "publish",
        slug: str = None,
        parent: int = 0,
        elementor_json: str = None          # ← NEW: Elementor JSON string
    ) -> dict:
        """
        Membuat halaman baru (Page) di WordPress menggunakan REST API v2.

        Jika `elementor_json` diberikan (string JSON dari elementor_builder),
        halaman akan disimpan dengan meta Elementor yang lengkap sehingga
        langsung dapat diedit di Elementor editor tanpa konfigurasi tambahan.

        Jika tidak diberikan, konten HTML biasa akan dikirim seperti sebelumnya
        (backward-compatible fallback).

        Parameter `parent` opsional untuk membuat child page.
        """
        url = f"{self.base_url}/wp-json/wp/v2/pages"

        payload = {
            "title":   title,
            "content": content,   # Plain HTML fallback (Elementor overrides this)
            "status":  status
        }
        if slug:
            payload["slug"] = slug
        if parent:
            payload["parent"] = parent

        # ── Inject Elementor meta when JSON is provided ───────────────────────
        if elementor_json:
            payload["meta"] = {
                # Core Elementor fields
                "_elementor_data":          elementor_json,   # must stay a string
                "_elementor_edit_mode":     "builder",
                "_elementor_template_type": "wp-page",
                "_elementor_version":       "3.21.0",
                # Page settings — must be a dict (object), NOT json.dumps()
                # CHANGED: "default" allows ElementsKit to inject its global
                # header/footer. "elementor_canvas" would bypass all hooks.
                "_elementor_page_settings": {
                    "hide_title":  "yes",
                    "page_layout": "default"
                }
            }

        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.post(url, json=payload, headers=self.headers)
                if response.status_code in [200, 201]:
                    result = response.json()
                    mode = "Elementor" if elementor_json else "HTML"
                    print(f"[WordPress] Berhasil deploy halaman ({mode}): '{title}'")
                    return result
                else:
                    print(
                        f"[WordPress Error] Gagal deploy '{title}': "
                        f"{response.status_code} - {response.text}"
                    )
                    return {}
            except Exception as e:
                print(f"[WordPress Error] Kendala jaringan saat mengakses REST API: {e}")
                return {}

    # ─────────────────────────────────────────────────────────────────────────
    # Reading Settings (Front Page)
    # ─────────────────────────────────────────────────────────────────────────

    async def set_reading_settings(self, page_id: int) -> bool:
        """
        Sets the WordPress front page to a static page instead of the
        blog archive (latest posts).

        Calls: POST /wp-json/wp/v2/settings
          show_on_front : "page"  → static page mode (not "posts")
          page_on_front : <id>    → the Page to use as the homepage

        Returns True on success, False otherwise.
        """
        url = f"{self.base_url}/wp-json/wp/v2/settings"
        payload = {
            "show_on_front": "page",
            "page_on_front": page_id,
        }

        async with httpx.AsyncClient(timeout=15.0) as client:
            try:
                response = await client.post(url, json=payload, headers=self.headers)
                if response.status_code == 200:
                    print(f"[WordPress] ✓ Front page set to Page ID {page_id}")
                    return True
                else:
                    print(
                        f"[WordPress Error] Gagal set front page: "
                        f"{response.status_code} — {response.text[:300]}"
                    )
                    return False
            except Exception as e:
                print(f"[WordPress Error] Kendala jaringan set_reading_settings: {e}")
                return False

    # ─────────────────────────────────────────────────────────────────────────
    # Posts (blog — unchanged from original)
    # ─────────────────────────────────────────────────────────────────────────

    async def create_post(
        self,
        title: str,
        content: str,
        excerpt: str = "",
        status: str = "publish"
    ) -> dict:
        """Membuat artikel blog baru (Post) di WordPress untuk tipe data Blog."""
        url = f"{self.base_url}/wp-json/wp/v2/posts"
        payload = {
            "title":   title,
            "content": content,
            "excerpt": excerpt,
            "status":  status
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.post(url, json=payload, headers=self.headers)
                if response.status_code in [200, 201]:
                    print(f"[WordPress] Berhasil deploy postingan blog: '{title}'")
                    return response.json()
                else:
                    print(
                        f"[WordPress Error] Gagal deploy blog '{title}': "
                        f"{response.status_code} - {response.text}"
                    )
                    return {}
            except Exception as e:
                print(f"[WordPress Error] Kendala jaringan saat mengakses REST API: {e}")
                return {}

    # ─────────────────────────────────────────────────────────────────────────
    # ElementsKit Global Header / Footer
    # ─────────────────────────────────────────────────────────────────────────

    async def create_elementskit_template(
        self,
        hf_type: str,           # "header"  or  "footer"
        title: str,
        elementor_json: str,
    ) -> dict:
        """
        Mendeploy header atau footer global via ElementsKit Free.

        ElementsKit menyimpan template H/F sebagai custom post type
        `elementskit_template`. Plugin membaca meta berikut untuk menentukan
        apa yang akan dirender dan di mana:

          _elementskit_template_type  →  "header" | "footer"
          _elementskit_conditions     →  JSON array kondisi tampil
          _elementor_data             →  Elementor section JSON (format
                                         sama dengan halaman biasa)
          _elementor_edit_mode        →  "builder"
          _elementor_template_type    →  "page"

        Kondisi "general" berarti template tampil di seluruh situs.

        Syarat: Plugin ElementsKit Elementor Addons (free) sudah terinstall
        dan aktif di WordPress target.
        """
        url = f"{self.base_url}/wp-json/wp/v2/elementskit_template"

        # Kondisi tampil: aktif di seluruh situs
        conditions = json.dumps([
            {"id": "general", "rule": "show", "isSelected": True}
        ])

        payload = {
            "title":  title,
            "status": "publish",
            "meta": {
                "_elementor_data":            elementor_json,
                "_elementor_edit_mode":       "builder",
                "_elementor_template_type":   "page",
                "_elementskit_template_type": hf_type,    # "header" atau "footer"
                "_elementskit_conditions":    conditions,
            },
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.post(
                    url, json=payload, headers=self.headers
                )
                if response.status_code in [200, 201]:
                    result = response.json()
                    print(
                        f"[ElementsKit] ✓ Global {hf_type} berhasil dideploy: "
                        f"'{title}'  (ID: {result.get('id')})"
                    )
                    return result
                else:
                    print(
                        f"[ElementsKit Error] Gagal deploy {hf_type}: "
                        f"{response.status_code} — {response.text[:400]}"
                    )
                    return {}
            except Exception as exc:
                print(f"[ElementsKit Error] Kendala jaringan: {exc}")
                return {}

    # ─────────────────────────────────────────────────────────────────────────
    # Navigation Menus
    # ─────────────────────────────────────────────────────────────────────────

    async def create_nav_menu(self, name: str, slug: str) -> tuple:
        """
        Membuat WordPress Navigation Menu baru, atau menemukan yang sudah ada.

        Mengembalikan (menu_id, actual_slug). Jika menu dengan nama yang sama
        sudah ada (dari run sebelumnya), fungsi ini mengambil data menu yang
        ada dan mengembalikan slug-nya yang sebenarnya — sehingga pipeline
        dapat dijalankan berulang kali tanpa error.
        """
        url = f"{self.base_url}/wp-json/wp/v2/menus"
        payload = {"name": name, "slug": slug}

        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.post(url, json=payload, headers=self.headers)

                if response.status_code in [200, 201]:
                    result      = response.json()
                    menu_id     = result.get("id", 0)
                    actual_slug = result.get("slug", slug)
                    print(f"[WordPress] Nav menu dibuat: '{name}' (ID: {menu_id}, slug: {actual_slug})")
                    return menu_id, actual_slug

                elif response.status_code == 400:
                    data = response.json()
                    if data.get("code") == "menu_exists":
                        # Menu sudah ada — ambil term_id dari respons error,
                        # lalu GET menu tersebut untuk mendapatkan slug yang sebenarnya
                        existing_id = (data.get("data") or {}).get("term_id", 0)
                        if existing_id:
                            get_resp = await client.get(
                                f"{self.base_url}/wp-json/wp/v2/menus/{existing_id}",
                                headers=self.headers,
                            )
                            if get_resp.status_code == 200:
                                existing    = get_resp.json()
                                actual_slug = existing.get("slug", slug)
                                print(
                                    f"[WordPress] Nav menu sudah ada, digunakan kembali: "
                                    f"'{name}' (ID: {existing_id}, slug: {actual_slug})"
                                )
                                return existing_id, actual_slug

                print(
                    f"[WordPress Error] Gagal membuat nav menu: "
                    f"{response.status_code} -- {response.text[:300]}"
                )
                return 0, ""

            except Exception as e:
                print(f"[WordPress Error] Kendala jaringan saat membuat nav menu: {e}")
                return 0, ""

    async def _clear_menu_items(self, menu_id: int) -> None:
        """
        Menghapus semua item yang ada di dalam sebuah menu.
        Dipanggil sebelum create_menu_items() agar tidak menumpuk pada re-run.
        """
        list_url = f"{self.base_url}/wp-json/wp/v2/menu-items"
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                resp = await client.get(
                    list_url,
                    params={"menus": menu_id, "per_page": 100},
                    headers=self.headers,
                )
                if resp.status_code != 200:
                    return
                for item in resp.json():
                    item_id = item.get("id")
                    if item_id:
                        await client.delete(
                            f"{self.base_url}/wp-json/wp/v2/menu-items/{item_id}",
                            params={"force": True},
                            headers=self.headers,
                        )
                print(f"[WordPress] Item menu lama dihapus (menu ID: {menu_id})")
            except Exception as e:
                print(f"[WordPress] Gagal menghapus item menu lama: {e}")

    async def create_menu_items(
        self, menu_id: int, page_links: dict, product_links: list
    ) -> None:
        """
        Mengisi nav menu dengan URL canonical aktual dari respons WordPress.

        Parameter:
          menu_id       : ID menu dari create_nav_menu()
          page_links    : dict URL aktual per halaman, diambil dari field "link"
                          respons create_page() — bukan konstruksi slug manual.
                          Format: {"home": "http://...", "solusi": "http://...",
                                   "produk": "http://...", "contact": "http://..."}
          product_links : list dict {"name": ..., "link": ...} untuk setiap produk
        """
        # Hapus item lama sebelum mengisi ulang (aman untuk re-run)
        await self._clear_menu_items(menu_id)

        url = f"{self.base_url}/wp-json/wp/v2/menu-items"

        top_level = [
            {"title": "Beranda", "href": page_links.get("home",    ""), "order": 1},
            {"title": "Solusi",  "href": page_links.get("solusi",  ""), "order": 2},
            {"title": "Produk",  "href": page_links.get("produk",  ""), "order": 3},
            {"title": "Kontak",  "href": page_links.get("contact", ""), "order": 4},
        ]

        produk_item_id = 0

        async with httpx.AsyncClient(timeout=30.0) as client:
            # Top-level items
            for item in top_level:
                payload = {
                    "title":      item["title"],
                    "url":        item["href"],
                    "status":     "publish",
                    "menus":      menu_id,
                    "menu_order": item["order"],
                    "parent":     0,
                    "type":       "custom",
                    "type_label": "Custom Link",
                }
                try:
                    response = await client.post(url, json=payload, headers=self.headers)
                    if response.status_code in [200, 201]:
                        result = response.json()
                        if item["title"] == "Produk":
                            produk_item_id = result.get("id", 0)
                        print(f"[WordPress] Menu item: '{item['title']}' -> {item['href']}")
                    else:
                        print(
                            f"[WordPress Error] Gagal membuat menu item '{item['title']}': "
                            f"{response.status_code}"
                        )
                except Exception as e:
                    print(f"[WordPress Error] Kendala jaringan menu item: {e}")

            # Child product items (nested under Produk)
            if produk_item_id and product_links:
                for order, prod in enumerate(product_links, start=1):
                    payload = {
                        "title":      prod.get("name", f"Produk {order}"),
                        "url":        prod.get("link", ""),
                        "status":     "publish",
                        "menus":      menu_id,
                        "menu_order": order,
                        "parent":     produk_item_id,
                        "type":       "custom",
                        "type_label": "Custom Link",
                    }
                    try:
                        response = await client.post(url, json=payload, headers=self.headers)
                        if response.status_code in [200, 201]:
                            print(f"[WordPress]   L-- Child item: '{prod.get('name')}'")
                        else:
                            print(
                                f"[WordPress Error] Gagal membuat child item "
                                f"'{prod.get('name')}': {response.status_code}"
                            )
                    except Exception as e:
                        print(f"[WordPress Error] Kendala jaringan child item: {e}")

    # ─────────────────────────────────────────────────────────────────────────
    # Contact Form 7
    # ─────────────────────────────────────────────────────────────────────────

    async def create_cf7_form(self, brand_name: str) -> str:
        """
        Mengembalikan ID Contact Form 7 untuk digunakan di shortcode halaman kontak.
        Strategi 3 langkah agar handal di semua versi CF7:

          1. GET  — Ambil daftar form yang ada. Prioritas: form berjudul
                    'Hubungi Kami'. Jika tidak ada, gunakan form pertama yang
                    ditemukan (CF7 selalu menginstall 'Formulir kontak 1' secara
                    default — form ini langsung bisa digunakan).
          2. POST — Buat form baru hanya jika daftar benar-benar kosong.
          3. GET  — Jika POST berhasil tapi ID-nya null (quirk beberapa versi CF7),
                    lakukan GET ulang untuk mengambil ID form yang baru dibuat.

        Mengembalikan ID sebagai string, atau "" jika semua langkah gagal.
        CF7 menyimpan ID sebagai hash string (mis. 'd66ef7b') di versi baru,
        atau integer di versi lama — keduanya ditangani dengan str(raw_id).
        """
        TARGET_TITLE = "Hubungi Kami"
        base_url     = f"{self.base_url}/wp-json/contact-form-7/v1/contact-forms"

        def _extract_id_from_list(resp_json) -> tuple[str, str]:
            """
            Kembalikan (form_id, form_title) dari respons GET list CF7.
            Prioritas: form berjudul TARGET_TITLE.
            Fallback: form pertama yang ditemukan (mis. 'Formulir kontak 1').
            CF7 GET /contact-forms → {"count": N, "items": [...]}
            """
            items = (resp_json.get("items", [])
                     if isinstance(resp_json, dict) else resp_json)
            if not isinstance(items, list):
                return "", ""

            first_id, first_title = "", ""
            for form in items:
                raw = form.get("id")
                if raw is None:
                    continue
                fid   = str(raw)
                title = form.get("title", "").strip()
                # Simpan form pertama sebagai fallback
                if not first_id:
                    first_id, first_title = fid, title
                # Prioritas utama: judul tepat "Hubungi Kami"
                if title == TARGET_TITLE:
                    return fid, title

            return first_id, first_title   # fallback ke form pertama

        form_body = (
            '<label>Nama Lengkap (required)\n'
            '    [text* full-name placeholder "Nama Lengkap Anda"] </label>\n\n'
            '<label>Email Perusahaan (required)\n'
            '    [email* your-email placeholder "email@perusahaan.com"] </label>\n\n'
            '<label>Nama Perusahaan\n'
            '    [text company-name placeholder "PT. Nama Perusahaan Anda"] </label>\n\n'
            '<label>Pesan / Kebutuhan IT\n'
            '    [textarea your-message placeholder "Ceritakan kebutuhan IT Anda..."] </label>\n\n'
            '[submit "Kirim Pesan"]'
        )

        recipient = f"{brand_name.lower()}@ilogoindonesia.com"
        payload = {
            "title":  TARGET_TITLE,
            "locale": "id_ID",
            "form":   form_body,
            "mail": {
                "active":             True,
                "recipient":          recipient,
                "sender":             f"Website {brand_name.capitalize()} <{recipient}>",
                "subject":            f"[{brand_name.capitalize()}] Permintaan Konsultasi Baru dari [full-name]",
                "body": (
                    "Nama       : [full-name]\n"
                    "Email      : [your-email]\n"
                    "Perusahaan : [company-name]\n\n"
                    "Pesan:\n[your-message]\n\n"
                    "---\nDikirim via formulir kontak website iLogo."
                ),
                "use_html":           False,
                "attachments":        "",
                "exclude_blank":      False,
                "reply_to":           "[your-email]",
                "additional_headers": "",
            },
        }

        async with httpx.AsyncClient(timeout=20.0) as client:

            # ── Step 1: GET — gunakan form yang sudah ada ────────────────────
            try:
                r = await client.get(base_url, headers=self.headers)
                if r.status_code == 200:
                    fid, found_title = _extract_id_from_list(r.json())
                    if fid:
                        print(f"[WordPress] CF7 form ditemukan — '{found_title}' (ID: {fid})")
                        return fid
                    # Jika fid kosong, daftar kosong → lanjut ke POST
            except Exception as e:
                print(f"[WordPress Warning] Gagal GET daftar CF7 form: {e}")

            # ── Step 2: POST — buat form baru (hanya jika daftar kosong) ─────
            try:
                r = await client.post(base_url, json=payload, headers=self.headers)
                if r.status_code in [200, 201]:
                    # Ambil ID dari response — .get() mengembalikan None (bukan "")
                    # jika key ada tapi nilainya null; tangani secara eksplisit.
                    raw_id = r.json().get("id")
                    if raw_id is not None:
                        print(f"[WordPress] CF7 form dibuat — ID: {raw_id}")
                        return str(raw_id)

                    # ── Step 3: GET ulang — form mungkin dibuat tapi ID null ─
                    print("[WordPress] CF7 POST berhasil tapi ID null, mencoba GET ulang...")
                    r2 = await client.get(base_url, headers=self.headers)
                    if r2.status_code == 200:
                        fid, found_title = _extract_id_from_list(r2.json())
                        if fid:
                            print(f"[WordPress] CF7 form ID ditemukan via GET ulang — '{found_title}' (ID: {fid})")
                            return fid

                    print(
                        "[WordPress Warning] CF7 form tidak dapat dibuat secara otomatis.\n"
                        "    Solusi: Buka CF7 Admin → Tambah Baru → beri judul 'Hubungi Kami'\n"
                        "    → Simpan. Pipeline berikutnya akan otomatis menemukan form ini."
                    )
                    return ""
                else:
                    print(
                        f"[WordPress Warning] Gagal membuat CF7 form: "
                        f"{r.status_code} - {r.text[:300]}\n"
                        "    Solusi: Buka CF7 Admin → Tambah Baru → beri judul 'Hubungi Kami'."
                    )
                    return ""
            except Exception as e:
                print(
                    f"[WordPress Warning] Kendala jaringan saat membuat CF7 form: {e}\n"
                    "    Solusi: Buka CF7 Admin → Tambah Baru → beri judul 'Hubungi Kami'."
                )
                return ""

    # ─────────────────────────────────────────────────────────────────────────
    # Media (unchanged from original)
    # ─────────────────────────────────────────────────────────────────────────

    async def upload_media(
        self,
        file_name: str,
        file_content: bytes,
        mime_type: str = "image/jpeg"
    ) -> str:
        """Mengunggah file biner gambar ke WordPress Media Library via REST API."""
        if not file_content:
            return ""

        url = f"{self.base_url}/wp-json/wp/v2/media"
        headers = {
            "Authorization":       self.headers["Authorization"],
            "Content-Disposition": f'attachment; filename="{file_name}"',
            "Content-Type":        mime_type
        }

        async with httpx.AsyncClient(timeout=40.0) as client:
            try:
                response = await client.post(url, content=file_content, headers=headers)
                if response.status_code in [200, 201]:
                    media_data = response.json()
                    source_url = media_data.get("source_url", "")
                    print(f"[WordPress] Berhasil mengunggah media: '{file_name}' -> {source_url}")
                    return source_url
                else:
                    print(
                        f"[WordPress Error] Gagal unggah media '{file_name}': "
                        f"{response.status_code} - {response.text}"
                    )
                    return ""
            except Exception as e:
                print(f"[WordPress Error] Kendala jaringan saat unggah media: {e}")
                return ""