import httpx
import urllib.parse
from abc import ABC, abstractmethod
from config.settings import settings

class BaseImageProvider(ABC):
    @abstractmethod
    async def generate_banner(self, prompt_desc: str, brand_name: str) -> bytes:
        pass

class PollinationsProvider(BaseImageProvider):
    def __init__(self):
        self.base_url = "https://image.pollinations.ai/p/"

    async def generate_banner(self, prompt_desc: str, brand_name: str) -> bytes:
        """
        Generate banner via Pollinations.ai (Gratis, tanpa API Key).
        Prompt dipastikan pendek dan berbahasa Inggris demi stabilitas output AI.
        """
        # Standarisasi prompt: Bersihkan karakter non-alphanumeric, buat pendek dan ringkas
        clean_desc = "".join([c if c.isalnum() or c in " _-" else "" for c in prompt_desc])
        words = clean_desc.split()[:8]  # Batasi maks 8 kata agar tidak terlalu panjang
        short_english_prompt = " ".join(words)
        
        # Contoh build query prompt berkualitas tinggi untuk teknologi & cybersec
        refined_query = f"modern clean tech banner for {brand_name}, {short_english_prompt}, professional, 1200x400"
        encoded_query = urllib.parse.quote(refined_query)
        
        url = f"{self.base_url}{encoded_query}?width=1200&height=400&enhance=true"
        print(f"[Pollinations] Requesting banner url: {url}")
        
        async with httpx.AsyncClient(timeout=40.0) as client:
            try:
                response = await client.get(url)
                if response.status_code == 200:
                    return response.content
                else:
                    print(f"[Pollinations Error] Status code: {response.status_code}")
                    return b""
            except Exception as e:
                print(f"[Pollinations Error] Gagal generate banner: {e}")
                return b""

class GPTImageProvider(BaseImageProvider):
    async def generate_banner(self, prompt_desc: str, brand_name: str) -> bytes:
        print("[GPT Image] Provider terpanggil (Upgrade Plan Needed).")
        # Placeholder integrasi DALL-E OpenAI
        return b""

class BannerbearProvider(BaseImageProvider):
    async def generate_banner(self, prompt_desc: str, brand_name: str) -> bytes:
        print("[Bannerbear] Provider terpanggil (Upgrade Plan Needed).")
        # Placeholder integrasi API Bannerbear
        return b""

def get_image_provider(provider_name: str = None) -> BaseImageProvider:
    provider = provider_name or settings.DEFAULT_IMAGE_PROVIDER
    if provider.lower() == "pollinations":
        return PollinationsProvider()
    elif provider.lower() == "gpt_image":
        return GPTImageProvider()
    elif provider.lower() == "bannerbear":
        return BannerbearProvider()
    else:
        raise NotImplementedError(f"Provider image {provider} belum diimplementasikan.")