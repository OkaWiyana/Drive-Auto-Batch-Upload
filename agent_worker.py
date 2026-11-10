import sys
import asyncio
from loguru import logger
from pathlib import Path

from src.core.config import config
from src.core.scanner import DirectoryScanner
from src.core.queue_manager import QueueManager
from src.browser.browser_pool import BrowserPool
from src.core.scheduler import Scheduler

def setup_logging():
    log_file = config.LOG_DIR / "gdrive_agent.log"
    logger.add(
        str(log_file),
        rotation="10 MB",
        retention="7 days",
        level="INFO",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {message}"
    )

async def main():
    setup_logging()
    logger.info("GDrive Auto Uploader Agent started")

    folder_url = config.get_clean_folder_url()
    if not folder_url:
        logger.error("GDRIVE_FOLDER_URL belum diset. Masukkan tautan folder Google Drive.")
        return

    logger.info(f"Target Google Drive Folder: {folder_url}")
    logger.info(f"Konfigurasi: {config.MAX_WORKERS} Tab | Batch Size: {config.BATCH_SIZE} File")

    queue_manager = QueueManager()
    browser_pool = BrowserPool()
    scheduler = Scheduler(queue_manager, browser_pool)

    def on_new_files(files: list[Path]):
        logger.info(f"Menambahkan {len(files)} file baru ke antrean")
        queue_manager.add_files(files)

    directory_scanner = DirectoryScanner(callback=on_new_files)
    directory_scanner.scan_existing()
    if getattr(config, "WATCHDOG_ENABLED", True):
        directory_scanner.start_watching()

    try:
        await browser_pool.start()
        logger.info("Menjalankan worker upload paralel...")
        await scheduler.run()

    except KeyboardInterrupt:
        logger.info("Menerima sinyal berhenti (KeyboardInterrupt)...")
    except Exception as e:
        logger.error(f"Terjadi kesalahan pada agent: {e}")
    finally:
        logger.info("Membersihkan sumber daya...")
        scheduler.stop()
        directory_scanner.stop_watching()
        await browser_pool.stop()
        logger.info("GDrive Agent selesai")

if __name__ == "__main__":
    if sys.platform == "win32":
        try:
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
        except Exception:
            pass
    asyncio.run(main())
