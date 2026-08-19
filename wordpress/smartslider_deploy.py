"""
wordpress/smartslider_deploy.py
--------------------------------
Otomatisasi deploy Smart Slider 3 untuk iAAWG.

Alur:
  1. Baca template .ss3 (ZIP arsip: `data` PHP-serialized + folder `images/`).
  2. Overwrite file gambar di folder `images/` dengan banner iAAWG per brand.
     Nama file DIPERTAHANKAN — jangan diubah, karena `data` PHP-serialized
     menyimpan panjang string di prefix (s:N:"..."), mengubah nama = korupsi.
  3. Re-zip jadi .ss3 baru (in-memory).
  4. POST multipart ke bridge plugin → dapat slider_id.
  5. Kembalikan shortcode `[smartslider3 slider="X"]` untuk di-inject ke
     Elementor JSON.

Pola desain mengikuti WordPressClient.create_elementskit_template():
  - Bridge PHP menerima payload
  - Bridge PHP memanggil Public API resmi Nextend
  - iAAWG murni jadi orchestrator, tidak menyentuh internal SS3.
"""

import io
import os
import zipfile
import httpx


# Nama slot gambar di dalam template.ss3.
# HARUS sinkron dengan file di dalam ZIP template. Verified via unzip.
TEMPLATE_IMAGE_SLOTS = ("slide-1.jpg", "slide-2.jpg", "slide-3.jpg")


def build_customized_ss3(template_path: str, replacement_images: dict) -> bytes:
    """
    Ambil template .ss3, timpa gambar slot dengan bytes dari iAAWG,
    kembalikan bytes .ss3 baru (siap upload).

    Parameter:
      template_path       : path ke assets/sliders/hero-template.ss3
      replacement_images  : dict {slot_filename: bytes_gambar_baru}
                            slot_filename harus salah satu dari
                            TEMPLATE_IMAGE_SLOTS. Slot yang tidak diberikan
                            akan tetap pakai gambar dummy dari template
                            (fallback aman — tidak akan crash / blank).

    Return: bytes .ss3 yang sudah dimodifikasi.
    """
    if not os.path.isfile(template_path):
        raise FileNotFoundError(f"Template .ss3 tidak ditemukan: {template_path}")

    output_buffer = io.BytesIO()

    with zipfile.ZipFile(template_path, "r") as zin:
        with zipfile.ZipFile(output_buffer, "w", zipfile.ZIP_DEFLATED) as zout:
            for item in zin.infolist():
                original_bytes = zin.read(item.filename)

                # Cek apakah entry ini salah satu slot gambar yang mau diganti.
                # Cocokkan basename supaya aman terhadap path prefix (images/).
                basename = os.path.basename(item.filename)
                if basename in replacement_images and replacement_images[basename]:
                    # Timpa dengan gambar baru — nama file di ZIP tetap sama
                    # supaya referensi di `data` PHP-serialized tetap valid.
                    zout.writestr(item, replacement_images[basename])
                else:
                    zout.writestr(item, original_bytes)

    return output_buffer.getvalue()


async def deploy_slider_to_wordpress(
    wp_base_url: str,
    wp_auth_header: str,
    ss3_bytes: bytes,
    filename: str = "hero.ss3",
    timeout: float = 60.0,
) -> int:
    """
    POST file .ss3 ke bridge plugin di WordPress.
    Return: slider_id (int) kalau sukses, 0 kalau gagal.

    Parameter:
      wp_base_url     : contoh 'http://localhost/zecurion'
      wp_auth_header  : nilai lengkap header Authorization, mis.
                        'Basic dXNlcjpwYXNz...' — biasanya diambil dari
                        WordPressClient.headers["Authorization"].
      ss3_bytes       : hasil build_customized_ss3()
      filename        : nama file untuk multipart (informational only)
    """
    url = f"{wp_base_url.rstrip('/')}/wp-json/iaawg/v1/smartslider/import"

    files = {
        "ss3_file": (filename, ss3_bytes, "application/octet-stream"),
    }
    headers = {
        "Authorization": wp_auth_header,
        # JANGAN set Content-Type di sini — httpx akan atur otomatis dengan
        # boundary multipart yang benar. Set manual = server tidak bisa parse.
    }

    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            response = await client.post(url, files=files, headers=headers)
        except Exception as e:
            print(f"[SmartSlider Error] Kendala jaringan: {e}")
            return 0

    if response.status_code == 200:
        data = response.json()
        slider_id = int(data.get("slider_id") or 0)
        if slider_id:
            print(
                f"[SmartSlider] ✓ Slider ter-import via Public API — "
                f"ID: {slider_id}, shortcode: {data.get('shortcode')}"
            )
            return slider_id
        print(f"[SmartSlider Error] Response 200 tapi slider_id kosong: {data}")
        return 0

    print(
        f"[SmartSlider Error] Bridge menolak import: "
        f"{response.status_code} — {response.text[:400]}"
    )
    return 0


def read_image_bytes(path: str) -> bytes:
    """Helper: baca file gambar. Kembalikan bytes kosong kalau tidak ada."""
    if not path or not os.path.isfile(path):
        return b""
    with open(path, "rb") as f:
        return f.read()


async def orchestrate_slider_deploy(
    template_path: str,
    wp_client,
    brand: str,
    visual_dir: str,
) -> str:
    """
    High-level orchestrator — dipanggil dari main.py Phase 3.

    Mapping slot → aset iAAWG (lihat percakapan desain):
      slide-1.jpg → banner AI home
      slide-2.jpg → banner AI solusi
      slide-3.jpg → banner AI produk

    Slot yang tidak punya file lokal fallback ke gambar dummy template
    (aman — slider tetap render, tidak blank).

    Return: shortcode string `[smartslider3 slider="X"]` untuk di-inject
    ke Elementor JSON hero home. Kembalikan "" kalau deploy gagal —
    caller boleh fallback ke hero image lama.
    """
    print("\n[*] Deploy Smart Slider 3 Hero...")

    # ── 1. Petakan slot → path banner iAAWG ──────────────────────────────────
    slot_to_source = {
        "slide-1.jpg": os.path.join(visual_dir, f"{brand}_home_banner.jpg"),
        "slide-2.jpg": os.path.join(visual_dir, f"{brand}_solusi_banner.jpg"),
        "slide-3.jpg": os.path.join(visual_dir, f"{brand}_produk_banner.jpg"),
    }

    replacements = {}
    for slot, source_path in slot_to_source.items():
        img_bytes = read_image_bytes(source_path)
        if img_bytes:
            replacements[slot] = img_bytes
            print(f"    [✓] Slot {slot} ← {os.path.basename(source_path)}")
        else:
            print(f"    [!] Slot {slot} tidak ada aset — pakai dummy template")

    # ── 2. Build .ss3 baru dengan gambar brand ───────────────────────────────
    try:
        ss3_bytes = build_customized_ss3(template_path, replacements)
    except Exception as e:
        print(f"[SmartSlider Error] Gagal build .ss3: {e}")
        return ""

    # ── 3. Upload ke bridge → dapat slider_id ────────────────────────────────
    slider_id = await deploy_slider_to_wordpress(
        wp_base_url=wp_client.base_url,
        wp_auth_header=wp_client.headers["Authorization"],
        ss3_bytes=ss3_bytes,
        filename=f"{brand}-hero.ss3",
    )

    if not slider_id:
        print("[SmartSlider] Deploy gagal — halaman home akan pakai hero image biasa.")
        return ""

    return f'[smartslider3 slider="{slider_id}"]'
