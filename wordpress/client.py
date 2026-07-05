import base64
import httpx
from config.settings import settings

class WordPressClient:
    def __init__(self):
        self.base_url = settings.WP_URL.rstrip('/')
        self.username = settings.WP_USERNAME
        self.app_password = settings.WP_APPLICATION_PASSWORD
        
        if not self.base_url or not self.username or not self.app_password:
            raise ValueError("Konfigurasi WordPress (WP_URL, WP_USERNAME, WP_APPLICATION_PASSWORD) belum lengkap di .env")
            
        # Membuat Basic Auth Token dari Application Password
        credential = f"{self.username}:{self.app_password}"
        encoded_cred = base64.b64encode(credential.encode('utf-8')).decode('utf-8')
        
        self.headers = {
            "Authorization": f"Basic {encoded_cred}",
            "Content-Type": "application/json"
        }

    async def create_page(self, title: str, content: str, status: str = "publish", slug: str = None) -> dict:
        """
        Membuat halaman baru (Page) di WordPress menggunakan REST API v2.
        """
        url = f"{self.base_url}/wp-json/wp/v2/pages"
        payload = {
            "title": title,
            "content": content,
            "status": status
        }
        if slug:
            payload["slug"] = slug

        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.post(url, json=payload, headers=self.headers)
                if response.status_code in [200, 201]:
                    print(f"[WordPress] Berhasil deploy halaman: '{title}'")
                    return response.json()
                else:
                    print(f"[WordPress Error] Gagal deploy '{title}': {response.status_code} - {response.text}")
                    return {}
            except Exception as e:
                print(f"[WordPress Error] Kendala jaringan saat mengakses REST API: {e}")
                return {}

    async def create_post(self, title: str, content: str, excerpt: str = "", status: str = "publish") -> dict:
        """
        Membuat artikel blog baru (Post) di WordPress untuk tipe data Blog.
        """
        url = f"{self.base_url}/wp-json/wp/v2/posts"
        payload = {
            "title": title,
            "content": content,
            "excerpt": excerpt,
            "status": status
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.post(url, json=payload, headers=self.headers)
                if response.status_code in [200, 201]:
                    print(f"[WordPress] Berhasil deploy postingan blog: '{title}'")
                    return response.json()
                else:
                    print(f"[WordPress Error] Gagal deploy blog '{title}': {response.status_code} - {response.text}")
                    return {}
            except Exception as e:
                print(f"[WordPress Error] Kendala jaringan saat mengakses REST API: {e}")
                return {}