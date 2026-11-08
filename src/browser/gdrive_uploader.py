import asyncio
import os
from pathlib import Path
from loguru import logger
from playwright.async_api import Page, TimeoutError

from src.core.config import config

class GDriveUploader:
    def __init__(self, page: Page, worker_name: str = "Worker"):
        self.page = page
        self.worker_name = worker_name

    async def is_logged_in(self) -> bool:
        """Check if currently authenticated in Google Drive."""
        current_url = self.page.url.lower()
        if "accounts.google.com" in current_url or "signin" in current_url:
            return False
        return True

    async def ensure_folder_page(self, folder_url: str) -> bool:
        """Navigates to the folder URL and ensures the folder is open."""
        clean_url = config.get_clean_folder_url() or folder_url
        if not clean_url:
            logger.error(f"[{self.worker_name}] Folder URL Google Drive kosong! Silakan isi di pengaturan.")
            return False

        current_url = self.page.url
        # If already on the page, don't necessarily reload unless needed
        if clean_url not in current_url:
            logger.info(f"[{self.worker_name}] Membuka folder Drive: {clean_url}")
            try:
                await self.page.goto(clean_url, wait_until="domcontentloaded", timeout=45000)
            except Exception as e:
                logger.warning(f"[{self.worker_name}] goto timed out or errored: {e}, continuing...")

        if not await self.is_logged_in():
            logger.error(f"[{self.worker_name}] Akun Google belum login atau dialihkan ke halaman login.")
            return False

        # Wait for either the main content container or the '+ New' button
        try:
            await self.page.wait_for_selector(
                "button:has-text('New'), button:has-text('Baru'), [aria-label*='New'], [aria-label*='Baru'], div[role='main']",
                timeout=15000
            )
        except Exception:
            logger.debug(f"[{self.worker_name}] Main container selector wait passed.")

        return True

    async def upload_batch(self, batch: dict) -> bool:
        """Uploads a batch of files to the Google Drive folder."""
        batch_id = batch["id"]
        files = batch["files"]

        valid_files = [f for f in files if Path(f).exists()]
        if len(valid_files) != len(files):
            missing = len(files) - len(valid_files)
            logger.warning(f"[{self.worker_name}|{batch_id}] {missing} file tidak ditemukan di disk, dilewati.")
            files = valid_files

        if not files:
            logger.error(f"[{self.worker_name}|{batch_id}] Tidak ada file valid untuk diunggah!")
            return False

        logger.info(f"[{self.worker_name}|{batch_id}] Memulai upload batch ({len(files)} file)...")

        # 1. Pastikan tab berada pada URL folder Google Drive
        target_url = config.get_clean_folder_url()
        ready = await self.ensure_folder_page(target_url)
        if not ready:
            return False

        # 2. Trigger Upload File
        uploaded_triggered = False

        # Cara A: File Chooser via tombol '+ New' / '+ Baru'
        new_btn_selectors = [
            "button:has-text('New')",
            "button:has-text('Baru')",
            "[aria-label='New']",
            "[aria-label='Baru']",
            "div[role='button']:has-text('New')",
            "div[role='button']:has-text('Baru')"
        ]

        new_btn = None
        for sel in new_btn_selectors:
            loc = self.page.locator(sel).first
            if await loc.count() > 0 and await loc.is_visible():
                new_btn = loc
                break

        if new_btn:
            try:
                await new_btn.click()
                await asyncio.sleep(0.6)

                upload_menu_item = self.page.locator(
                    "[role='menuitem']:has-text('File upload'), [role='menuitem']:has-text('Upload file'), [role='menuitem']:has-text('Unggah file')"
                ).first

                if await upload_menu_item.count() > 0 and await upload_menu_item.is_visible():
                    async with self.page.expect_file_chooser(timeout=10000) as fc_info:
                        await upload_menu_item.click()
                    file_chooser = await fc_info.value
                    await file_chooser.set_files(files)
                    uploaded_triggered = True
                    logger.info(f"[{self.worker_name}|{batch_id}] File berhasil dikirim melalui menu upload!")
            except Exception as e:
                logger.warning(f"[{self.worker_name}|{batch_id}] Menu upload file chooser gagal: {e}")

        # Cara B: Fallback langsung ke input[type='file'] di DOM jika Cara A tidak jalan
        if not uploaded_triggered:
            try:
                file_input = self.page.locator("input[type='file']").first
                if await file_input.count() > 0:
                    await file_input.set_input_files(files, timeout=15000)
                    uploaded_triggered = True
                    logger.info(f"[{self.worker_name}|{batch_id}] File dikirim langsung melalui input[type='file']!")
            except Exception as e:
                logger.warning(f"[{self.worker_name}|{batch_id}] Direct file input upload gagal: {e}")

        # Cara C: Drag & Drop via Playwright event jika input tidak ditemukan
        if not uploaded_triggered:
            try:
                # Expect file chooser fallback
                drop_target = self.page.locator("div[role='main']").first
                if await drop_target.count() > 0:
                    async with self.page.expect_file_chooser(timeout=5000) as fc_info:
                        await drop_target.click()
                    file_chooser = await fc_info.value
                    await file_chooser.set_files(files)
                    uploaded_triggered = True
            except Exception as e:
                logger.error(f"[{self.worker_name}|{batch_id}] Semua cara upload gagal: {e}")
                return False

        # 3. Handle duplicate modal jika muncul ("Keep separate" / "Replace")
        await asyncio.sleep(1.5)
        await self._handle_duplicate_modal()

        # 4. Tunggu proses upload di Drive selesai
        completed = await self._wait_for_upload_completion(batch_id, len(files))
        return completed

    async def _handle_duplicate_modal(self):
        """Detect and handle Google Drive's duplicate file prompt."""
        try:
            duplicate_dialog = self.page.locator(
                "div[role='dialog']:has-text('already exists'), div[role='dialog']:has-text('sudah ada')"
            ).first
            if await duplicate_dialog.count() > 0 and await duplicate_dialog.is_visible():
                logger.info(f"[{self.worker_name}] Terdeteksi dialog file duplikat...")
                if config.DUPLICATE_ACTION == "replace":
                    btn = duplicate_dialog.locator("button:has-text('Replace'), button:has-text('Ganti')").first
                else:
                    btn = duplicate_dialog.locator(
                        "button:has-text('Keep separate'), button:has-text('Simpan keduanya')"
                    ).first

                if await btn.count() > 0:
                    await btn.click()
                    logger.info(f"[{self.worker_name}] Memilih aksi duplikat: {config.DUPLICATE_ACTION}")
        except Exception:
            pass

    async def _wait_for_upload_completion(self, batch_id: str, file_count: int, timeout_sec: int = 900) -> bool:
        """Polls Google Drive upload progress tray until batch is done."""
        logger.info(f"[{self.worker_name}|{batch_id}] Memantau progress upload...")
        start_time = asyncio.get_event_loop().time()

        while True:
            # Check for duplicate prompt periodically
            await self._handle_duplicate_modal()

            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed > timeout_sec:
                logger.error(f"[{self.worker_name}|{batch_id}] Upload timeout setelah {timeout_sec}s.")
                return False

            # Inspect Drive's upload notification popup / tray
            # Usually located at bottom-right
            tray = self.page.locator(
                "div[role='region'][aria-label*='Upload'], div[aria-live='polite'], div:has-text('uploads complete'), div:has-text('upload selesai'), div:has-text('selesai')"
            )

            try:
                # Look for completion text:
                # e.g. "X uploads complete" or "X upload selesai" or "Selesai mengupload"
                completion_indicators = [
                    f"{file_count} uploads complete",
                    f"{file_count} upload selesai",
                    "uploads complete",
                    "upload selesai",
                    "Selesai mengupload",
                    "Complete"
                ]

                page_text = await self.page.evaluate("() => document.body.innerText")

                is_complete = any(ind.lower() in page_text.lower() for ind in completion_indicators)
                if is_complete:
                    logger.info(f"[{self.worker_name}|{batch_id}] ✅ Berhasil mengupload seluruh file dalam batch ({elapsed:.1f}s)!")
                    return True

                # Check if there are active upload progress bars or spinners
                progress_indicators = self.page.locator(
                    "[role='progressbar'], [aria-label*='Uploading'], [aria-label*='Mengunggah'], div[class*='progress']"
                )
                active_count = await progress_indicators.count()

                # If no progress bars remain after at least 5 seconds and some files were uploaded
                if elapsed > 5 and active_count == 0:
                    # Double check if any error occurred
                    error_elem = self.page.locator("button:has-text('Retry'), button:has-text('Coba lagi')")
                    if await error_elem.count() > 0:
                        logger.warning(f"[{self.worker_name}|{batch_id}] Terdeteksi error upload pada item Drive, mencoba retry...")
                        try:
                            await error_elem.first.click()
                        except Exception:
                            pass

                    # If no errors and no active progress bars, consider finished
                    logger.info(f"[{self.worker_name}|{batch_id}] ✅ Indikator upload selesai ({elapsed:.1f}s).")
                    return True

            except Exception as e:
                logger.debug(f"[{self.worker_name}|{batch_id}] Polling error: {e}")

            await asyncio.sleep(2)
