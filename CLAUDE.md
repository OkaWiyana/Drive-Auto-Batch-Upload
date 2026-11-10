# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

GDrive Auto Uploader is a Python desktop application and headless worker that uploads large volumes of local files to a single Google Drive folder in parallel batches across multiple browser tabs (Playwright persistent context) without relying on Google Drive API quotas.

## Development & Execution Commands

### Environment Setup
```bash
# Install dependencies
pip install -r requirements.txt

# Install Playwright browser binaries (if not using installed Chrome or Edge)
playwright install chromium
```

### Running the Application
```bash
# Launch GUI (CustomTkinter desktop interface)
python run.py
# Alternatively on Windows:
start.bat

# Run background upload agent directly (CLI / headless mode)
python run.py --run-agent
# or
python agent_worker.py

# Launch standalone Google authentication window to save browser profile
python -m src.browser.auth_helper
```

### Testing & Code Quality
```bash
# Run tests (when test files are added)
python -m unittest discover -s tests
pytest

# Syntax/type check if tools are installed
python -m py_compile run.py agent_worker.py src/**/*.py
```

## Architecture & System Design

### Execution Flow & Process Separation
- **GUI Mode (`run.py` -> `src.ui.app.GDriveLauncher`)**: A CustomTkinter interface. It does not run Playwright directly in the UI thread; instead, it saves config to `.env`, executes `agent_worker.py` as a `subprocess.Popen` child process, streams stdout/stderr to a live log console, and polls `state.json` every 1.5 seconds to refresh progress bars and batch tables.
- **Worker Process (`agent_worker.py` / `run.py --run-agent`)**: The core automation pipeline. It initializes `QueueManager`, `BrowserPool`, `DirectoryScanner`, and `Scheduler`. Runs on `asyncio` (specifically using `WindowsProactorEventLoopPolicy` on Windows).

### Component Architecture
1. **Configuration (`src/core/config.py`)**:
   - Uses `pydantic-settings.BaseSettings` reading from `.env`.
   - Supports bundled execution via PyInstaller (`sys.frozen` flag sets `DATA_DIR` and `PLAYWRIGHT_BROWSERS_PATH`).
   - Normalizes Google Drive links (`get_clean_folder_url` handles either bare 25+ char folder IDs or full URLs).

2. **Queue Management & State Persistence (`src/core/queue_manager.py`)**:
   - Manages all batch states in `state.json` behind a thread lock.
   - **Zombie Recovery**: On startup, any batch left in `processing` or `retrying` status is automatically reset to `pending`.
   - **Deduplication & Chunking**: Discovered files are checked against all existing batches in `state.json` before being chunked into batches of `BATCH_SIZE`.
   - **Batch Lifecycle**: `pending` -> `processing` -> `completed` or `retrying` (incremented until `RETRY_LIMIT` is reached) -> `failed`. Retrying batches are prioritized over pending batches.

3. **File Discovery & Watching (`src/core/scanner.py`)**:
   - `DirectoryScanner` scans directories in `TARGET_FOLDERS` on startup and optionally runs a `watchdog.observers.Observer` to capture new matching files as they are written to disk.

4. **Browser Tab Pool (`src/browser/browser_pool.py`)**:
   - Launches a single Playwright `launch_persistent_context` referencing `config.USER_DATA_DIR` (`gdrive_profile/`). This preserves Google cookies, avoiding repeated logins and bot checkpoints.
   - Attempts browser launch via channel preference: `config.BROWSER_CHANNEL` (defaults to `"chrome"`), falling back to `"msedge"` then bundled chromium.
   - Pre-allocates `MAX_WORKERS` tabs (`Page` objects) into an `asyncio.Queue`. Automatically detects crashed or closed tabs and respawns replacement pages when released.

5. **DOM Automation & Upload Logic (`src/browser/gdrive_uploader.py`)**:
   - Interacts with Google Drive's web interface per tab.
   - 3-tier file upload trigger:
     1. UI navigation: clicks `+ New` / `+ Baru` -> `File upload` menu item -> captures file chooser via `page.expect_file_chooser()`.
     2. Direct input fallback: targets `input[type='file']`.
     3. Drop target fallback: clicks `div[role='main']` expecting file chooser.
   - Automatically detects and dismisses Google Drive duplicate file dialogs based on `config.DUPLICATE_ACTION` (`keep_both` vs `replace`).
   - Polls Drive's upload notification tray / progress indicators for completion or failure retries.

6. **Parallel Scheduler (`src/core/scheduler.py`)**:
   - The coordinator loop: when active worker count < `MAX_WORKERS`, pulls the next batch from `QueueManager`, acquires an available tab from `BrowserPool`, spawns an `_worker` async task, and marks batch completion or failure upon return.

### Key Data Paths & Files
- `state.json`: Master state store for queue progress, file lists, retry counts, and errors.
- `gdrive_profile/`: Persistent Chromium user profile directory containing login sessions and authentication cookies.
- `.env`: Local configuration overrides (`TARGET_FOLDERS`, `GDRIVE_FOLDER_URL`, `MAX_WORKERS`, `BATCH_SIZE`, `DUPLICATE_ACTION`).
- `logs/gdrive_agent.log`: Loguru rolling file logs (10 MB rotation, 7 days retention).
