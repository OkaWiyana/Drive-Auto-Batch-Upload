import asyncio
from pathlib import Path
from loguru import logger
from playwright.async_api import async_playwright, BrowserContext, Page

from src.core.config import config

class BrowserPool:
    def __init__(self):
        self.playwright = None
        self.context: BrowserContext = None
        self.pages: list[Page] = []
        self.available_pages = asyncio.Queue()
        self._lock = asyncio.Lock()

    async def start(self):
        logger.info("Menginisialisasi Browser Pool dengan profil persisten...")
        self.playwright = await async_playwright().start()

        args = [
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-infobars"
        ]

        browser_channel = config.BROWSER_CHANNEL
        self.context = None

        # Attempt to launch with preferred browser channel without duplicates
        channels = list(dict.fromkeys([browser_channel, "chrome", "msedge", None]))
        for channel in channels:
            try:
                kwargs = {
                    "user_data_dir": str(config.USER_DATA_DIR),
                    "headless": config.HEADLESS,
                    "args": args,
                    "viewport": {"width": 1280, "height": 800}
                }
                if channel:
                    kwargs["channel"] = channel

                self.context = await self.playwright.chromium.launch_persistent_context(**kwargs)
                logger.info(f"Browser pool berhasil berjalan menggunakan channel: {channel or 'bundled chromium'}")
                break
            except Exception as e:
                logger.warning(f"Gagal membuka channel {channel}: {e}")
                continue

        if not self.context:
            raise RuntimeError("Gagal membuka browser context. Pastikan browser tidak sedang terkunci.")

        # Allocate worker tabs
        logger.info(f"Membuka {config.MAX_WORKERS} tab paralel untuk worker upload...")
        
        # Reuse existing page if any
        if self.context.pages:
            self.pages.append(self.context.pages[0])
            await self.available_pages.put(self.context.pages[0])
            count_needed = config.MAX_WORKERS - 1
        else:
            count_needed = config.MAX_WORKERS

        for i in range(count_needed):
            page = await self.context.new_page()
            self.pages.append(page)
            await self.available_pages.put(page)

        logger.info(f"Browser Pool siap dengan {len(self.pages)} tab aktif.")

    async def get_page(self) -> Page:
        """Mengambil tab yang tersedia dari antrean pool."""
        return await self.available_pages.get()

    async def release_page(self, page: Page):
        """Mengembalikan tab ke pool. Jika tab crash/tertutup, tab baru dibuat."""
        if page.is_closed():
            logger.warning("Tab browser tertutup atau crash. Membuka tab pengganti baru...")
            try:
                new_page = await self.context.new_page()
                if page in self.pages:
                    self.pages.remove(page)
                self.pages.append(new_page)
                await self.available_pages.put(new_page)
            except Exception as e:
                logger.error(f"Gagal membuat tab pengganti: {e}")
        else:
            await self.available_pages.put(page)

    async def stop(self):
        """Menutup browser context dan playwright."""
        logger.info("Menutup Browser Pool...")
        try:
            if self.context:
                await self.context.close()
            if self.playwright:
                await self.playwright.stop()
        except Exception as e:
            logger.debug(f"Error saat menutup browser pool: {e}")
        logger.info("Browser Pool ditutup.")
