import asyncio
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup

# ── Cloudflare / Bot-Wall Fingerprints ────────────────────────────────────────
# Teks penanda yang muncul di halaman challenge/block Cloudflare.
# Dua atau lebih penanda = hampir pasti bukan konten asli brand.
_CF_MARKERS = [
    "checking your browser",
    "cloudflare ray id",
    "cf-browser-verification",
    "ddos protection by cloudflare",
    "performance & security by cloudflare",
    "enable javascript and cookies to continue",
    "access denied",
    "error 1020",
    "error 1015",
    "error 1009",
    "just a moment",
    "cf_chl_opt",
]

# User-Agent Chrome realistis — perbarui setiap beberapa bulan agar tetap relevan
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)

# Script diinjeksi sebelum script halaman berjalan — menghapus penanda #1 headless browser
_STEALTH_SCRIPT = """
    Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
    Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3] });
    Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
    window.chrome = { runtime: {} };
"""


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
                # Anti-Detection: argumen browser untuk menyembunyikan tanda-tanda otomasi
                browser = await p.chromium.launch(
                    headless=True,
                    args=[
                        "--disable-blink-features=AutomationControlled",
                        "--no-sandbox",
                        "--disable-setuid-sandbox",
                        "--disable-dev-shm-usage",
                        "--disable-gpu",
                    ],
                )
                # Anti-Detection: context browser yang terlihat seperti pengguna nyata
                context = await browser.new_context(
                    user_agent=_USER_AGENT,
                    viewport={"width": 1920, "height": 1080},
                    locale="en-US",
                    timezone_id="America/New_York",
                    extra_http_headers={
                        "Accept-Language": "en-US,en;q=0.9",
                        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                        "Sec-Fetch-Site": "none",
                        "Sec-Fetch-Mode": "navigate",
                    },
                )
                page = await context.new_page()

                # Anti-Detection: sembunyikan properti webdriver dari JavaScript halaman
                await page.add_init_script(_STEALTH_SCRIPT)

                try:
                    # domcontentloaded lebih cepat & menghindari timeout loop challenge CF
                    await page.goto(url, timeout=self.timeout, wait_until="domcontentloaded")
                    # Beri jeda agar Cloudflare Turnstile sempat auto-resolve jika ada
                    await asyncio.sleep(3)
                    content = await page.content()
                    if content and len(content) > 1000:  # Validasi awal bahwa HTML terunduh cukup besar
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
    def is_bot_wall(text: str) -> bool:
        """
        Mengembalikan True jika teks bersih terdeteksi sebagai halaman
        challenge/block Cloudflare atau WAF lainnya, bukan konten brand asli.
        Dua atau lebih penanda dianggap positif untuk menghindari false-positive.
        """
        text_lower = text.lower()
        hits = sum(1 for marker in _CF_MARKERS if marker in text_lower)
        return hits >= 2

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