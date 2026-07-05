import asyncio
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup

class BaseScraper:
    def __init__(self, timeout: int = 30000):
        self.timeout = timeout

    async def scrape_url(self, url: str) -> str:
        """
        Mengambil konten HTML dari URL menggunakan Playwright (headless).
        """
        if not url.startswith(("http://", "https://")):
            url = f"https://{url}"
            
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            try:
                await page.goto(url, timeout=self.timeout, wait_until="networkidle")
                content = await page.content()
                return content
            except Exception as e:
                print(f"[Error Crawler] Gagal mengakses {url}: {str(e)}")
                # Fallback sederhana jika networkidle timeout namun HTML parsial didapat
                return await page.content()
            finally:
                await browser.close()

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