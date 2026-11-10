import sys
import asyncio
from pathlib import Path
from loguru import logger
from playwright.async_api import async_playwright

from src.core.config import config

class AuthHelper:
    """Helper to open a browser window with persistent context for manual Google login."""

    @staticmethod
    async def open_login_window():
        """Launches browser allowing the user to sign in to Google.
        The session is automatically saved in config.USER_DATA_DIR.
        """
        logger.info(f"Opening browser for Google login using profile: {config.USER_DATA_DIR}")
        
        async with async_playwright() as p:
            args = [
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-infobars"
            ]
            
            # Prefer real Google Chrome to pass Google's strict bot detection
            browser_channel = config.BROWSER_CHANNEL
            context = None
            
            channels = list(dict.fromkeys([browser_channel, "chrome", "msedge", None]))
            for channel in channels:
                try:
                    kwargs = {
                        "user_data_dir": str(config.USER_DATA_DIR),
                        "headless": False,
                        "args": args,
                        "viewport": {"width": 1280, "height": 800}
                    }
                    if channel:
                        kwargs["channel"] = channel
                    
                    context = await p.chromium.launch_persistent_context(**kwargs)
                    logger.info(f"Launched browser with channel: {channel or 'bundled chromium'}")
                    break
                except Exception as e:
                    logger.warning(f"Could not launch browser with channel {channel}: {e}")
                    continue

            if not context:
                logger.error("Failed to launch any browser channel for login.")
                return False

            page = context.pages[0] if context.pages else await context.new_page()
            
            target_url = config.get_clean_folder_url() or "https://drive.google.com"
            logger.info(f"Navigating to {target_url}...")
            await page.goto(target_url, timeout=60000)

            logger.info("Silakan lakukan login Google pada jendela browser yang terbuka.")
            logger.info("Jendela akan tetap terbuka sampai Anda menutupnya atau menekan Enter di konsol...")

            # Wait until the user closes the page or logs in
            try:
                # Keep open until page is closed by user or enters drive
                while not page.is_closed():
                    await asyncio.sleep(1)
                    # Check if page is currently on Drive main interface
                    if "drive.google.com/drive" in page.url and "accounts.google.com" not in page.url:
                        # User has reached Drive!
                        pass
            except Exception:
                pass
            finally:
                try:
                    await context.close()
                except Exception:
                    pass
                    
            logger.info("Google login browser window closed. Profil sesi telah tersimpan!")
            return True

    @staticmethod
    def is_logged_in_sync() -> bool:
        """Heuristic check: does the user data dir have cookies/storage?"""
        profile_dir = Path(config.USER_DATA_DIR)
        if not profile_dir.exists():
            return False
        # In Chromium user data dirs, Default/Cookies or Default/Network/Cookies exists when used
        cookies_files = list(profile_dir.glob("**/Cookies*")) + list(profile_dir.glob("**/Network/Cookies*"))
        return len(cookies_files) > 0

if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    asyncio.run(AuthHelper.open_login_window())
