"""
GDrive Auto Uploader GUI
Modern desktop interface for parallel multi-tab batch uploading to Google Drive.
"""
import os
import sys
import json
import time
import subprocess
import threading
from pathlib import Path
from datetime import datetime

import customtkinter as ctk
from tkinter import filedialog, messagebox
from PIL import Image

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

if getattr(sys, 'frozen', False):
    BUNDLE_DIR = Path(sys._MEIPASS)
    DATA_DIR = Path(sys.executable).parent
else:
    BUNDLE_DIR = Path(__file__).resolve().parent.parent.parent
    DATA_DIR = BUNDLE_DIR

ENV_FILE = DATA_DIR / ".env"
STATE_FILE = DATA_DIR / "state.json"
PROFILE_DIR = DATA_DIR / "gdrive_profile"

# ─── Colors (Modern GDrive Aesthetic) ─────────────────────────────────────────
BG_MAIN       = "#0f111a"   # Deep slate background
BG_CARD       = "#161926"   # Slightly lighter card surface
BG_ENTRY      = "#1f2438"   # Field entry background
BORDER_COLOR  = "#2a314d"   # Clean borders
ACCENT_BLUE   = "#4285F4"   # Google Blue
ACCENT_GREEN  = "#34A853"   # Google Green
ACCENT_YELLOW = "#FBBC05"   # Google Yellow
ACCENT_RED    = "#EA4335"   # Google Red
TEXT_MAIN     = "#F8FAFC"   # Crisp white
TEXT_MUTED    = "#94A3B8"   # Slate dim

def load_env() -> dict:
    env = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                env[k.strip()] = v.strip()
    return env

def save_env(values: dict):
    lines = [f"{k}={v}" for k, v in values.items() if v]
    ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")

def load_state() -> dict:
    if not STATE_FILE.exists():
        return {"batches": {}}
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"batches": {}}

