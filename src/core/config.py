import os
import sys
import re
from pathlib import Path
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    if getattr(sys, 'frozen', False):
        BUNDLE_DIR: Path = Path(sys._MEIPASS)
        DATA_DIR: Path = Path(sys.executable).parent
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(DATA_DIR / "browsers")
    else:
        BUNDLE_DIR: Path = Path(__file__).resolve().parent.parent.parent
        DATA_DIR: Path = BUNDLE_DIR

    # Target local folders to scan (comma separated)
    TARGET_FOLDERS: str = str(DATA_DIR / "files_to_upload")
    
    # Target Google Drive URL or Folder ID
    GDRIVE_FOLDER_URL: str = ""
    
    # Storage and logs
    LOG_DIR: Path = DATA_DIR / "logs"
    STATE_FILE: Path = DATA_DIR / "state.json"
    USER_DATA_DIR: Path = DATA_DIR / "gdrive_profile"

    # Concurrency and batching
    BATCH_SIZE: int = 50
    MAX_WORKERS: int = 3
    MIN_WORKERS: int = 1
    
    # Retry policy
    RETRY_LIMIT: int = 3
    RETRY_DELAY_SECONDS: int = 10
    
    # File filter (comma separated, empty for all files)
    FILE_EXTENSIONS: str = ""
    
    # Browser settings
    BROWSER_CHANNEL: str = "chrome"  # 'chrome', 'msedge', or 'chromium'
    HEADLESS: bool = False
    
    # Conflict resolution in Drive: 'keep_both' or 'replace'
    DUPLICATE_ACTION: str = "keep_both"

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
        # If user passed just the folder ID
        if re.match(r'^[a-zA-Z0-9_-]{25,}$', raw):
            return f"https://drive.google.com/drive/folders/{raw}"
        # If user passed a full link, normalize it
        return raw

    class Config:
        env_file = ".env"
        extra = "ignore"

config = Settings()

# Ensure directories exist
config.LOG_DIR.mkdir(parents=True, exist_ok=True)
config.USER_DATA_DIR.mkdir(parents=True, exist_ok=True)
for folder in config.get_target_folders():
    folder.mkdir(parents=True, exist_ok=True)
