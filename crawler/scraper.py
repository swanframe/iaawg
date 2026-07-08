import asyncio
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup

class BaseScraper:
    def __init__(self, timeout: int = 30000):
        self.timeout = timeout

    async def scrape_url(self, url: str) -> str:
        """
        Mengambil konten HTML dari URL menggunakan Playwright (headless).
        Dilengkapi dengan mekanisme Retry hingga 3 kali.
        """
        if not url.startswith(("http://", "https://")):
            url = f"https://{url}"
            
        max_retries = 3
        for attempt in range(1, max_retries + 1):
            print(f"    [~] Percobaan scraping {attempt}/{max_retries} untuk: {url}...")
            
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()
                try:
                    await page.goto(url, timeout=self.timeout, wait_until="networkidle")
                    content = await page.content()
                    if content and len(content) > 1000: # Validasi awal bahwa HTML terunduh cukup besar
                        return content
                except Exception as e:
                    print(f"    [!] Percobaan {attempt} gagal: {str(e)}")
                    if attempt == max_retries:
                        # Fallback terakhir di percobaan ke-3 jika ada HTML parsial
                        return await page.content()
                finally:
                    await browser.close()
            
            # Berikan jeda 3 detik sebelum mencoba ulang (jika bukan percobaan terakhir)
            if attempt < max_retries:
                await asyncio.sleep(3)
                
        return ""

class ContentExtractor:
    @staticmethod
    def clean_html(html_content: str) -> str:
        """
        Membersihkan tag HTML tidak penting dan mengambil teks esensial.
        """
        if not html_content:
            return ""
            
        soup = BeautifulSoup(html_content, "html.parser")
        
        # Hapus elemen yang mengganggu ekstraksi informasi esensial
        for element in soup(["script", "style", "nav", "footer", "header", "noscript"]):
            element.extract()
            
        # Ambil teks dan rapikan whitespace
        text = soup.get_text(separator="\n")
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        return "\n".join(lines)