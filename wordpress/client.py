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