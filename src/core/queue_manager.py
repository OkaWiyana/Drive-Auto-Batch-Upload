import json
import uuid
import threading
from pathlib import Path
from datetime import datetime
from loguru import logger

from src.core.config import config

class QueueManager:
    def __init__(self):
        self.state_file = config.STATE_FILE
        self.lock = threading.Lock()
        self._ensure_state_file()
        self._reset_zombie_batches()

    def _reset_zombie_batches(self):
        """If the app crashed or restarted, reset processing/retrying batches to pending."""
        with self.lock:
            state = self._load_state()
            zombies_fixed = 0
            for batch in state["batches"].values():
                if batch.get("status") in ["processing", "retrying"]:
                    batch["status"] = "pending"
                    zombies_fixed += 1
            if zombies_fixed > 0:
                self._save_state(state)
                logger.info(f"Reset {zombies_fixed} unfinished batch(es) to pending.")

    def _ensure_state_file(self):
        if not self.state_file.exists():
            with open(self.state_file, 'w', encoding="utf-8") as f:
                json.dump({
                    "created_at": datetime.now().isoformat(),
                    "batches": {}
                }, f, indent=2)

    def _load_state(self) -> dict:
        try:
            with open(self.state_file, 'r', encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {"batches": {}}

    def _save_state(self, state: dict):
        with open(self.state_file, 'w', encoding="utf-8") as f:
            json.dump(state, f, indent=2)

    def add_files(self, files: list[Path]):
        """Add files to the queue, chunking them into batches."""
        if not files:
            return

        batch_size = max(1, config.BATCH_SIZE)

        with self.lock:
            state = self._load_state()
            if "batches" not in state:
                state["batches"] = {}

            # Gather all existing files to prevent duplicates
            existing_files = set()
            for b in state["batches"].values():
                existing_files.update(b.get("files", []))

            # Filter out files already queued
            new_files_str = [str(p.resolve()) for p in files if str(p.resolve()) not in existing_files]
            if not new_files_str:
                return

            # Check if there is an existing pending batch with space
            last_pending_id = None
            for b_id, b in state["batches"].items():
                if b.get("status") == "pending" and len(b.get("files", [])) < batch_size:
                    last_pending_id = b_id
                    break

            files_to_assign = new_files_str
            if last_pending_id:
                space = batch_size - len(state["batches"][last_pending_id]["files"])
                state["batches"][last_pending_id]["files"].extend(files_to_assign[:space])
                files_to_assign = files_to_assign[space:]

            # Chunk remaining files into new batches
            for i in range(0, len(files_to_assign), batch_size):
                chunk = files_to_assign[i:i + batch_size]
                b_id = f"batch_{uuid.uuid4().hex[:8]}"
                state["batches"][b_id] = {
                    "id": b_id,
                    "status": "pending",
                    "files": chunk,
                    "retry_count": 0,
                    "worker_id": None,
                    "error_message": None,
                    "created_at": datetime.now().isoformat(),
                    "completed_at": None
                }

            self._save_state(state)
            logger.info(f"Added {len(new_files_str)} files across batches. Total batches: {len(state['batches'])}")

    def get_next_batch(self, worker_id: str = None) -> dict | None:
        """Find next batch: prioritize retries over pending batches."""
        with self.lock:
            state = self._load_state()
            batches = state.get("batches", {})

            # 1. Retrying batches first
            for b_id, b in batches.items():
                if b.get("status") == "retrying":
                    b["status"] = "processing"
                    b["worker_id"] = worker_id
                    self._save_state(state)
                    return b

            # 2. Pending batches
            for b_id, b in batches.items():
                if b.get("status") == "pending":
                    b["status"] = "processing"
                    b["worker_id"] = worker_id
                    self._save_state(state)
                    return b

            return None

    def mark_completed(self, batch_id: str):
        with self.lock:
            state = self._load_state()
            if batch_id in state.get("batches", {}):
                state["batches"][batch_id]["status"] = "completed"
                state["batches"][batch_id]["completed_at"] = datetime.now().isoformat()
                state["batches"][batch_id]["error_message"] = None
                self._save_state(state)
                logger.info(f"[{batch_id}] Marked as COMPLETED.")

    def mark_failed(self, batch_id: str, error_msg: str):
        with self.lock:
            state = self._load_state()
            if batch_id in state.get("batches", {}):
                b = state["batches"][batch_id]
                b["retry_count"] = b.get("retry_count", 0) + 1
                b["error_message"] = str(error_msg)[:300]

                if b["retry_count"] >= config.RETRY_LIMIT:
                    b["status"] = "failed"
                    logger.error(f"[{batch_id}] Exceeded retry limit ({config.RETRY_LIMIT}). Marked as FAILED.")
                else:
                    b["status"] = "retrying"
                    logger.warning(f"[{batch_id}] Retry attempt {b['retry_count']}/{config.RETRY_LIMIT}. Queued for retry.")

                self._save_state(state)

    def reset_queue(self):
        """Clears all batches."""
        with self.lock:
            self._save_state({"created_at": datetime.now().isoformat(), "batches": {}})
            logger.info("Queue has been completely reset.")

    def get_statistics(self) -> dict:
        """Calculate counts for GUI status cards."""
        with self.lock:
            state = self._load_state()
            batches = state.get("batches", {})
            total_files = sum(len(b.get("files", [])) for b in batches.values())
            completed_files = sum(len(b.get("files", [])) for b in batches.values() if b.get("status") == "completed")
            
            pending_count = sum(1 for b in batches.values() if b.get("status") in ["pending", "retrying"])
            processing_count = sum(1 for b in batches.values() if b.get("status") == "processing")
            completed_count = sum(1 for b in batches.values() if b.get("status") == "completed")
            failed_count = sum(1 for b in batches.values() if b.get("status") == "failed")

            return {
                "total_batches": len(batches),
                "pending_batches": pending_count,
                "processing_batches": processing_count,
                "completed_batches": completed_count,
                "failed_batches": failed_count,
                "total_files": total_files,
                "completed_files": completed_files
            }
