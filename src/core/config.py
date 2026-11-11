import os
import sys
import re
from pathlib import Path

class Settings:
    def __init__(self):
        if getattr(sys, 'frozen', False):
            self.BUNDLE_DIR: Path = Path(sys._MEIPASS)
            self.DATA_DIR: Path = Path(sys.executable).parent
            os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(self.DATA_DIR / "browsers")
        else:
            self.BUNDLE_DIR: Path = Path(__file__).resolve().parent.parent.parent
            self.DATA_DIR: Path = self.BUNDLE_DIR

        # Target local folders to scan (comma separated)
        self.TARGET_FOLDERS: str = str(self.DATA_DIR / "files_to_upload")
        
        # Target Google Drive URL or Folder ID
        self.GDRIVE_FOLDER_URL: str = ""
        
        # Storage and logs
        self.LOG_DIR: Path = self.DATA_DIR / "logs"
        self.STATE_FILE: Path = self.DATA_DIR / "state.json"
        self.USER_DATA_DIR: Path = self.DATA_DIR / "gdrive_profile"

        # Concurrency and batching
        self.BATCH_SIZE: int = 50
        self.MAX_WORKERS: int = 3

        # Retry policy
        self.RETRY_LIMIT: int = 3
        self.RETRY_DELAY_SECONDS: int = 10
        self.ZOMBIE_RECOVERY: bool = True

        # File filter (comma separated, empty for all files)
        self.FILE_EXTENSIONS: str = ""

        # Browser settings
        self.BROWSER_CHANNEL: str = "chrome"  # 'chrome', 'msedge', or 'chromium'
        self.HEADLESS: bool = False
        self.WATCHDOG_ENABLED: bool = True
        
        # Conflict resolution in Drive: 'keep_both' or 'replace'
        self.DUPLICATE_ACTION: str = "keep_both"

        self._load_env()

    def _load_env(self):
        env_file = self.DATA_DIR / ".env"
        env_vars = {}
        if env_file.exists():
            for line in env_file.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, _, v = line.partition("=")
                    env_vars[k.strip()] = v.strip()

        # Update attributes from .env
        for k, v in env_vars.items():
            if hasattr(self, k):
                cur = getattr(self, k)
                if isinstance(cur, bool):
                    setattr(self, k, v.lower() in ("true", "1", "yes"))
                elif isinstance(cur, int):
                    try:
                        setattr(self, k, int(v))
                    except ValueError:
                        pass
                elif isinstance(cur, Path):
                    setattr(self, k, Path(v))
                else:
                    setattr(self, k, v)

    def get_target_folders(self) -> list[Path]:
        return [Path(p.strip()) for p in self.TARGET_FOLDERS.split(",") if p.strip()]

    def get_file_extensions(self) -> set[str]:
        if not self.FILE_EXTENSIONS.strip():
            return set()
        return {ext.strip().lower() if ext.strip().startswith(".") else f".{ext.strip().lower()}" 
                for ext in self.FILE_EXTENSIONS.split(",") if ext.strip()}

    def get_clean_folder_url(self) -> str:
        """Ensure Google Drive folder URL is well-formed."""
        raw = self.GDRIVE_FOLDER_URL.strip()
        if not raw:
            return ""
        if re.match(r'^[a-zA-Z0-9_-]{25,}$', raw):
            return f"https://drive.google.com/drive/folders/{raw}"
        return raw

config = Settings()

# Ensure directories exist
config.LOG_DIR.mkdir(parents=True, exist_ok=True)
config.USER_DATA_DIR.mkdir(parents=True, exist_ok=True)
for folder in config.get_target_folders():
    try:
        folder.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
