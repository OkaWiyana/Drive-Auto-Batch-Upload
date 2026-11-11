import asyncio
from loguru import logger

from src.core.config import config
from src.core.queue_manager import QueueManager
from src.browser.browser_pool import BrowserPool
from src.browser.gdrive_uploader import GDriveUploader

class Scheduler:
    def __init__(self, queue_manager: QueueManager, browser_pool: BrowserPool):
        self.queue_manager = queue_manager
        self.browser_pool = browser_pool
        self.active_workers = 0
        self.is_running = False
        self.worker_freed_event = asyncio.Event()
        self._next_worker_num = 1

    async def _worker(self, batch: dict, worker_id: int):
        page = None
        worker_name = f"Tab-{worker_id}"

        try:
            page = await self.browser_pool.get_page()
            uploader = GDriveUploader(page, worker_name=worker_name)
            success = await uploader.upload_batch(batch)

            if success:
                self.queue_manager.mark_completed(batch["id"])
            else:
                self.queue_manager.mark_failed(batch["id"], "Upload batch gagal atau timeout.")

        except Exception as e:
            err_msg = str(e)
            logger.error(f"[{worker_name}] Exception pada batch {batch['id']}: {err_msg}")
            self.queue_manager.mark_failed(batch["id"], err_msg)
        finally:
            if page:
                await self.browser_pool.release_page(page)
            self.active_workers -= 1
            self.worker_freed_event.set()

    async def run(self):
        logger.info(f"Upload Scheduler loop aktif. Max worker tab: {config.MAX_WORKERS}")
        self.is_running = True
        empty_cycles = 0

        while self.is_running:
            spawned = False

            if self.active_workers < config.MAX_WORKERS:
                worker_id = (self._next_worker_num % config.MAX_WORKERS) + 1
                self._next_worker_num += 1

                batch = self.queue_manager.get_next_batch(worker_id=f"tab_{worker_id}")
                if batch:
                    self.active_workers += 1  # increment before create_task so the loop doesn't over-spawn
                    asyncio.create_task(self._worker(batch, worker_id))
                    spawned = True
                    empty_cycles = 0

            if spawned:
                await asyncio.sleep(0.1)
            elif self.active_workers > 0:
                self.worker_freed_event.clear()
                try:
                    await asyncio.wait_for(self.worker_freed_event.wait(), timeout=1.0)
                except asyncio.TimeoutError:
                    pass
            else:
                # No active workers and no batch was spawned. Check if queue is finished.
                stats = self.queue_manager.get_statistics()
                if stats["total_batches"] > 0 and stats["pending_batches"] == 0 and stats["processing_batches"] == 0:
                    # Brief verification pause to ensure all worker tasks and writes have settled
                    await asyncio.sleep(0.5)
                    stats = self.queue_manager.get_statistics()
                    if stats["pending_batches"] == 0 and stats["processing_batches"] == 0 and self.active_workers == 0:
                        logger.info(
                            f"Semua batch selesai diproses! ({stats['completed_batches']}/{stats['total_batches']} sukses, "
                            f"{stats['failed_batches']} gagal). Menghentikan scheduler..."
                        )
                        self.is_running = False
                        break
                elif stats["total_batches"] == 0:
                    empty_cycles += 1
                    if empty_cycles >= 5:
                        logger.info("Tidak ada berkas/batch dalam antrean. Menghentikan scheduler...")
                        self.is_running = False
                        break
                    await asyncio.sleep(1.0)
                else:
                    await asyncio.sleep(1.0)

    def stop(self):
        logger.info("Menghentikan Scheduler loop...")
        self.is_running = False
        self.worker_freed_event.set()