class GDriveLauncher(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("GDrive Auto Uploader - Multi-Tab Batch Worker")
        self.geometry("980x760")
        self.minsize(860, 680)
        self.configure(fg_color=BG_MAIN)

        self._process: subprocess.Popen | None = None
        self._log_thread: threading.Thread | None = None
        self._running = False
        self._start_time = None

        # Load Logo if present
        self.logo_ctk = None
        logo_path = BUNDLE_DIR / "public" / "LogoAI.png"
        if logo_path.exists():
            try:
                img = Image.open(logo_path)
                self.logo_ctk = ctk.CTkImage(light_image=img, dark_image=img, size=(42, 42))
            except Exception:
                pass

        self._setup_ui()
        self._load_saved_settings()
        self._check_login_status()
        self._poll_status()

    def _setup_ui(self):
        # ── Header ────────────────────────────────────────────────────────────
        header_frame = ctk.CTkFrame(self, fg_color=BG_CARD, corner_radius=0, height=75)
        header_frame.pack(fill="x", side="top")
        header_frame.pack_propagate(False)

        header_inner = ctk.CTkFrame(header_frame, fg_color="transparent")
        header_inner.pack(fill="both", expand=True, padx=20, pady=10)

        title_box = ctk.CTkFrame(header_inner, fg_color="transparent")
        title_box.pack(side="left")

        if self.logo_ctk:
            logo_lbl = ctk.CTkLabel(title_box, image=self.logo_ctk, text="")
            logo_lbl.pack(side="left", padx=(0, 12))

        text_box = ctk.CTkFrame(title_box, fg_color="transparent")
        text_box.pack(side="left")

        title_lbl = ctk.CTkLabel(
            text_box,
            text="GDrive Auto Uploader",
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color=TEXT_MAIN
        )
        title_lbl.pack(anchor="w")

        sub_lbl = ctk.CTkLabel(
            text_box,
            text="Unggah massal paralel multi-tab ke 1 folder Google Drive tanpa macet",
            font=ctk.CTkFont(size=12),
            text_color=TEXT_MUTED
        )
        sub_lbl.pack(anchor="w")

        # Status badge & timer
        self.status_badge = ctk.CTkLabel(
            header_inner,
            text="STATUS: SIAP",
            fg_color="#1e293b",
            text_color=TEXT_MAIN,
            corner_radius=8,
            font=ctk.CTkFont(size=12, weight="bold"),
            padx=14,
            pady=6
        )
        self.status_badge.pack(side="right", pady=8)

        # ── Main Scrollable Container ─────────────────────────────────────────
        self.content_scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.content_scroll.pack(fill="both", expand=True, padx=20, pady=12)

        # ── Card 1: Akun & Sesi Google ────────────────────────────────────────
        auth_card = ctk.CTkFrame(self.content_scroll, fg_color=BG_CARD, corner_radius=10, border_color=BORDER_COLOR, border_width=1)
        auth_card.pack(fill="x", pady=(0, 12), padx=4)

        auth_inner = ctk.CTkFrame(auth_card, fg_color="transparent")
        auth_inner.pack(fill="x", padx=16, pady=14)

        ctk.CTkLabel(
            auth_inner,
            text="🔐 Autentikasi Akun Google",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=TEXT_MAIN
        ).pack(anchor="w", pady=(0, 6))

        auth_row = ctk.CTkFrame(auth_inner, fg_color="transparent")
        auth_row.pack(fill="x")

        self.login_status_lbl = ctk.CTkLabel(
            auth_row,
            text="Status Akun: Memeriksa...",
            font=ctk.CTkFont(size=12),
            text_color=TEXT_MUTED
        )
        self.login_status_lbl.pack(side="left")

        self.btn_login = ctk.CTkButton(
            auth_row,
            text="🔑 Buka Browser Login Google",
            command=self._open_browser_login,
            fg_color="#334155",
            hover_color="#475569",
            height=32,
            font=ctk.CTkFont(size=12, weight="bold")
        )
        self.btn_login.pack(side="right")

        # ── Card 2: Pengaturan Upload ──────────────────────────────────────────
        cfg_card = ctk.CTkFrame(self.content_scroll, fg_color=BG_CARD, corner_radius=10, border_color=BORDER_COLOR, border_width=1)
        cfg_card.pack(fill="x", pady=(0, 12), padx=4)

        cfg_inner = ctk.CTkFrame(cfg_card, fg_color="transparent")
        cfg_inner.pack(fill="x", padx=16, pady=14)

        ctk.CTkLabel(
            cfg_inner,
            text="⚙️ Parameter & Target Folder",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=TEXT_MAIN
        ).pack(anchor="w", pady=(0, 10))

        # Folder Target Lokal
        ctk.CTkLabel(cfg_inner, text="Folder Sumber di Komputer:", font=ctk.CTkFont(size=12), text_color=TEXT_MUTED).pack(anchor="w")
        folder_row = ctk.CTkFrame(cfg_inner, fg_color="transparent")
        folder_row.pack(fill="x", pady=(2, 10))

        self.entry_local_folder = ctk.CTkEntry(folder_row, fg_color=BG_ENTRY, border_color=BORDER_COLOR, placeholder_text="Pilih folder berisi file yang akan diunggah...")
        self.entry_local_folder.pack(side="left", fill="x", expand=True, padx=(0, 8))

        btn_browse = ctk.CTkButton(folder_row, text="Pilih Folder...", width=110, command=self._browse_folder, fg_color="#334155", hover_color="#475569")
        btn_browse.pack(side="right")

        # Link Folder Google Drive
        ctk.CTkLabel(cfg_inner, text="Tautan Folder Google Drive Tujuan (URL atau Folder ID):", font=ctk.CTkFont(size=12), text_color=TEXT_MUTED).pack(anchor="w")
        self.entry_drive_url = ctk.CTkEntry(cfg_inner, fg_color=BG_ENTRY, border_color=BORDER_COLOR, placeholder_text="Contoh: https://drive.google.com/drive/folders/1aBcDeFgHiJkLmNoPqRsTuVwXyZ...")
        self.entry_drive_url.pack(fill="x", pady=(2, 12))

        # Concurrency & Batch Settings in 2 columns
        grid_frame = ctk.CTkFrame(cfg_inner, fg_color="transparent")
        grid_frame.pack(fill="x")
        grid_frame.grid_columnconfigure((0, 1, 2), weight=1)

        # Col 0: Max Workers / Tabs
        col0 = ctk.CTkFrame(grid_frame, fg_color="transparent")
        col0.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        ctk.CTkLabel(col0, text="Jumlah Tab Paralel (Workers):", font=ctk.CTkFont(size=12), text_color=TEXT_MUTED).pack(anchor="w")
        self.opt_workers = ctk.CTkOptionMenu(col0, values=["1 Tab", "2 Tab", "3 Tab", "5 Tab", "8 Tab", "10 Tab"], fg_color=BG_ENTRY, button_color="#334155")
        self.opt_workers.pack(fill="x", pady=4)
        self.opt_workers.set("3 Tab")

        # Col 1: Batch Size
        col1 = ctk.CTkFrame(grid_frame, fg_color="transparent")
        col1.grid(row=0, column=1, sticky="ew", padx=(0, 8))
        ctk.CTkLabel(col1, text="Ukuran Batch (File per Tab):", font=ctk.CTkFont(size=12), text_color=TEXT_MUTED).pack(anchor="w")
        self.opt_batch_size = ctk.CTkOptionMenu(col1, values=["10 File", "25 File", "50 File", "100 File", "200 File"], fg_color=BG_ENTRY, button_color="#334155")
        self.opt_batch_size.pack(fill="x", pady=4)
        self.opt_batch_size.set("50 File")

        # Col 2: Duplicate Handling
        col2 = ctk.CTkFrame(grid_frame, fg_color="transparent")
        col2.grid(row=0, column=2, sticky="ew")
        ctk.CTkLabel(col2, text="Jika File Sudah Ada:", font=ctk.CTkFont(size=12), text_color=TEXT_MUTED).pack(anchor="w")
        self.opt_duplicates = ctk.CTkOptionMenu(col2, values=["Simpan Keduanya", "Ganti File Lama"], fg_color=BG_ENTRY, button_color="#334155")
        self.opt_duplicates.pack(fill="x", pady=4)
        self.opt_duplicates.set("Simpan Keduanya")

        # ── Card 3: Statistik Progress ─────────────────────────────────────────
        stat_card = ctk.CTkFrame(self.content_scroll, fg_color=BG_CARD, corner_radius=10, border_color=BORDER_COLOR, border_width=1)
        stat_card.pack(fill="x", pady=(0, 12), padx=4)

        stat_inner = ctk.CTkFrame(stat_card, fg_color="transparent")
        stat_inner.pack(fill="x", padx=16, pady=14)

        ctk.CTkLabel(stat_inner, text="📊 Progress Antrean", font=ctk.CTkFont(size=14, weight="bold"), text_color=TEXT_MAIN).pack(anchor="w", pady=(0, 8))

        # Progress bar
        self.progress_bar = ctk.CTkProgressBar(stat_inner, fg_color=BG_ENTRY, progress_color=ACCENT_BLUE, height=12)
        self.progress_bar.pack(fill="x", pady=(0, 10))
        self.progress_bar.set(0)

        # Counter boxes
        stat_row = ctk.CTkFrame(stat_inner, fg_color="transparent")
        stat_row.pack(fill="x")
        stat_row.grid_columnconfigure((0, 1, 2, 3), weight=1)

        self.card_total_files = self._create_stat_pill(stat_row, 0, "Total File", "0", TEXT_MAIN)
        self.card_done_files  = self._create_stat_pill(stat_row, 1, "File Terupload", "0", ACCENT_GREEN)
        self.card_pending_b   = self._create_stat_pill(stat_row, 2, "Batch Pending", "0", ACCENT_YELLOW)
        self.card_failed_b    = self._create_stat_pill(stat_row, 3, "Batch Gagal", "0", ACCENT_RED)

        # ── Card 4: Tabview (Antrean & Log) ───────────────────────────────────
        tab_card = ctk.CTkFrame(self.content_scroll, fg_color=BG_CARD, corner_radius=10, border_color=BORDER_COLOR, border_width=1)
        tab_card.pack(fill="x", pady=(0, 12), padx=4)

        self.tabview = ctk.CTkTabview(tab_card, fg_color=BG_CARD, segmented_button_selected_color=ACCENT_BLUE)
        self.tabview.pack(fill="both", expand=True, padx=10, pady=8)

        tab_queue = self.tabview.add("Antrean Batch")
        tab_logs = self.tabview.add("Log Konsol Real-Time")

        # Queue list inside tab
        self.queue_scroll = ctk.CTkScrollableFrame(tab_queue, fg_color=BG_ENTRY, height=180)
        self.queue_scroll.pack(fill="both", expand=True)

        # Log textbox inside tab
        self.log_textbox = ctk.CTkTextbox(tab_logs, fg_color=BG_ENTRY, font=("Consolas", 11), height=180)
        self.log_textbox.pack(fill="both", expand=True)

        # ── Bottom Action Controls ────────────────────────────────────────────
        control_frame = ctk.CTkFrame(self, fg_color=BG_CARD, corner_radius=0, height=75)
        control_frame.pack(fill="x", side="bottom")
        control_frame.pack_propagate(False)

        ctrl_inner = ctk.CTkFrame(control_frame, fg_color="transparent")
        ctrl_inner.pack(fill="both", expand=True, padx=20, pady=12)

        self.btn_start = ctk.CTkButton(
            ctrl_inner,
            text="🚀 Mulai Upload",
            command=self._start_upload,
            fg_color=ACCENT_BLUE,
            hover_color="#3367d6",
            font=ctk.CTkFont(size=14, weight="bold"),
            height=42,
            width=160
        )
        self.btn_start.pack(side="left", padx=(0, 10))

        self.btn_stop = ctk.CTkButton(
            ctrl_inner,
            text="⏸️ Hentikan",
            command=self._stop_upload,
            state="disabled",
            fg_color="#ef4444",
            hover_color="#dc2626",
            font=ctk.CTkFont(size=14, weight="bold"),
            height=42,
            width=130
        )
        self.btn_stop.pack(side="left", padx=(0, 10))

        btn_reset = ctk.CTkButton(
            ctrl_inner,
            text="🔄 Reset Antrean",
            command=self._reset_queue,
            fg_color="#334155",
            hover_color="#475569",
            height=42,
            width=140
        )
        btn_reset.pack(side="left")

        btn_open_log = ctk.CTkButton(
            ctrl_inner,
            text="📁 Buka Folder Log",
            command=self._open_log_folder,
            fg_color="transparent",
            border_color=BORDER_COLOR,
            border_width=1,
            height=42
        )
        btn_open_log.pack(side="right")

    def _create_stat_pill(self, parent, col, title, initial_val, color):
        frame = ctk.CTkFrame(parent, fg_color=BG_ENTRY, corner_radius=8)
        frame.grid(row=0, column=col, sticky="ew", padx=4)
        ctk.CTkLabel(frame, text=title, font=ctk.CTkFont(size=11), text_color=TEXT_MUTED).pack(pady=(6, 0))
        val_lbl = ctk.CTkLabel(frame, text=initial_val, font=ctk.CTkFont(size=18, weight="bold"), text_color=color)
        val_lbl.pack(pady=(0, 6))
        return val_lbl

    def _browse_folder(self):
        folder = filedialog.askdirectory(title="Pilih Folder Berisi File")
        if folder:
            self.entry_local_folder.delete(0, "end")
            self.entry_local_folder.insert(0, folder)
            self._save_current_settings()

    def _open_log_folder(self):
        log_dir = DATA_DIR / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        os.startfile(str(log_dir))

    def _check_login_status(self):
        profile_path = DATA_DIR / "gdrive_profile"
        if profile_path.exists() and any(profile_path.glob("**/Cookies*")):
            self.login_status_lbl.configure(text="Status Akun: ✅ Profil Sesi Tersimpan", text_color=ACCENT_GREEN)
        else:
            self.login_status_lbl.configure(text="Status Akun: ⚠️ Belum Login (Klik tombol login di kanan)", text_color=ACCENT_YELLOW)

    def _open_browser_login(self):
        self._save_current_settings()
        self.login_status_lbl.configure(text="Membuka browser untuk login...", text_color=ACCENT_BLUE)
        def run_auth():
            cmd = [sys.executable, "-c", "import asyncio; from src.browser.auth_helper import AuthHelper; asyncio.run(AuthHelper.open_login_window())"]
            subprocess.call(cmd, cwd=str(DATA_DIR))
            self.after(500, self._check_login_status)
        threading.Thread(target=run_auth, daemon=True).start()

    def _save_current_settings(self):
        workers_val = int(self.opt_workers.get().split()[0])
        batch_val = int(self.opt_batch_size.get().split()[0])
        dup_val = "replace" if self.opt_duplicates.get() == "Ganti File Lama" else "keep_both"

        values = {
            "TARGET_FOLDERS": self.entry_local_folder.get().strip(),
            "GDRIVE_FOLDER_URL": self.entry_drive_url.get().strip(),
            "MAX_WORKERS": str(workers_val),
            "BATCH_SIZE": str(batch_val),
            "DUPLICATE_ACTION": dup_val
        }
        save_env(values)

    def _load_saved_settings(self):
        env = load_env()
        if "TARGET_FOLDERS" in env:
            self.entry_local_folder.insert(0, env["TARGET_FOLDERS"])
        if "GDRIVE_FOLDER_URL" in env:
            self.entry_drive_url.insert(0, env["GDRIVE_FOLDER_URL"])
        if "MAX_WORKERS" in env:
            self.opt_workers.set(f"{env['MAX_WORKERS']} Tab")
        if "BATCH_SIZE" in env:
            self.opt_batch_size.set(f"{env['BATCH_SIZE']} File")
        if "DUPLICATE_ACTION" in env:
            self.opt_duplicates.set("Ganti File Lama" if env["DUPLICATE_ACTION"] == "replace" else "Simpan Keduanya")

    def _start_upload(self):
        self._save_current_settings()

        local_dir = self.entry_local_folder.get().strip()
        drive_url = self.entry_drive_url.get().strip()

        if not local_dir or not Path(local_dir).exists():
            messagebox.showerror("Folder Tidak Ditemukan", "Silakan pilih folder sumber di komputer Anda.")
            return

        if not drive_url:
            messagebox.showerror("URL Drive Kosong", "Silakan masukkan tautan folder Google Drive tujuan.")
            return

        self._running = True
        self._start_time = time.time()
        self.btn_start.configure(state="disabled")
        self.btn_stop.configure(state="normal")
        self.status_badge.configure(text="STATUS: BERJALAN (00:00:00)", fg_color="#1e3a8a", text_color=TEXT_MAIN)

        self._append_log("🚀 Memulai background upload agent...\n")

        def run_worker():
            cmd = [sys.executable, "agent_worker.py"]
            self._process = subprocess.Popen(
                cmd,
                cwd=str(DATA_DIR),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                encoding="utf-8",
                errors="replace"
            )

            for line in iter(self._process.stdout.readline, ''):
                if not line:
                    break
                self._append_log(line)

            self._process.stdout.close()
            self._process.wait()
            self._running = False
            self.after(0, self._on_worker_finished)

        self._log_thread = threading.Thread(target=run_worker, daemon=True)
        self._log_thread.start()

    def _stop_upload(self):
        if self._process and self._process.poll() is None:
            self._append_log("\n⚠️ Menghentikan agent...\n")
            self._process.terminate()
            try:
                self._process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self._process.kill()
        self._running = False
        self._on_worker_finished()

    def _on_worker_finished(self):
        self.btn_start.configure(state="normal")
        self.btn_stop.configure(state="disabled")
        self.status_badge.configure(text="STATUS: BERHENTI", fg_color="#334155")
        self._append_log("⏹️ Agent selesai atau dihentikan.\n")

    def _reset_queue(self):
        if messagebox.askyesno("Reset Antrean", "Apakah Anda yakin ingin mengosongkan antrean upload?"):
            if STATE_FILE.exists():
                STATE_FILE.unlink()
            self._append_log("🔄 Antrean telah direset.\n")
            self._update_queue_ui()

    def _append_log(self, text: str):
        def _insert():
            self.log_textbox.insert("end", text)
            self.log_textbox.see("end")
        self.after(0, _insert)

    def _poll_status(self):
        # Update running timer
        if self._running and self._start_time:
            elapsed = int(time.time() - self._start_time)
            hrs, rem = divmod(elapsed, 3600)
            mins, secs = divmod(rem, 60)
            self.status_badge.configure(text=f"STATUS: BERJALAN ({hrs:02d}:{mins:02d}:{secs:02d})")

        self._update_queue_ui()
        self.after(1500, self._poll_status)

    def _update_queue_ui(self):
        state = load_state()
        batches = state.get("batches", {})

        total_files = sum(len(b.get("files", [])) for b in batches.values())
        done_files = sum(len(b.get("files", [])) for b in batches.values() if b.get("status") == "completed")
        pending_b = sum(1 for b in batches.values() if b.get("status") in ["pending", "retrying", "processing"])
        failed_b = sum(1 for b in batches.values() if b.get("status") == "failed")

        self.card_total_files.configure(text=str(total_files))
        self.card_done_files.configure(text=str(done_files))
        self.card_pending_b.configure(text=str(pending_b))
        self.card_failed_b.configure(text=str(failed_b))

        pct = (done_files / total_files) if total_files > 0 else 0
        self.progress_bar.set(pct)

        # Re-render queue items if tab is visible
        if self.tabview.get() == "Antrean Batch":
            for child in self.queue_scroll.winfo_children():
                child.destroy()

            if not batches:
                ctk.CTkLabel(self.queue_scroll, text="Belum ada antrean batch.", text_color=TEXT_MUTED).pack(pady=10)
            else:
                for b_id, b in list(batches.items())[:40]:  # limit to top 40 for responsiveness
                    row = ctk.CTkFrame(self.queue_scroll, fg_color=BG_CARD, corner_radius=6)
                    row.pack(fill="x", pady=2, padx=4)

                    status = b.get("status", "pending")
                    st_color = ACCENT_GREEN if status == "completed" else (ACCENT_YELLOW if status == "processing" else (ACCENT_RED if status == "failed" else TEXT_MUTED))

                    ctk.CTkLabel(row, text=f"📦 {b_id}", font=ctk.CTkFont(size=11, weight="bold"), text_color=TEXT_MAIN).pack(side="left", padx=8)
                    ctk.CTkLabel(row, text=f"{len(b.get('files', []))} File", font=ctk.CTkFont(size=11), text_color=TEXT_MUTED).pack(side="left", padx=8)

                    badge = ctk.CTkLabel(row, text=status.upper(), text_color=st_color, font=ctk.CTkFont(size=10, weight="bold"))
                    badge.pack(side="right", padx=8)

    def on_close(self):
        if self._running:
            self._stop_upload()
        self.destroy()

if __name__ == "__main__":
    app = GDriveLauncher()
    app.protocol("WM_DELETE_WINDOW", app.on_close)
    app.mainloop()
