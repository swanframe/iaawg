import httpx
from config.settings import settings

class StockImageFetcher:
    def __init__(self):
        self.api_key = settings.UNSPLASH_API_KEY
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