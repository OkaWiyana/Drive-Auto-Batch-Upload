import os
from pathlib import Path
from loguru import logger
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from src.core.config import config

class FileEventHandler(FileSystemEventHandler):
    """Watches for new files matching the configured extensions and triggers callback."""
    def __init__(self, callback, extensions: set[str]):
        super().__init__()
        self.callback = callback
        self.extensions = extensions

    def on_created(self, event):
        if not event.is_directory:
            path = Path(event.src_path)
            if not self.extensions or path.suffix.lower() in self.extensions:
                # Give the OS a tiny fraction of a second to release any write lock
                try:
                    if path.exists() and path.stat().st_size > 0:
                        logger.info(f"New file detected: {path}")
                        self.callback([path])
                except Exception as e:
                    logger.debug(f"Could not stat new file {path}: {e}")

class DirectoryScanner:
    def __init__(self, callback):
        """
        Args:
            callback: Function(files: list[Path]) called when files are found.
        """
        self.callback = callback
        self.observer = None
        self.extensions = config.get_file_extensions()

    def scan_existing(self):
        """Scan all configured folders for existing files."""
        folders = config.get_target_folders()
        files = []
        for folder in folders:
            if not folder.exists():
                continue
            logger.info(f"Scanning files in {folder}...")
            for root, _, filenames in os.walk(folder):
                for filename in filenames:
                    path = Path(root) / filename
                    if not self.extensions or path.suffix.lower() in self.extensions:
                        files.append(path)

        if files:
            logger.info(f"Found {len(files)} existing file(s) across {len(folders)} folder(s).")
            self.callback(files)
        else:
            logger.info("No matching files found.")

    def start_watching(self):
        """Start filesystem watcher for configured folders."""
        folders = config.get_target_folders()
        self.observer = Observer()
        handler = FileEventHandler(self.callback, self.extensions)
        started_any = False
        for folder in folders:
            if folder.exists():
                self.observer.schedule(handler, str(folder), recursive=True)
                logger.info(f"Started folder watcher on {folder}")
                started_any = True
        if started_any:
            self.observer.start()

    def stop_watching(self):
        if self.observer:
            try:
                self.observer.stop()
                self.observer.join(timeout=2.0)
            except Exception as e:
                logger.debug(f"Error stopping observer: {e}")
            logger.info("Stopped folder watcher.")
