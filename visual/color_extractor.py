import os
import httpx
from colorthief import ColorThief

class ColorExtractor:
    @staticmethod
    def extract_palette(image_path: str, color_count: int = 3) -> list[str]:
        """
        Mengekstrak palet warna dari file gambar lokal menggunakan ColorThief.
        Mengembalikan list berisi hex color strings.
        """
        if not os.path.exists(image_path):
            print(f"[Color Extractor] File tidak ditemukan: {image_path}. Menggunakan palet fallback iLogo.")
            return ["#1E7E34", "#f4f4f4", "#333333"]
            
        try:
            color_thief = ColorThief(image_path)
            # Ambil warna dominan
            dominant_color = color_thief.get_color(quality=1)
            # Ambil palet warna pendukung
            palette = color_thief.get_palette(color_count=color_count, quality=1)
            
            # Konversi RGB ke HEX format string
            def rgb_to_hex(rgb):
                return '#{:02x}{:02x}{:02x}'.format(*rgb)
                
            hex_palette = [rgb_to_hex(dominant_color)] + [rgb_to_hex(col) for col in palette]
            # Hapus duplikat sambil mempertahankan urutan
            return list(dict.fromkeys(hex_palette))[:color_count]
        except Exception as e:
            print(f"[Color Extractor Error] Gagal mengekstrak warna: {e}")
            return ["#1E7E34", "#f4f4f4", "#333333"]