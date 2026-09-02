import base64
import httpx
from openai import OpenAI
from config.settings import settings, get_setting

class StockImageFetcher:
    def __init__(self):
        self.api_key = get_setting("UNSPLASH_API_KEY") or settings.UNSPLASH_API_KEY
        self.base_url = "https://api.unsplash.com/search/photos"

    async def fetch_stock_url(self, keyword: str) -> str:
        """
        Mencari gambar di Unsplash berdasarkan keyword bahasa inggris/teknis.
        Mengembalikan string URL gambar mentah (regular size).
        """
        if not self.api_key:
            print("[Unsplash] UNSPLASH_API_KEY tidak dikonfigurasi. Menggunakan placeholder image.")
            return f"https://images.unsplash.com/photo-1518770660439-4636190af475?w=800" # Default tech image
            
        headers = {"Authorization": f"Client-ID {self.api_key}"}
        params = {
            "query": keyword,
            "per_page": 1,
            "orientation": "landscape"
        }
        
        async with httpx.AsyncClient(timeout=15.0) as client:
            try:
                response = await client.get(self.base_url, headers=headers, params=params)
                if response.status_code == 200:
                    data = response.json()
                    results = data.get("results", [])
                    if results:
                        return results[0]["urls"]["regular"]
                    else:
                        print(f"[Unsplash] Gambar tidak ditemukan untuk keyword: {keyword}")
                        return "https://images.unsplash.com/photo-1518770660439-4636190af475?w=800"
                else:
                    print(f"[Unsplash Error] Status code: {response.status_code} - {response.text}")
                    return "https://images.unsplash.com/photo-1518770660439-4636190af475?w=800"
            except Exception as e:
                print(f"[Unsplash Error] Kendala koneksi API Unsplash: {e}")
                return "https://images.unsplash.com/photo-1518770660439-4636190af475?w=800"


def generate_ai_image(prompt: str, quality: str = "medium") -> bytes:
    """
    Generate 1 gambar via OpenAI gpt-image-1 (opsional, berbayar — dipicu manual
    oleh operator per artikel di halaman review, bukan default batch).
    Selalu landscape 1536x1024 untuk featured image blog. Melempar exception
    kalau API key tidak ada / request gagal — caller yang menangani response error.
    """
    api_key = get_setting("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY tidak ditemukan (tidak ada di DB maupun .env)")

    quality = (quality or "medium").lower()
    if quality not in {"low", "medium", "high"}:
        quality = "medium"

    client = OpenAI(api_key=api_key)
    result = client.images.generate(
        model="gpt-image-1",
        prompt=prompt,
        size="1536x1024",
        quality=quality,
        n=1,
    )
    b64 = result.data[0].b64_json
    return base64.b64decode(b64)