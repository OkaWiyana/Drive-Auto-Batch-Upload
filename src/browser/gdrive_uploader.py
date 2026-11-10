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
        return "drive.google.com" in current_url

    async def ensure_folder_page(self, folder_url: str) -> bool:
        """Navigates to the folder URL and ensures the folder is open."""
        import re
        clean_url = config.get_clean_folder_url() or folder_url
        if not clean_url:
            logger.error(f"[{self.worker_name}] Folder URL Google Drive kosong! Silakan isi di pengaturan.")
            return False

        current_url = self.page.url
        folder_match = re.search(r'([a-zA-Z0-9_-]{25,})', clean_url)
        folder_id = folder_match.group(1) if folder_match else clean_url

        # Avoid reloading if the tab is already on the target folder
        if not ("drive.google.com" in current_url and folder_id in current_url):
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

        # Tutup notifikasi tray lama jika masih ada
        await self._close_existing_upload_tray()

        # 2. Trigger Upload File
        uploaded_triggered = False

        new_btn_selectors = [
            "button:has-text('New')",
            "button:has-text('Baru')",
            "[aria-label='New']",
            "[aria-label='Baru']",
            "div[role='button']:has-text('New')",
            "div[role='button']:has-text('Baru')"
        ]

        # Coba trigger upload via tombol '+ Baru' -> 'Upload file' (dengan retry sampai 3x jika tab sedang lag)
        for attempt in range(3):
            try:
                # Cari tombol '+ New' / '+ Baru'
                new_btn = None
                for sel in new_btn_selectors:
                    loc = self.page.locator(sel).first
                    if await loc.count() > 0 and await loc.is_visible():
                        new_btn = loc
                        break

                if not new_btn:
                    await asyncio.sleep(1.0)
                    continue

                await new_btn.click()

                # Tunggu menu dropdown muncul
                upload_menu_item = self.page.locator(
                    "[role='menuitem']:has-text('File upload'), "
                    "[role='menuitem']:has-text('Upload file'), "
                    "[role='menuitem']:has-text('Unggah file')"
                ).first

                await upload_menu_item.wait_for(state="visible", timeout=5000)

                async with self.page.expect_file_chooser(timeout=10000) as fc_info:
                    await upload_menu_item.click()
                file_chooser = await fc_info.value
                await file_chooser.set_files(files)
                uploaded_triggered = True
                logger.info(f"[{self.worker_name}|{batch_id}] File berhasil dikirim melalui menu upload!")
                break

            except Exception as e:
                logger.debug(f"[{self.worker_name}|{batch_id}] Percobaan buka menu upload ke-{attempt+1} gagal: {e}")
                # Tekan Escape untuk mereset dropdown jika macet
                try:
                    await self.page.keyboard.press("Escape")
                except Exception:
                    pass
                await asyncio.sleep(1.5)

        # Fallback langsung ke input[type='file'] di DOM jika menu tidak merespon
        if not uploaded_triggered:
            try:
                file_input = self.page.locator("input[type='file']").first
                if await file_input.count() > 0:
                    await file_input.set_input_files(files, timeout=10000)
                    uploaded_triggered = True
                    logger.info(f"[{self.worker_name}|{batch_id}] File dikirim langsung melalui input[type='file']!")
            except Exception as e:
                logger.warning(f"[{self.worker_name}|{batch_id}] Direct file input upload gagal: {e}")

        if not uploaded_triggered:
            logger.error(f"[{self.worker_name}|{batch_id}] Gagal mengirim file ke Google Drive setelah 3 percobaan.")
            return False

        # 3. Handle duplicate modal jika muncul ("Keep separate" / "Replace")
        await asyncio.sleep(1.5)
        await self._handle_duplicate_modal()

        # 4. Tunggu proses upload di Drive selesai
        completed = await self._wait_for_upload_completion(batch_id, len(files))
        return completed

    async def _close_existing_upload_tray(self):
        """Tutup pop-up upload selesai sebelumnya jika ada agar tidak mengacaukan pemantauan batch baru."""
        try:
            close_btn = self.page.locator(
                "div[role='region'] button[aria-label*='Tutup'], "
                "div[role='region'] button[aria-label*='Close'], "
                "button[aria-label*='Tutup'], "
                "button[aria-label*='Close'], "
                "button[aria-label*='pemberitahuan']"
            ).first
            if await close_btn.count() > 0 and await close_btn.is_visible():
                await close_btn.click()
                await asyncio.sleep(0.5)
        except Exception:
            pass

    async def _handle_duplicate_modal(self):
        """Detect and handle Google Drive's duplicate file prompt."""
        try:
            duplicate_dialog = self.page.locator(
                "div[role='dialog']:has-text('Opsi upload'), "
                "div[role='dialog']:has-text('Upload options'), "
                "div[role='dialog']:has-text('already exists'), "
                "div[role='dialog']:has-text('sudah ada'), "
                "div[role='dialog']:has-text('duplikat')"
            ).first
            if await duplicate_dialog.count() > 0 and await duplicate_dialog.is_visible():
                logger.info(f"[{self.worker_name}] Terdeteksi dialog opsi file duplikat...")

                # 1. Jika ada radio button (Format baru Google Drive: 'Ganti item yang ada' vs 'Simpan semua item')
                if config.DUPLICATE_ACTION == "replace":
                    radio_opt = duplicate_dialog.locator(
                        "[role='radio']:has-text('Ganti'), [role='radio']:has-text('Replace'), label:has-text('Ganti'), div:has-text('Ganti item')"
                    ).first
                else:
                    radio_opt = duplicate_dialog.locator(
                        "[role='radio']:has-text('Simpan'), [role='radio']:has-text('Keep'), label:has-text('Simpan'), div:has-text('Simpan semua')"
                    ).first

                if await radio_opt.count() > 0 and await radio_opt.is_visible():
                    try:
                        await radio_opt.click()
                        await asyncio.sleep(0.3)
                    except Exception:
                        pass

                # 2. Centang checkbox 'Terapkan untuk semua' jika tersedia
                checkbox = duplicate_dialog.locator(
                    "input[type='checkbox'], [role='checkbox'], label:has-text('semua'), label:has-text('all')"
                ).first
                if await checkbox.count() > 0 and await checkbox.is_visible():
                    try:
                        checked = await checkbox.get_attribute("aria-checked")
                        if checked != "true":
                            await checkbox.click()
                    except Exception:
                        pass

                # 3. Klik tombol konfirmasi aksi
                # A. Tombol 'Upload' / 'Unggah' (pada modal Opsi upload dengan radio button)
                confirm_btn = duplicate_dialog.locator(
                    "button:has-text('Upload'), button:has-text('Unggah')"
                ).first
                if await confirm_btn.count() > 0 and await confirm_btn.is_visible():
                    await confirm_btn.click()
                    logger.info(f"[{self.worker_name}] Menekan tombol konfirmasi Upload pada dialog duplikat.")
                    await asyncio.sleep(0.8)
                    return

                # B. Tombol langsung jika modal versi lama (tanpa radio button)
                if config.DUPLICATE_ACTION == "replace":
                    btn = duplicate_dialog.locator(
                        "button:has-text('Replace'), button:has-text('Ganti'), button:has-text('Perbarui')"
                    ).first
                else:
                    btn = duplicate_dialog.locator(
                        "button:has-text('Keep separate'), button:has-text('Simpan keduanya'), "
                        "button:has-text('Pisahkan'), button:has-text('Simpan terpisah'), button:has-text('Simpan')"
                    ).first

                if await btn.count() > 0 and await btn.is_visible():
                    await btn.click()
                    logger.info(f"[{self.worker_name}] Memilih aksi duplikat langsung: {config.DUPLICATE_ACTION}")
                    await asyncio.sleep(0.8)
        except Exception as e:
            logger.debug(f"[{self.worker_name}] Duplicate modal check: {e}")

    async def _wait_for_upload_completion(self, batch_id: str, file_count: int, timeout_sec: int = 300) -> bool:
        """Polls Drive's upload status until the batch is done or times out."""
        import re
        logger.info(f"[{self.worker_name}|{batch_id}] Memantau progress upload ({file_count} file, timeout: {timeout_sec}s)...")
        start_time = asyncio.get_event_loop().time()

        # Polling loop
        completion_pattern = re.compile(
            r"(\d+\s+)?uploads?\s+(selesai|complete)|selesai\s+meng(upload|unggah)",
            re.IGNORECASE
        )
        uploading_pattern = re.compile(
            r"meng(upload|unggah)|uploading|menyimpan|sisa\s+\d+|less\s+than",
            re.IGNORECASE
        )

        upload_detected = False

        while True:
            await self._handle_duplicate_modal()

            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed > timeout_sec:
                logger.error(f"[{self.worker_name}|{batch_id}] Upload timeout setelah {elapsed:.1f}s.")
                return False

            try:
                # 1. Cek langsung teks penyelesaian upload di layar (seperti "10 upload selesai")
                comp_loc = self.page.get_by_text(completion_pattern)
                comp_count = await comp_loc.count()
                for i in range(comp_count):
                    el = comp_loc.nth(i)
                    if await el.is_visible():
                        match_text = (await el.inner_text()).strip().replace("\n", " ")
                        logger.info(f"[{self.worker_name}|{batch_id}] Upload selesai terdeteksi via teks ('{match_text}') dalam {elapsed:.1f}s.")
                        return True

                # 2. Cek apakah ada aktivitas upload yang sedang berjalan (indikator aktif)
                active_uploading = False
                upload_text_loc = self.page.get_by_text(uploading_pattern)
                u_count = await upload_text_loc.count()
                for i in range(u_count):
                    if await upload_text_loc.nth(i).is_visible():
                        active_uploading = True
                        break

                # Progress bar & tombol cancel aktif (hanya yang visible)
                visible_bars = await self.page.locator("[role='progressbar']:visible").count()
                cancel_btns = await self.page.locator(
                    "button[aria-label*='Batalkan']:visible, button[aria-label*='Cancel']:visible"
                ).count()

                if active_uploading or visible_bars > 0 or cancel_btns > 0:
                    upload_detected = True

                # 3. Cek tombol Retry jika Drive mengalami error upload
                error_elem = self.page.locator("button:has-text('Retry'):visible, button:has-text('Coba lagi'):visible")
                if await error_elem.count() > 0:
                    logger.warning(f"[{self.worker_name}|{batch_id}] Error upload terdeteksi pada tombol Retry, mencoba klik...")
                    try:
                        await error_elem.first.click()
                    except Exception:
                        pass

                # 4. Fallback: jika upload pernah aktif atau sudah berlalu >= 8 detik,
                # dan sekarang tidak ada progress bar, tidak ada tombol cancel, tidak ada teks uploading aktif
                if (upload_detected or elapsed >= 8) and not active_uploading and visible_bars == 0 and cancel_btns == 0:
                    # Tunggu sejenak untuk memastikan bukan jeda render
                    await asyncio.sleep(2)
                    v_bars_after = await self.page.locator("[role='progressbar']:visible").count()
                    if v_bars_after == 0:
                        logger.info(f"[{self.worker_name}|{batch_id}] Upload selesai — tidak ada aktivitas upload aktif tersisa ({elapsed:.1f}s).")
                        return True

            except Exception as e:
                logger.debug(f"[{self.worker_name}|{batch_id}] Polling error: {e}")

            await asyncio.sleep(2)
