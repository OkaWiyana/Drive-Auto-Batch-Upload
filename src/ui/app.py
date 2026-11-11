import os
import sys
import json
import time
import subprocess
import threading
import webbrowser
from pathlib import Path

import customtkinter as ctk
from tkinter import filedialog, messagebox
from PIL import Image

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

if getattr(sys, "frozen", False):
    BUNDLE_DIR = Path(sys._MEIPASS)
    DATA_DIR = Path(sys.executable).parent
else:
    BUNDLE_DIR = Path(__file__).resolve().parent.parent.parent
    DATA_DIR = BUNDLE_DIR

ENV_FILE = DATA_DIR / ".env"
STATE_FILE = DATA_DIR / "state.json"
PROFILE_DIR = DATA_DIR / "gdrive_profile"
LOG_DIR = DATA_DIR / "logs"

BG_MAIN = "#0B0F19"
BG_NAV = "#111827"
BG_CARD = "#151D2E"
BG_CARD_ALT = "#1E293B"
BG_INPUT = "#0F172A"
BORDER_COLOR = "#243247"
BORDER_SUBTLE = "#1E293B"

ACCENT_BLUE = "#2563EB"
ACCENT_BLUE_HOVER = "#1D4ED8"
ACCENT_GREEN = "#10B981"
ACCENT_AMBER = "#F59E0B"
ACCENT_RED = "#EF4444"

TEXT_MAIN = "#F8FAFC"
TEXT_MUTED = "#94A3B8"
TEXT_DIM = "#64748B"


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
    lines = [f"{k}={v}" for k, v in values.items()]
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
        self.title("GDrive Auto Uploader - Multi-Tab Parallel Batch Engine v2.4")
        self.geometry("1160x820")
        self.minsize(980, 720)
        self.configure(fg_color=BG_MAIN)

        self._process: subprocess.Popen | None = None
        self._log_thread: threading.Thread | None = None
        self._running = False
        self._manual_stop = False
        self._start_time = None
        self._last_queue_sig = None
        self._active_tab = "dashboard"
        self._queue_filter = "all"
        self._autoscroll = True

        self.logo_ctk = None
        logo_path = BUNDLE_DIR / "public" / "LogoAI.png"
        if logo_path.exists():
            try:
                img = Image.open(logo_path)
                self.logo_ctk = ctk.CTkImage(light_image=img, dark_image=img, size=(32, 32))
            except Exception:
                pass

        self._setup_navbar()
        self._setup_view_container()

        self._load_saved_settings()
        self._check_login_status()
        self._poll_status()

    def _setup_navbar(self):
        self.nav_frame = ctk.CTkFrame(self, fg_color=BG_NAV, corner_radius=0, height=64)
        self.nav_frame.pack(fill="x", side="top")
        self.nav_frame.pack_propagate(False)

        nav_inner = ctk.CTkFrame(self.nav_frame, fg_color="transparent")
        nav_inner.pack(fill="both", expand=True, padx=20, pady=10)

        brand_box = ctk.CTkFrame(nav_inner, fg_color="transparent")
        brand_box.pack(side="left")

        if self.logo_ctk:
            ctk.CTkLabel(brand_box, image=self.logo_ctk, text="").pack(side="left", padx=(0, 10))
        else:
            logo_pill = ctk.CTkLabel(
                brand_box,
                text="GD",
                fg_color=ACCENT_BLUE,
                text_color=TEXT_MAIN,
                font=ctk.CTkFont(size=13, weight="bold"),
                corner_radius=6,
                width=34,
                height=34,
            )
            logo_pill.pack(side="left", padx=(0, 10))

        titles_box = ctk.CTkFrame(brand_box, fg_color="transparent")
        titles_box.pack(side="left")

        ctk.CTkLabel(
            titles_box,
            text="GDrive Auto Uploader",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=TEXT_MAIN,
        ).pack(anchor="w")

        ctk.CTkLabel(
            titles_box,
            text="Multi-Tab Parallel Batch Engine v2.4",
            font=ctk.CTkFont(size=11),
            text_color=TEXT_MUTED,
        ).pack(anchor="w")

        tabs_box = ctk.CTkFrame(nav_inner, fg_color=BG_MAIN, corner_radius=8, height=38)
        tabs_box.pack(side="left", padx=30)

        self.nav_buttons = {}
        tab_defs = [
            ("dashboard", "🚀 Dashboard"),
            ("queue", "📋 Antrean Batch"),
            ("config", "⚙️ Konfigurasi"),
            ("logs", "📝 Live Konsol"),
        ]

        for tab_id, tab_label in tab_defs:
            btn = ctk.CTkButton(
                tabs_box,
                text=tab_label,
                font=ctk.CTkFont(size=12, weight="bold"),
                height=32,
                corner_radius=6,
                fg_color="transparent",
                text_color=TEXT_MUTED,
                hover_color=BG_CARD,
                command=lambda tid=tab_id: self._switch_tab(tid),
            )
            btn.pack(side="left", padx=3, pady=3)
            self.nav_buttons[tab_id] = btn

        right_box = ctk.CTkFrame(nav_inner, fg_color="transparent")
        right_box.pack(side="right")

        self.session_pill = ctk.CTkLabel(
            right_box,
            text="Checking session...",
            fg_color=BG_CARD_ALT,
            text_color=TEXT_MUTED,
            font=ctk.CTkFont(size=11, weight="bold"),
            corner_radius=6,
            padx=12,
            pady=6,
        )
        self.session_pill.pack(side="left", padx=(0, 10))

        self.btn_login = ctk.CTkButton(
            right_box,
            text="🔑 Buka Login",
            command=self._open_browser_login,
            fg_color=BG_CARD_ALT,
            hover_color="#334155",
            font=ctk.CTkFont(size=11, weight="bold"),
            height=32,
            width=100,
            corner_radius=6,
        )
        self.btn_login.pack(side="left")

    def _setup_view_container(self):
        self.views_container = ctk.CTkFrame(self, fg_color="transparent")
        self.views_container.pack(fill="both", expand=True)

        self.view_dashboard = ctk.CTkFrame(self.views_container, fg_color="transparent")
        self.view_queue = ctk.CTkFrame(self.views_container, fg_color="transparent")
        self.view_config = ctk.CTkFrame(self.views_container, fg_color="transparent")
        self.view_logs = ctk.CTkFrame(self.views_container, fg_color="transparent")

        self._build_dashboard_view()
        self._build_queue_view()
        self._build_config_view()
        self._build_logs_view()

        self._switch_tab("dashboard")

    def _switch_tab(self, tab_id: str):
        self._active_tab = tab_id
        for tid, btn in self.nav_buttons.items():
            if tid == tab_id:
                btn.configure(fg_color=BG_CARD_ALT, text_color=TEXT_MAIN)
            else:
                btn.configure(fg_color="transparent", text_color=TEXT_MUTED)

        for v in (self.view_dashboard, self.view_queue, self.view_config, self.view_logs):
            v.pack_forget()

        if tab_id == "dashboard":
            self.view_dashboard.pack(fill="both", expand=True, padx=20, pady=16)
        elif tab_id == "queue":
            self.view_queue.pack(fill="both", expand=True, padx=20, pady=16)
            self._update_queue_ui(force=True)
        elif tab_id == "config":
            self.view_config.pack(fill="both", expand=True, padx=20, pady=16)
        elif tab_id == "logs":
            self.view_logs.pack(fill="both", expand=True, padx=20, pady=16)

    def _build_dashboard_view(self):
        grid = ctk.CTkFrame(self.view_dashboard, fg_color="transparent")
        grid.pack(fill="both", expand=True)
        grid.grid_columnconfigure(0, weight=5, uniform="dash_cols")
        grid.grid_columnconfigure(1, weight=6, uniform="dash_cols")
        grid.grid_rowconfigure(0, weight=1)

        left_scroll = ctk.CTkScrollableFrame(grid, fg_color="transparent")
        left_scroll.grid(row=0, column=0, sticky="nsew", padx=(0, 10))

        right_scroll = ctk.CTkScrollableFrame(grid, fg_color="transparent")
        right_scroll.grid(row=0, column=1, sticky="nsew", padx=(10, 0))

        # Left Column - Card 1: Target Folders
        c1 = ctk.CTkFrame(left_scroll, fg_color=BG_CARD, corner_radius=12, border_color=BORDER_COLOR, border_width=1)
        c1.pack(fill="x", pady=(0, 14))
        c1_in = ctk.CTkFrame(c1, fg_color="transparent")
        c1_in.pack(fill="x", padx=16, pady=14)

        ctk.CTkLabel(c1_in, text="📁 Target Folder Komputer & Drive", font=ctk.CTkFont(size=14, weight="bold"), text_color=TEXT_MAIN).pack(anchor="w", pady=(0, 8))

        ctk.CTkLabel(c1_in, text="Folder Sumber di Komputer:", font=ctk.CTkFont(size=12), text_color=TEXT_MUTED).pack(anchor="w")
        folder_row = ctk.CTkFrame(c1_in, fg_color="transparent")
        folder_row.pack(fill="x", pady=(2, 10))
        self.entry_local_folder = ctk.CTkEntry(folder_row, fg_color=BG_INPUT, border_color=BORDER_COLOR, corner_radius=8, placeholder_text="Pilih folder file yang akan diunggah...")
        self.entry_local_folder.pack(side="left", fill="x", expand=True, padx=(0, 8))
        ctk.CTkButton(folder_row, text="Pilih Folder...", width=100, corner_radius=8, command=self._browse_folder, fg_color=BG_CARD_ALT, hover_color="#334155").pack(side="right")

        ctk.CTkLabel(c1_in, text="Tautan Folder Google Drive (URL atau ID):", font=ctk.CTkFont(size=12), text_color=TEXT_MUTED).pack(anchor="w")
        self.entry_drive_url = ctk.CTkEntry(c1_in, fg_color=BG_INPUT, border_color=BORDER_COLOR, corner_radius=8, placeholder_text="https://drive.google.com/drive/folders/...")
        self.entry_drive_url.pack(fill="x", pady=(2, 4))

        # Left Column - Card 2: Worker & Batch Params
        c2 = ctk.CTkFrame(left_scroll, fg_color=BG_CARD, corner_radius=12, border_color=BORDER_COLOR, border_width=1)
        c2.pack(fill="x", pady=(0, 14))
        c2_in = ctk.CTkFrame(c2, fg_color="transparent")
        c2_in.pack(fill="x", padx=16, pady=14)

        ctk.CTkLabel(c2_in, text="⚡ Parameter Worker & Batch Kustom", font=ctk.CTkFont(size=14, weight="bold"), text_color=TEXT_MAIN).pack(anchor="w", pady=(0, 4))
        ctk.CTkLabel(c2_in, text="Kapasitas paralel multi-tab dan ukuran pembagian berkas.", font=ctk.CTkFont(size=11), text_color=TEXT_DIM).pack(anchor="w", pady=(0, 10))

        param_grid = ctk.CTkFrame(c2_in, fg_color="transparent")
        param_grid.pack(fill="x")
        param_grid.grid_columnconfigure((0, 1), weight=1)

        p0 = ctk.CTkFrame(param_grid, fg_color="transparent")
        p0.grid(row=0, column=0, sticky="ew", padx=(0, 6), pady=4)
        ctk.CTkLabel(p0, text="Jumlah Tab (Workers):", font=ctk.CTkFont(size=11), text_color=TEXT_MUTED).pack(anchor="w")
        self.opt_workers = ctk.CTkOptionMenu(p0, values=["1 Tab", "2 Tab", "3 Tab", "4 Tab", "5 Tab", "8 Tab", "10 Tab"], fg_color=BG_INPUT, button_color=BG_CARD_ALT, corner_radius=8)
        self.opt_workers.pack(fill="x", pady=2)
        self.opt_workers.set("3 Tab")

        p1 = ctk.CTkFrame(param_grid, fg_color="transparent")
        p1.grid(row=0, column=1, sticky="ew", padx=(6, 0), pady=4)
        ctk.CTkLabel(p1, text="Ukuran Batch (File/Tab):", font=ctk.CTkFont(size=11), text_color=TEXT_MUTED).pack(anchor="w")
        self.opt_batch_size = ctk.CTkOptionMenu(p1, values=["10 File", "25 File", "50 File", "100 File", "200 File"], fg_color=BG_INPUT, button_color=BG_CARD_ALT, corner_radius=8)
        self.opt_batch_size.pack(fill="x", pady=2)
        self.opt_batch_size.set("50 File")

        p2 = ctk.CTkFrame(param_grid, fg_color="transparent")
        p2.grid(row=1, column=0, sticky="ew", padx=(0, 6), pady=4)
        ctk.CTkLabel(p2, text="Jika File Duplikat:", font=ctk.CTkFont(size=11), text_color=TEXT_MUTED).pack(anchor="w")
        self.opt_duplicates = ctk.CTkOptionMenu(p2, values=["Simpan Keduanya", "Ganti File Lama"], fg_color=BG_INPUT, button_color=BG_CARD_ALT, corner_radius=8)
        self.opt_duplicates.pack(fill="x", pady=2)
        self.opt_duplicates.set("Simpan Keduanya")

        p3 = ctk.CTkFrame(param_grid, fg_color="transparent")
        p3.grid(row=1, column=1, sticky="ew", padx=(6, 0), pady=4)
        ctk.CTkLabel(p3, text="Mode Browser:", font=ctk.CTkFont(size=11), text_color=TEXT_MUTED).pack(anchor="w")
        self.opt_headless = ctk.CTkOptionMenu(p3, values=["Jendela Tampak (Headful)", "Latar Belakang (Headless)"], fg_color=BG_INPUT, button_color=BG_CARD_ALT, corner_radius=8)
        self.opt_headless.pack(fill="x", pady=2)
        self.opt_headless.set("Jendela Tampak (Headful)")

        # Left Column - Card 3: Execution Controls
        c3 = ctk.CTkFrame(left_scroll, fg_color=BG_CARD, corner_radius=12, border_color=BORDER_COLOR, border_width=1)
        c3.pack(fill="x", pady=(0, 10))
        c3_in = ctk.CTkFrame(c3, fg_color="transparent")
        c3_in.pack(fill="x", padx=16, pady=14)

        ctk.CTkLabel(c3_in, text="🎮 Kontrol Eksekusi", font=ctk.CTkFont(size=14, weight="bold"), text_color=TEXT_MAIN).pack(anchor="w", pady=(0, 8))

        btn_row1 = ctk.CTkFrame(c3_in, fg_color="transparent")
        btn_row1.pack(fill="x", pady=(0, 8))

        self.btn_start = ctk.CTkButton(
            btn_row1,
            text="🚀 Mulai Upload",
            command=self._start_upload,
            fg_color=ACCENT_BLUE,
            hover_color=ACCENT_BLUE_HOVER,
            font=ctk.CTkFont(size=13, weight="bold"),
            height=38,
            corner_radius=8,
        )
        self.btn_start.pack(side="left", fill="x", expand=True, padx=(0, 6))

        self.btn_stop = ctk.CTkButton(
            btn_row1,
            text="⏸️ Hentikan",
            command=self._stop_upload,
            state="disabled",
            fg_color=ACCENT_RED,
            hover_color="#DC2626",
            font=ctk.CTkFont(size=13, weight="bold"),
            height=38,
            corner_radius=8,
        )
        self.btn_stop.pack(side="right", fill="x", expand=True, padx=(6, 0))

        btn_row2 = ctk.CTkFrame(c3_in, fg_color="transparent")
        btn_row2.pack(fill="x")

        ctk.CTkButton(
            btn_row2,
            text="🔄 Reset Antrean",
            command=self._reset_queue,
            fg_color=BG_CARD_ALT,
            hover_color="#334155",
            font=ctk.CTkFont(size=11, weight="bold"),
            height=32,
            corner_radius=8,
        ).pack(side="left", fill="x", expand=True, padx=(0, 6))

        ctk.CTkButton(
            btn_row2,
            text="🔁 Retry Batch Gagal",
            command=self._retry_failed,
            fg_color=BG_CARD_ALT,
            hover_color="#334155",
            font=ctk.CTkFont(size=11, weight="bold"),
            height=32,
            corner_radius=8,
        ).pack(side="right", fill="x", expand=True, padx=(6, 0))

        # Right Column - Card 4: Progress & Stats
        c4 = ctk.CTkFrame(right_scroll, fg_color=BG_CARD, corner_radius=12, border_color=BORDER_COLOR, border_width=1)
        c4.pack(fill="x", pady=(0, 14))
        c4_in = ctk.CTkFrame(c4, fg_color="transparent")
        c4_in.pack(fill="x", padx=16, pady=14)

        c4_top = ctk.CTkFrame(c4_in, fg_color="transparent")
        c4_top.pack(fill="x", pady=(0, 6))

        ctk.CTkLabel(c4_top, text="📊 Ringkasan Progres", font=ctk.CTkFont(size=14, weight="bold"), text_color=TEXT_MAIN).pack(side="left")

        self.dash_status_badge = ctk.CTkLabel(
            c4_top,
            text="STATUS: SIAP",
            fg_color=BG_CARD_ALT,
            text_color=TEXT_MAIN,
            font=ctk.CTkFont(size=11, weight="bold"),
            corner_radius=6,
            padx=10,
            pady=4,
        )
        self.dash_status_badge.pack(side="right")

        self.dash_progress_bar = ctk.CTkProgressBar(c4_in, fg_color=BG_INPUT, progress_color=ACCENT_BLUE, height=10, corner_radius=5)
        self.dash_progress_bar.pack(fill="x", pady=(4, 8))
        self.dash_progress_bar.set(0)

        # 4 Stat Tiles
        tiles_frame = ctk.CTkFrame(c4_in, fg_color="transparent")
        tiles_frame.pack(fill="x", pady=(4, 0))
        tiles_frame.grid_columnconfigure((0, 1, 2, 3), weight=1)

        self.stat_total = self._create_tile(tiles_frame, 0, "Total File", "0", TEXT_MAIN)
        self.stat_done = self._create_tile(tiles_frame, 1, "File Terupload", "0", ACCENT_GREEN)
        self.stat_pending = self._create_tile(tiles_frame, 2, "Batch Pending", "0", ACCENT_AMBER)
        self.stat_failed = self._create_tile(tiles_frame, 3, "Batch Gagal", "0", ACCENT_RED)

        # Right Column - Card 5: Parallel Worker Tabs
        c5 = ctk.CTkFrame(right_scroll, fg_color=BG_CARD, corner_radius=12, border_color=BORDER_COLOR, border_width=1)
        c5.pack(fill="x", pady=(0, 14))
        c5_in = ctk.CTkFrame(c5, fg_color="transparent")
        c5_in.pack(fill="x", padx=16, pady=14)

        ctk.CTkLabel(c5_in, text="🖥️ Status Tab Worker Paralel", font=ctk.CTkFont(size=14, weight="bold"), text_color=TEXT_MAIN).pack(anchor="w", pady=(0, 8))

        self.worker_container = ctk.CTkFrame(c5_in, fg_color="transparent")
        self.worker_container.pack(fill="x")
        self.worker_cards = {}
        self._refresh_worker_cards(3)

        # Right Column - Card 6: Console Snippet
        c6 = ctk.CTkFrame(right_scroll, fg_color=BG_CARD, corner_radius=12, border_color=BORDER_COLOR, border_width=1)
        c6.pack(fill="x", pady=(0, 10))
        c6_in = ctk.CTkFrame(c6, fg_color="transparent")
        c6_in.pack(fill="x", padx=16, pady=14)

        c6_top = ctk.CTkFrame(c6_in, fg_color="transparent")
        c6_top.pack(fill="x", pady=(0, 6))

        ctk.CTkLabel(c6_top, text="📝 Cuplikan Konsol", font=ctk.CTkFont(size=14, weight="bold"), text_color=TEXT_MAIN).pack(side="left")

        ctk.CTkButton(
            c6_top,
            text="Buka Konsol Penuh →",
            command=lambda: self._switch_tab("logs"),
            fg_color="transparent",
            text_color=ACCENT_BLUE,
            hover_color=BG_CARD_ALT,
            font=ctk.CTkFont(size=11, weight="bold"),
            height=26,
            corner_radius=6,
        ).pack(side="right")

        self.dash_log_preview = ctk.CTkTextbox(c6_in, fg_color=BG_INPUT, font=("Consolas", 10), height=110, corner_radius=8)
        self.dash_log_preview.pack(fill="x")
        self.dash_log_preview.insert("end", "[Info] Sistem siap. Klik Mulai Upload untuk memproses antrean.\n")

    def _create_tile(self, parent, col, title, val, color):
        tile = ctk.CTkFrame(parent, fg_color=BG_INPUT, corner_radius=8)
        tile.grid(row=0, column=col, sticky="ew", padx=3)
        ctk.CTkLabel(tile, text=title, font=ctk.CTkFont(size=10), text_color=TEXT_MUTED).pack(pady=(6, 0))
        lbl = ctk.CTkLabel(tile, text=val, font=ctk.CTkFont(size=16, weight="bold"), text_color=color)
        lbl.pack(pady=(0, 6))
        return lbl

    def _refresh_worker_cards(self, count: int):
        for child in self.worker_container.winfo_children():
            child.destroy()
        self.worker_cards.clear()

        for i in range(1, count + 1):
            row = ctk.CTkFrame(self.worker_container, fg_color=BG_INPUT, corner_radius=8, height=36)
            row.pack(fill="x", pady=3)
            row.pack_propagate(False)

            icon_lbl = ctk.CTkLabel(row, text=f"Tab {i}", font=ctk.CTkFont(size=11, weight="bold"), text_color=TEXT_MAIN)
            icon_lbl.pack(side="left", padx=10)

            batch_lbl = ctk.CTkLabel(row, text="Menunggu tugas...", font=ctk.CTkFont(size=11), text_color=TEXT_DIM)
            batch_lbl.pack(side="left", padx=10)

            badge = ctk.CTkLabel(
                row,
                text="IDLE",
                fg_color=BG_CARD_ALT,
                text_color=TEXT_MUTED,
                font=ctk.CTkFont(size=10, weight="bold"),
                corner_radius=6,
                padx=8,
                pady=2,
            )
            badge.pack(side="right", padx=10)

            self.worker_cards[i] = {"batch": batch_lbl, "badge": badge}

    def _build_queue_view(self):
        toolbar = ctk.CTkFrame(self.view_queue, fg_color=BG_CARD, corner_radius=12, border_color=BORDER_COLOR, border_width=1)
        toolbar.pack(fill="x", pady=(0, 12))
        tb_in = ctk.CTkFrame(toolbar, fg_color="transparent")
        tb_in.pack(fill="x", padx=16, pady=10)

        filter_box = ctk.CTkFrame(tb_in, fg_color=BG_INPUT, corner_radius=8)
        filter_box.pack(side="left")

        self.filter_buttons = {}
        for f_key, f_lbl in [("all", "Semua"), ("pending", "Pending"), ("processing", "Berjalan"), ("completed", "Selesai"), ("failed", "Gagal")]:
            btn = ctk.CTkButton(
                filter_box,
                text=f_lbl,
                font=ctk.CTkFont(size=11, weight="bold"),
                height=28,
                corner_radius=6,
                fg_color="transparent",
                text_color=TEXT_MUTED,
                hover_color=BG_CARD,
                command=lambda k=f_key: self._set_queue_filter(k),
            )
            btn.pack(side="left", padx=2, pady=2)
            self.filter_buttons[f_key] = btn
        self.filter_buttons["all"].configure(fg_color=BG_CARD_ALT, text_color=TEXT_MAIN)

        self.queue_search_entry = ctk.CTkEntry(tb_in, placeholder_text="Cari ID batch...", fg_color=BG_INPUT, border_color=BORDER_COLOR, corner_radius=8, width=180, height=30)
        self.queue_search_entry.pack(side="left", padx=12)
        self.queue_search_entry.bind("<KeyRelease>", lambda e: self._update_queue_ui(force=True))

        tb_right = ctk.CTkFrame(tb_in, fg_color="transparent")
        tb_right.pack(side="right")

        ctk.CTkButton(
            tb_right,
            text="🔁 Retry Gagal",
            command=self._retry_failed,
            fg_color=BG_CARD_ALT,
            hover_color="#334155",
            font=ctk.CTkFont(size=11, weight="bold"),
            height=30,
            corner_radius=6,
        ).pack(side="left", padx=4)

        ctk.CTkButton(
            tb_right,
            text="🔄 Reset Antrean",
            command=self._reset_queue,
            fg_color=BG_CARD_ALT,
            hover_color="#334155",
            font=ctk.CTkFont(size=11, weight="bold"),
            height=30,
            corner_radius=6,
        ).pack(side="left", padx=4)

        table_card = ctk.CTkFrame(self.view_queue, fg_color=BG_CARD, corner_radius=12, border_color=BORDER_COLOR, border_width=1)
        table_card.pack(fill="both", expand=True)

        header_row = ctk.CTkFrame(table_card, fg_color=BG_INPUT, corner_radius=8, height=36)
        header_row.pack(fill="x", padx=12, pady=(12, 6))
        header_row.pack_propagate(False)

        ctk.CTkLabel(header_row, text="BATCH ID", font=ctk.CTkFont(size=11, weight="bold"), text_color=TEXT_MUTED, width=160, anchor="w").pack(side="left", padx=(12, 6))
        ctk.CTkLabel(header_row, text="JUMLAH FILE", font=ctk.CTkFont(size=11, weight="bold"), text_color=TEXT_MUTED, width=110, anchor="w").pack(side="left", padx=6)
        ctk.CTkLabel(header_row, text="STATUS", font=ctk.CTkFont(size=11, weight="bold"), text_color=TEXT_MUTED, width=120, anchor="w").pack(side="left", padx=6)
        ctk.CTkLabel(header_row, text="WORKER / INFO", font=ctk.CTkFont(size=11, weight="bold"), text_color=TEXT_MUTED, anchor="w").pack(side="left", fill="x", expand=True, padx=6)
        ctk.CTkLabel(header_row, text="RETRY", font=ctk.CTkFont(size=11, weight="bold"), text_color=TEXT_MUTED, width=70, anchor="center").pack(side="right", padx=(6, 12))

        self.queue_scroll = ctk.CTkScrollableFrame(table_card, fg_color="transparent")
        self.queue_scroll.pack(fill="both", expand=True, padx=12, pady=(0, 12))

    def _set_queue_filter(self, key: str):
        self._queue_filter = key
        for k, btn in self.filter_buttons.items():
            if k == key:
                btn.configure(fg_color=BG_CARD_ALT, text_color=TEXT_MAIN)
            else:
                btn.configure(fg_color="transparent", text_color=TEXT_MUTED)
        self._update_queue_ui(force=True)

    def _build_config_view(self):
        c_scroll = ctk.CTkScrollableFrame(self.view_config, fg_color="transparent")
        c_scroll.pack(fill="both", expand=True)

        header_box = ctk.CTkFrame(c_scroll, fg_color="transparent")
        header_box.pack(fill="x", pady=(0, 14))
        ctk.CTkLabel(header_box, text="⚙️ Konfigurasi Sistem & Parameter Backend", font=ctk.CTkFont(size=18, weight="bold"), text_color=TEXT_MAIN).pack(anchor="w")
        ctk.CTkLabel(header_box, text="Sesuaikan mesin browser Playwright, kebijakan retry antrean, filter berkas, dan penyimpanan profil.", font=ctk.CTkFont(size=12), text_color=TEXT_MUTED).pack(anchor="w")

        grid = ctk.CTkFrame(c_scroll, fg_color="transparent")
        grid.pack(fill="both", expand=True)
        grid.grid_columnconfigure((0, 1), weight=1, uniform="cfg_cols")

        # Col 0: Browser & Retry
        col0 = ctk.CTkFrame(grid, fg_color="transparent")
        col0.grid(row=0, column=0, sticky="nsew", padx=(0, 10))

        card_browser = ctk.CTkFrame(col0, fg_color=BG_CARD, corner_radius=12, border_color=BORDER_COLOR, border_width=1)
        card_browser.pack(fill="x", pady=(0, 14))
        cb_in = ctk.CTkFrame(card_browser, fg_color="transparent")
        cb_in.pack(fill="x", padx=16, pady=14)

        ctk.CTkLabel(cb_in, text="🌐 Browser Engine (Playwright)", font=ctk.CTkFont(size=14, weight="bold"), text_color=TEXT_MAIN).pack(anchor="w", pady=(0, 8))

        ctk.CTkLabel(cb_in, text="Browser Channel:", font=ctk.CTkFont(size=11), text_color=TEXT_MUTED).pack(anchor="w")
        self.cfg_browser_channel = ctk.CTkOptionMenu(cb_in, values=["chrome", "msedge", "chromium"], fg_color=BG_INPUT, button_color=BG_CARD_ALT, corner_radius=8)
        self.cfg_browser_channel.pack(fill="x", pady=(2, 8))

        self.cfg_headless_cb = ctk.CTkCheckBox(cb_in, text="Jalankan Mode Headless (tanpa jendela GUI)", font=ctk.CTkFont(size=12), text_color=TEXT_MAIN)
        self.cfg_headless_cb.pack(anchor="w", pady=(2, 6))

        self.cfg_watchdog_cb = ctk.CTkCheckBox(cb_in, text="Pantau Folder Real-Time (Watchdog Auto-Add)", font=ctk.CTkFont(size=12), text_color=TEXT_MAIN)
        self.cfg_watchdog_cb.pack(anchor="w", pady=(2, 6))

        card_retry = ctk.CTkFrame(col0, fg_color=BG_CARD, corner_radius=12, border_color=BORDER_COLOR, border_width=1)
        card_retry.pack(fill="x", pady=(0, 14))
        cr_in = ctk.CTkFrame(card_retry, fg_color="transparent")
        cr_in.pack(fill="x", padx=16, pady=14)

        ctk.CTkLabel(cr_in, text="🛡️ Retry & Ketahanan Antrean", font=ctk.CTkFont(size=14, weight="bold"), text_color=TEXT_MAIN).pack(anchor="w", pady=(0, 8))

        ctk.CTkLabel(cr_in, text="Batas Maksimum Percobaan Ulang (Retry Limit):", font=ctk.CTkFont(size=11), text_color=TEXT_MUTED).pack(anchor="w")
        self.cfg_retry_limit = ctk.CTkOptionMenu(cr_in, values=["1 Kali", "2 Kali", "3 Kali", "5 Kali", "10 Kali"], fg_color=BG_INPUT, button_color=BG_CARD_ALT, corner_radius=8)
        self.cfg_retry_limit.pack(fill="x", pady=(2, 8))

        ctk.CTkLabel(cr_in, text="Jeda Antar Percobaan Ulang (detik):", font=ctk.CTkFont(size=11), text_color=TEXT_MUTED).pack(anchor="w")
        self.cfg_retry_delay = ctk.CTkEntry(cr_in, fg_color=BG_INPUT, border_color=BORDER_COLOR, corner_radius=8)
        self.cfg_retry_delay.pack(fill="x", pady=(2, 8))

        self.cfg_zombie_cb = ctk.CTkCheckBox(cr_in, text="Pemulihan Otomatis Batch Zombie saat Aplikasi Terputus", font=ctk.CTkFont(size=12), text_color=TEXT_MAIN)
        self.cfg_zombie_cb.pack(anchor="w", pady=(2, 6))

        # Col 1: Filters & Storage
        col1 = ctk.CTkFrame(grid, fg_color="transparent")
        col1.grid(row=0, column=1, sticky="nsew", padx=(10, 0))

        card_filter = ctk.CTkFrame(col1, fg_color=BG_CARD, corner_radius=12, border_color=BORDER_COLOR, border_width=1)
        card_filter.pack(fill="x", pady=(0, 14))
        cf_in = ctk.CTkFrame(card_filter, fg_color="transparent")
        cf_in.pack(fill="x", padx=16, pady=14)

        ctk.CTkLabel(cf_in, text="📑 Filter Berkas & Duplikat", font=ctk.CTkFont(size=14, weight="bold"), text_color=TEXT_MAIN).pack(anchor="w", pady=(0, 8))

        ctk.CTkLabel(cf_in, text="Filter Ekstensi Berkas (kosongkan untuk semua):", font=ctk.CTkFont(size=11), text_color=TEXT_MUTED).pack(anchor="w")
        self.cfg_extensions = ctk.CTkEntry(cf_in, placeholder_text=".jpg, .png, .pdf, .mp4", fg_color=BG_INPUT, border_color=BORDER_COLOR, corner_radius=8)
        self.cfg_extensions.pack(fill="x", pady=(2, 8))

        card_storage = ctk.CTkFrame(col1, fg_color=BG_CARD, corner_radius=12, border_color=BORDER_COLOR, border_width=1)
        card_storage.pack(fill="x", pady=(0, 14))
        cs_in = ctk.CTkFrame(card_storage, fg_color="transparent")
        cs_in.pack(fill="x", padx=16, pady=14)

        ctk.CTkLabel(cs_in, text="💾 Penyimpanan & Profil Akun", font=ctk.CTkFont(size=14, weight="bold"), text_color=TEXT_MAIN).pack(anchor="w", pady=(0, 8))

        ctk.CTkLabel(cs_in, text=f"File Status: {STATE_FILE.name}", font=ctk.CTkFont(size=11), text_color=TEXT_MUTED).pack(anchor="w", pady=(0, 2))
        ctk.CTkLabel(cs_in, text=f"Profil Direktori: {PROFILE_DIR.name}", font=ctk.CTkFont(size=11), text_color=TEXT_MUTED).pack(anchor="w", pady=(0, 8))

        btn_grid = ctk.CTkFrame(cs_in, fg_color="transparent")
        btn_grid.pack(fill="x", pady=(4, 0))

        ctk.CTkButton(
            btn_grid,
            text="📁 Buka Folder Profil",
            command=self._open_profile_folder,
            fg_color=BG_CARD_ALT,
            hover_color="#334155",
            font=ctk.CTkFont(size=11, weight="bold"),
            height=32,
            corner_radius=8,
        ).pack(side="left", fill="x", expand=True, padx=(0, 4))

        ctk.CTkButton(
            btn_grid,
            text="📁 Buka Folder Log",
            command=self._open_log_folder,
            fg_color=BG_CARD_ALT,
            hover_color="#334155",
            font=ctk.CTkFont(size=11, weight="bold"),
            height=32,
            corner_radius=8,
        ).pack(side="right", fill="x", expand=True, padx=(4, 0))

        # Bottom Config Action Bar
        action_bar = ctk.CTkFrame(c_scroll, fg_color=BG_CARD, corner_radius=12, border_color=BORDER_COLOR, border_width=1)
        action_bar.pack(fill="x", pady=(4, 10))
        ab_in = ctk.CTkFrame(action_bar, fg_color="transparent")
        ab_in.pack(fill="x", padx=16, pady=12)

        ctk.CTkButton(
            ab_in,
            text="💾 Simpan Perubahan Konfigurasi (.env)",
            command=self._save_all_settings,
            fg_color=ACCENT_BLUE,
            hover_color=ACCENT_BLUE_HOVER,
            font=ctk.CTkFont(size=12, weight="bold"),
            height=36,
            corner_radius=8,
        ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            ab_in,
            text="🔄 Muat Ulang Nilai",
            command=self._load_saved_settings,
            fg_color=BG_CARD_ALT,
            hover_color="#334155",
            font=ctk.CTkFont(size=12, weight="bold"),
            height=36,
            corner_radius=8,
        ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            ab_in,
            text="⚠️ Kembalikan Setelan Pabrik",
            command=self._reset_defaults,
            fg_color="transparent",
            text_color=ACCENT_RED,
            hover_color=BG_CARD_ALT,
            font=ctk.CTkFont(size=12, weight="bold"),
            height=36,
            corner_radius=8,
        ).pack(side="right")

    def _build_logs_view(self):
        header = ctk.CTkFrame(self.view_logs, fg_color=BG_CARD, corner_radius=12, border_color=BORDER_COLOR, border_width=1)
        header.pack(fill="x", pady=(0, 12))
        h_in = ctk.CTkFrame(header, fg_color="transparent")
        h_in.pack(fill="x", padx=16, pady=10)

        ctk.CTkLabel(h_in, text="📝 Live Konsol Real-Time", font=ctk.CTkFont(size=14, weight="bold"), text_color=TEXT_MAIN).pack(side="left")

        actions = ctk.CTkFrame(h_in, fg_color="transparent")
        actions.pack(side="right")

        self.autoscroll_cb = ctk.CTkCheckBox(
            actions,
            text="Auto-scroll",
            font=ctk.CTkFont(size=11),
            text_color=TEXT_MUTED,
            command=self._toggle_autoscroll,
        )
        self.autoscroll_cb.pack(side="left", padx=8)
        self.autoscroll_cb.select()

        ctk.CTkButton(
            actions,
            text="Bersihkan Tampilan",
            command=self._clear_logs,
            fg_color=BG_CARD_ALT,
            hover_color="#334155",
            font=ctk.CTkFont(size=11, weight="bold"),
            height=28,
            corner_radius=6,
        ).pack(side="left", padx=4)

        ctk.CTkButton(
            actions,
            text="📁 Buka Folder Log",
            command=self._open_log_folder,
            fg_color=BG_CARD_ALT,
            hover_color="#334155",
            font=ctk.CTkFont(size=11, weight="bold"),
            height=28,
            corner_radius=6,
        ).pack(side="left", padx=4)

        terminal_card = ctk.CTkFrame(self.view_logs, fg_color=BG_CARD, corner_radius=12, border_color=BORDER_COLOR, border_width=1)
        terminal_card.pack(fill="both", expand=True)

        self.log_textbox = ctk.CTkTextbox(terminal_card, fg_color=BG_INPUT, font=("Consolas", 11), corner_radius=8)
        self.log_textbox.pack(fill="both", expand=True, padx=12, pady=12)

    def _toggle_autoscroll(self):
        self._autoscroll = bool(self.autoscroll_cb.get())

    def _clear_logs(self):
        self.log_textbox.delete("1.0", "end")
        self.dash_log_preview.delete("1.0", "end")

    def _browse_folder(self):
        folder = filedialog.askdirectory(title="Pilih Folder Berisi Berkas")
        if folder:
            old_folder = self.entry_local_folder.get().strip()
            self.entry_local_folder.delete(0, "end")
            self.entry_local_folder.insert(0, folder)
            self._save_all_settings()

            if old_folder and Path(old_folder).resolve() != Path(folder).resolve():
                state = load_state()
                if state.get("batches"):
                    if messagebox.askyesno(
                        "Folder Berubah",
                        "Anda memilih folder sumber yang berbeda.\n\n"
                        "Apakah Anda ingin mereset antrean upload lama agar antrean dimulai bersih dari nol (0)?",
                    ):
                        if STATE_FILE.exists():
                            try:
                                STATE_FILE.unlink()
                            except Exception:
                                pass
                        self._append_log(f"🔄 Folder sumber diubah ke '{folder}'. Antrean lama telah direset.\n")
                        self._update_queue_ui(force=True)

    def _open_log_folder(self):
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        os.startfile(str(LOG_DIR))

    def _open_profile_folder(self):
        PROFILE_DIR.mkdir(parents=True, exist_ok=True)
        os.startfile(str(PROFILE_DIR))

    def _check_login_status(self):
        has_session = PROFILE_DIR.exists() and any(PROFILE_DIR.glob("**/Cookies*"))
        if has_session:
            self.session_pill.configure(text="🟢 Akun Aktif: gdrive_profile", text_color=ACCENT_GREEN)
        else:
            self.session_pill.configure(text="🟡 Belum Login", text_color=ACCENT_AMBER)

    def _open_browser_login(self):
        self._save_all_settings()
        self.session_pill.configure(text="Memulai sesi login...", text_color=ACCENT_BLUE)

        def run_auth():
            cmd = [
                sys.executable,
                "-c",
                "import asyncio; from src.browser.auth_helper import AuthHelper; asyncio.run(AuthHelper.open_login_window())",
            ]
            subprocess.call(cmd, cwd=str(DATA_DIR))
            self.after(500, self._check_login_status)

        threading.Thread(target=run_auth, daemon=True).start()

    def _save_all_settings(self):
        workers_val = int(self.opt_workers.get().split()[0])
        batch_val = int(self.opt_batch_size.get().split()[0])
        dup_val = "replace" if self.opt_duplicates.get() == "Ganti File Lama" else "keep_both"
        headless_val = "true" if "Headless" in self.opt_headless.get() or self.cfg_headless_cb.get() else "false"

        retry_limit = int(self.cfg_retry_limit.get().split()[0])
        retry_delay = self.cfg_retry_delay.get().strip() or "10"

        values = {
            "TARGET_FOLDERS": self.entry_local_folder.get().strip(),
            "GDRIVE_FOLDER_URL": self.entry_drive_url.get().strip(),
            "MAX_WORKERS": str(workers_val),
            "BATCH_SIZE": str(batch_val),
            "DUPLICATE_ACTION": dup_val,
            "HEADLESS": headless_val,
            "BROWSER_CHANNEL": self.cfg_browser_channel.get(),
            "WATCHDOG_ENABLED": "true" if self.cfg_watchdog_cb.get() else "false",
            "RETRY_LIMIT": str(retry_limit),
            "RETRY_DELAY_SECONDS": retry_delay,
            "ZOMBIE_RECOVERY": "true" if self.cfg_zombie_cb.get() else "false",
            "FILE_EXTENSIONS": self.cfg_extensions.get().strip(),
        }
        save_env(values)
        self._refresh_worker_cards(workers_val)

    def _load_saved_settings(self):
        env = load_env()

        if "TARGET_FOLDERS" in env:
            self.entry_local_folder.delete(0, "end")
            self.entry_local_folder.insert(0, env["TARGET_FOLDERS"])

        if "GDRIVE_FOLDER_URL" in env:
            self.entry_drive_url.delete(0, "end")
            self.entry_drive_url.insert(0, env["GDRIVE_FOLDER_URL"])

        if "MAX_WORKERS" in env:
            w_val = env["MAX_WORKERS"]
            self.opt_workers.set(f"{w_val} Tab")
            try:
                self._refresh_worker_cards(int(w_val))
            except ValueError:
                pass

        if "BATCH_SIZE" in env:
            self.opt_batch_size.set(f"{env['BATCH_SIZE']} File")

        if "DUPLICATE_ACTION" in env:
            self.opt_duplicates.set("Ganti File Lama" if env["DUPLICATE_ACTION"] == "replace" else "Simpan Keduanya")

        is_headless = env.get("HEADLESS", "false").lower() == "true"
        self.opt_headless.set("Latar Belakang (Headless)" if is_headless else "Jendela Tampak (Headful)")
        if is_headless:
            self.cfg_headless_cb.select()
        else:
            self.cfg_headless_cb.deselect()

        if "BROWSER_CHANNEL" in env:
            self.cfg_browser_channel.set(env["BROWSER_CHANNEL"])

        if env.get("WATCHDOG_ENABLED", "true").lower() == "true":
            self.cfg_watchdog_cb.select()
        else:
            self.cfg_watchdog_cb.deselect()

        if "RETRY_LIMIT" in env:
            self.cfg_retry_limit.set(f"{env['RETRY_LIMIT']} Kali")

        self.cfg_retry_delay.delete(0, "end")
        self.cfg_retry_delay.insert(0, env.get("RETRY_DELAY_SECONDS", "10"))

        if env.get("ZOMBIE_RECOVERY", "true").lower() == "true":
            self.cfg_zombie_cb.select()
        else:
            self.cfg_zombie_cb.deselect()

        if "FILE_EXTENSIONS" in env:
            self.cfg_extensions.delete(0, "end")
            self.cfg_extensions.insert(0, env["FILE_EXTENSIONS"])

    def _reset_defaults(self):
        if messagebox.askyesno("Reset Pabrik", "Kembalikan seluruh parameter konfigurasi ke nilai default?"):
            self.opt_workers.set("3 Tab")
            self.opt_batch_size.set("50 File")
            self.opt_duplicates.set("Simpan Keduanya")
            self.opt_headless.set("Jendela Tampak (Headful)")
            self.cfg_headless_cb.deselect()
            self.cfg_browser_channel.set("chrome")
            self.cfg_watchdog_cb.select()
            self.cfg_retry_limit.set("3 Kali")
            self.cfg_retry_delay.delete(0, "end")
            self.cfg_retry_delay.insert(0, "10")
            self.cfg_zombie_cb.select()
            self.cfg_extensions.delete(0, "end")
            self._save_all_settings()

    def _start_upload(self):
        self._save_all_settings()

        local_dir = self.entry_local_folder.get().strip()
        drive_url = self.entry_drive_url.get().strip()

        if not local_dir or not Path(local_dir).exists():
            messagebox.showerror("Folder Tidak Ditemukan", "Pilih folder sumber di komputer Anda.")
            return

        if not drive_url:
            messagebox.showerror("URL Drive Kosong", "Masukkan tautan folder Google Drive tujuan.")
            return

        # Check if previous queue state exists with batches
        state = load_state()
        batches = state.get("batches", {})
        if batches:
            total_files = sum(len(b.get("files", [])) for b in batches.values())
            done_files = sum(len(b.get("files", [])) for b in batches.values() if b.get("status") == "completed")
            pending_b = sum(1 for b in batches.values() if b.get("status") in ["pending", "retrying", "processing"])
            failed_b = sum(1 for b in batches.values() if b.get("status") == "failed")

            if total_files > 0:
                self._show_resume_or_reset_dialog(
                    total_files=total_files,
                    done_files=done_files,
                    pending_b=pending_b,
                    failed_b=failed_b,
                    on_proceed=self._launch_upload_worker,
                )
                return

        self._launch_upload_worker()

    def _show_resume_or_reset_dialog(self, total_files: int, done_files: int, pending_b: int, failed_b: int, on_proceed):
        dialog = ctk.CTkToplevel(self)
        dialog.title("Konfirmasi Riwayat Antrean")
        dialog.geometry("500x260")
        dialog.resizable(False, False)
        dialog.configure(fg_color=BG_MAIN)
        dialog.transient(self)
        dialog.grab_set()

        # Center on parent window
        self.update_idletasks()
        dx = max(0, self.winfo_x() + (self.winfo_width() - 500) // 2)
        dy = max(0, self.winfo_y() + (self.winfo_height() - 260) // 2)
        dialog.geometry(f"+{dx}+{dy}")

        card = ctk.CTkFrame(dialog, fg_color=BG_CARD, corner_radius=12, border_color=BORDER_COLOR, border_width=1)
        card.pack(fill="both", expand=True, padx=16, pady=16)

        ctk.CTkLabel(
            card,
            text="Riwayat Upload Sebelumnya Ditemukan",
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color=TEXT_MAIN,
        ).pack(anchor="w", padx=20, pady=(16, 6))

        all_done = (pending_b == 0 and failed_b == 0 and done_files == total_files)

        if all_done:
            msg = (
                f"Sesi upload sebelumnya telah 100% selesai ({done_files} dari {total_files} file).\n"
                f"Apakah Anda ingin mereset antrean dan memulai upload baru dari nol (0)?"
            )
        else:
            msg = (
                f"File state.json menyimpan riwayat upload yang belum rampung:\n"
                f"• Terupload: {done_files} / {total_files} file\n"
                f"• Batch: {pending_b} pending, {failed_b} gagal\n\n"
                f"Pilih apakah Anda ingin melanjutkan sisa antrean atau mulai dari awal (0):"
            )

        ctk.CTkLabel(
            card,
            text=msg,
            font=ctk.CTkFont(size=12),
            text_color=TEXT_MUTED,
            justify="left",
            wraplength=440,
        ).pack(anchor="w", padx=20, pady=(0, 16))

        btn_row = ctk.CTkFrame(card, fg_color="transparent")
        btn_row.pack(fill="x", padx=20, pady=(0, 16), side="bottom")

        def do_reset():
            if STATE_FILE.exists():
                try:
                    STATE_FILE.unlink()
                except Exception:
                    pass
            self._append_log("🔄 Antrean lama telah direset. Memulai sesi baru dari 0...\n")
            self._update_queue_ui(force=True)
            dialog.destroy()
            on_proceed()

        def do_resume():
            self._append_log(f"▶️ Melanjutkan sisa antrean upload ({done_files}/{total_files} file sudah ada)...\n")
            dialog.destroy()
            on_proceed()

        def do_cancel():
            dialog.destroy()

        btn_reset = ctk.CTkButton(
            btn_row,
            text="Mulai Baru (Reset ke 0)",
            command=do_reset,
            fg_color=ACCENT_RED,
            hover_color="#DC2626",
            font=ctk.CTkFont(size=12, weight="bold"),
            height=36,
            corner_radius=8,
        )
        btn_reset.pack(side="left", fill="x", expand=True, padx=(0, 6))

        if not all_done:
            btn_resume = ctk.CTkButton(
                btn_row,
                text="Lanjutkan Sisa",
                command=do_resume,
                fg_color=ACCENT_BLUE,
                hover_color=ACCENT_BLUE_HOVER,
                font=ctk.CTkFont(size=12, weight="bold"),
                height=36,
                corner_radius=8,
            )
            btn_resume.pack(side="left", fill="x", expand=True, padx=(0, 6))

        btn_cancel = ctk.CTkButton(
            btn_row,
            text="Batal",
            command=do_cancel,
            fg_color=BG_CARD_ALT,
            hover_color="#334155",
            font=ctk.CTkFont(size=12),
            height=36,
            width=70,
            corner_radius=8,
        )
        btn_cancel.pack(side="right")

    def _launch_upload_worker(self):
        self._running = True
        self._manual_stop = False
        self._start_time = time.time()
        self.btn_start.configure(state="disabled")
        self.btn_stop.configure(state="normal")
        self.dash_status_badge.configure(text="STATUS: BERJALAN (00:00:00)", fg_color="#1E3A8A")

        self._append_log("🚀 Background upload agent started\n")

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
                errors="replace",
            )

            for line in iter(self._process.stdout.readline, ""):
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
        self._manual_stop = True
        if self._process and self._process.poll() is None:
            self._append_log("⚠️ Menghentikan agent...\n")
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

        for w_data in self.worker_cards.values():
            w_data["batch"].configure(text="Menunggu tugas...", text_color=TEXT_DIM)
            w_data["badge"].configure(text="IDLE", fg_color=BG_CARD_ALT, text_color=TEXT_MUTED)

        if self._manual_stop:
            self.dash_status_badge.configure(text="STATUS: BERHENTI", fg_color=BG_CARD_ALT)
            self._append_log("⏹️ Agent dihentikan oleh pengguna\n")
            self._manual_stop = False
            return

        state = load_state()
        batches = state.get("batches", {})
        total_batches = len(batches)
        pending_batches = sum(1 for b in batches.values() if b.get("status") in ["pending", "retrying", "processing"])
        completed_batches = sum(1 for b in batches.values() if b.get("status") == "completed")
        failed_batches = sum(1 for b in batches.values() if b.get("status") == "failed")
        total_files = sum(len(b.get("files", [])) for b in batches.values())
        done_files = sum(len(b.get("files", [])) for b in batches.values() if b.get("status") == "completed")

        duration_str = "00:00:00"
        if self._start_time:
            elapsed = int(time.time() - self._start_time)
            hrs, rem = divmod(elapsed, 3600)
            mins, secs = divmod(rem, 60)
            duration_str = f"{hrs:02d}:{mins:02d}:{secs:02d}"

        if total_batches > 0 and pending_batches == 0:
            self.dash_status_badge.configure(text="STATUS: SELESAI", fg_color=ACCENT_GREEN)
            self._append_log(f"✨ Seluruh upload selesai ({done_files}/{total_files} file). Browser ditutup & agent berhenti.\n")
            self._update_queue_ui(force=True)
            self._show_upload_completed_dialog(
                total_files=total_files,
                done_files=done_files,
                total_batches=total_batches,
                done_batches=completed_batches,
                failed_batches=failed_batches,
                duration=duration_str,
            )
        else:
            self.dash_status_badge.configure(text="STATUS: BERHENTI", fg_color=BG_CARD_ALT)
            self._append_log("⏹️ Agent berhenti\n")

    def _show_upload_completed_dialog(
        self,
        total_files: int,
        done_files: int,
        total_batches: int,
        done_batches: int,
        failed_batches: int,
        duration: str,
    ):
        dialog = ctk.CTkToplevel(self)
        dialog.title("Proses Upload Selesai")
        dialog.geometry("540x390")
        dialog.resizable(False, False)
        dialog.configure(fg_color=BG_MAIN)
        dialog.transient(self)
        dialog.grab_set()

        # Center on parent window
        self.update_idletasks()
        dx = max(0, self.winfo_x() + (self.winfo_width() - 540) // 2)
        dy = max(0, self.winfo_y() + (self.winfo_height() - 390) // 2)
        dialog.geometry(f"+{dx}+{dy}")

        card = ctk.CTkFrame(dialog, fg_color=BG_CARD, corner_radius=12, border_color=BORDER_COLOR, border_width=1)
        card.pack(fill="both", expand=True, padx=16, pady=16)

        # Top pill badge & title
        is_all_success = (failed_batches == 0)
        badge_color = "#064E3B" if is_all_success else "#78350F"
        badge_text_color = "#34D399" if is_all_success else "#FBBF24"
        badge_text = "SELESAI (100% SUKSES)" if is_all_success else f"SELESAI ({failed_batches} BATCH GAGAL)"

        header_row = ctk.CTkFrame(card, fg_color="transparent")
        header_row.pack(fill="x", padx=20, pady=(18, 4))

        ctk.CTkLabel(
            header_row,
            text=badge_text,
            fg_color=badge_color,
            text_color=badge_text_color,
            font=ctk.CTkFont(size=10, weight="bold"),
            corner_radius=6,
            padx=10,
            pady=3,
        ).pack(side="left")

        title_text = "Seluruh Proses Upload Selesai" if is_all_success else "Upload Selesai dengan Catatan"
        ctk.CTkLabel(
            card,
            text=title_text,
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=TEXT_MAIN,
        ).pack(anchor="w", padx=20, pady=(6, 2))

        subtitle_text = (
            "Semua tab browser otomatis ditutup dan agent background telah dihentikan secara aman."
            if is_all_success
            else f"Sebagian batch berhasil diunggah ({done_files}/{total_files} file). Browser telah ditutup."
        )
        ctk.CTkLabel(
            card,
            text=subtitle_text,
            font=ctk.CTkFont(size=12),
            text_color=TEXT_MUTED,
            justify="left",
            wraplength=480,
        ).pack(anchor="w", padx=20, pady=(0, 14))

        # Metrics 4-card grid
        metrics_frame = ctk.CTkFrame(card, fg_color=BG_MAIN, corner_radius=10, border_color=BORDER_COLOR, border_width=1)
        metrics_frame.pack(fill="x", padx=20, pady=(0, 14))
        metrics_frame.grid_columnconfigure((0, 1, 2, 3), weight=1)

        def make_metric(col, label, val, color):
            box = ctk.CTkFrame(metrics_frame, fg_color="transparent")
            box.grid(row=0, column=col, padx=6, pady=10, sticky="nsew")
            ctk.CTkLabel(box, text=label, font=ctk.CTkFont(size=10, weight="bold"), text_color=TEXT_DIM).pack()
            ctk.CTkLabel(box, text=val, font=ctk.CTkFont(size=15, weight="bold"), text_color=color).pack(pady=(2, 0))

        make_metric(0, "TOTAL FILE", f"{done_files}/{total_files}", ACCENT_GREEN if is_all_success else TEXT_MAIN)
        make_metric(1, "BATCH SUKSES", f"{done_batches}/{total_batches}", TEXT_MAIN)
        make_metric(2, "BATCH GAGAL", str(failed_batches), ACCENT_RED if failed_batches > 0 else TEXT_MUTED)
        make_metric(3, "TOTAL DURASI", duration, ACCENT_BLUE)

        # Drive Folder Info snippet
        drive_url = self.entry_drive_url.get().strip()
        if drive_url:
            drive_info_frame = ctk.CTkFrame(card, fg_color=BG_INPUT, corner_radius=8)
            drive_info_frame.pack(fill="x", padx=20, pady=(0, 14))
            drive_short = drive_url if len(drive_url) <= 52 else (drive_url[:49] + "...")
            ctk.CTkLabel(
                drive_info_frame,
                text=f"Tautan Drive: {drive_short}",
                font=ctk.CTkFont(size=11),
                text_color=TEXT_MUTED,
                anchor="w",
            ).pack(fill="x", padx=12, pady=7)

        # Action Buttons
        btn_row = ctk.CTkFrame(card, fg_color="transparent")
        btn_row.pack(fill="x", padx=20, pady=(0, 16), side="bottom")

        def do_close():
            dialog.destroy()

        def do_open_drive():
            if drive_url:
                webbrowser.open(drive_url)

        def do_retry():
            dialog.destroy()
            self._retry_failed()

        if failed_batches > 0:
            btn_retry = ctk.CTkButton(
                btn_row,
                text="Ulangi Batch Gagal",
                command=do_retry,
                fg_color=ACCENT_AMBER,
                hover_color="#D97706",
                font=ctk.CTkFont(size=12, weight="bold"),
                height=36,
                corner_radius=8,
            )
            btn_retry.pack(side="left", padx=(0, 8))

        if drive_url:
            btn_drive = ctk.CTkButton(
                btn_row,
                text="Buka Google Drive",
                command=do_open_drive,
                fg_color=ACCENT_BLUE,
                hover_color=ACCENT_BLUE_HOVER,
                font=ctk.CTkFont(size=12, weight="bold"),
                height=36,
                corner_radius=8,
            )
            btn_drive.pack(side="left", padx=(0, 8))

        btn_ok = ctk.CTkButton(
            btn_row,
            text="Selesai",
            command=do_close,
            fg_color=ACCENT_GREEN if is_all_success else BG_CARD_ALT,
            hover_color="#059669" if is_all_success else "#334155",
            font=ctk.CTkFont(size=12, weight="bold"),
            height=36,
            corner_radius=8,
        )
        btn_ok.pack(side="right", fill="x", expand=True)

    def _reset_queue(self):
        if self._running:
            messagebox.showwarning("Sedang Berjalan", "Hentikan upload terlebih dahulu sebelum mereset antrean.")
            return
        if messagebox.askyesno("Reset Antrean", "Kosongkan seluruh antrean batch?"):
            if STATE_FILE.exists():
                STATE_FILE.unlink()
            self._append_log("🔄 Antrean telah direset\n")
            self._update_queue_ui(force=True)

    def _retry_failed(self):
        from src.core.queue_manager import QueueManager

        count = QueueManager().retry_failed_batches()
        if count > 0:
            self._append_log(f"🔁 Mengembalikan {count} batch gagal ke antrean pending\n")
            messagebox.showinfo("Retry Berhasil", f"{count} batch gagal dikembalikan ke antrean pending.")
        else:
            messagebox.showinfo("Retry", "Tidak ada batch berstatus gagal.")
        self._update_queue_ui(force=True)

    def _append_log(self, text: str):
        def _insert():
            self.log_textbox.insert("end", text)
            if self._autoscroll:
                self.log_textbox.see("end")

            # Update dash preview snippet
            self.dash_log_preview.insert("end", text)
            lines = self.dash_log_preview.get("1.0", "end").splitlines()
            if len(lines) > 20:
                self.dash_log_preview.delete("1.0", f"{len(lines) - 15}.0")
            self.dash_log_preview.see("end")

        self.after(0, _insert)

    def _poll_status(self):
        if self._running and self._start_time:
            elapsed = int(time.time() - self._start_time)
            hrs, rem = divmod(elapsed, 3600)
            mins, secs = divmod(rem, 60)
            self.dash_status_badge.configure(text=f"STATUS: BERJALAN ({hrs:02d}:{mins:02d}:{secs:02d})")

        self._update_queue_ui()
        self.after(1500, self._poll_status)

    def _update_queue_ui(self, force: bool = False):
        state = load_state()
        batches = state.get("batches", {})

        total_files = sum(len(b.get("files", [])) for b in batches.values())
        done_files = sum(len(b.get("files", [])) for b in batches.values() if b.get("status") == "completed")
        pending_b = sum(1 for b in batches.values() if b.get("status") in ["pending", "retrying", "processing"])
        failed_b = sum(1 for b in batches.values() if b.get("status") == "failed")

        self.stat_total.configure(text=str(total_files))
        self.stat_done.configure(text=str(done_files))
        self.stat_pending.configure(text=str(pending_b))
        self.stat_failed.configure(text=str(failed_b))

        pct = (done_files / total_files) if total_files > 0 else 0
        self.dash_progress_bar.set(pct)

        # Update active worker states from running batches
        active_by_worker = {}
        for b_id, b in batches.items():
            if b.get("status") == "processing" and b.get("worker_id"):
                active_by_worker[b.get("worker_id")] = (b_id, len(b.get("files", [])))

        for i, w_data in self.worker_cards.items():
            wid = f"tab_{i}"
            if wid in active_by_worker:
                b_id, f_count = active_by_worker[wid]
                w_data["batch"].configure(text=f"{b_id} ({f_count} file)", text_color=TEXT_MAIN)
                w_data["badge"].configure(text="UPLOADING", fg_color=ACCENT_BLUE, text_color=TEXT_MAIN)
            elif not self._running:
                w_data["batch"].configure(text="Menunggu tugas...", text_color=TEXT_DIM)
                w_data["badge"].configure(text="OFFLINE", fg_color=BG_CARD_ALT, text_color=TEXT_MUTED)
            else:
                w_data["batch"].configure(text="Menunggu tugas...", text_color=TEXT_DIM)
                w_data["badge"].configure(text="IDLE", fg_color=BG_CARD_ALT, text_color=TEXT_MUTED)

        # Render Queue view list when queue tab is open
        if self._active_tab == "queue":
            query = self.queue_search_entry.get().strip().lower()
            filtered_items = []
            for b_id, b in batches.items():
                status = b.get("status", "pending")
                if self._queue_filter != "all" and status != self._queue_filter:
                    continue
                if query and query not in b_id.lower() and not any(query in f.lower() for f in b.get("files", [])):
                    continue
                filtered_items.append((b_id, b))

            sig = hash(tuple((b_id, b.get("status"), b.get("retry_count")) for b_id, b in filtered_items[:50]))
            if force or sig != self._last_queue_sig:
                self._last_queue_sig = sig
                for child in self.queue_scroll.winfo_children():
                    child.destroy()

                if not filtered_items:
                    ctk.CTkLabel(self.queue_scroll, text="Tidak ada batch yang sesuai filter.", text_color=TEXT_MUTED).pack(pady=20)
                else:
                    for b_id, b in filtered_items[:60]:
                        row = ctk.CTkFrame(self.queue_scroll, fg_color=BG_INPUT, corner_radius=8, height=36)
                        row.pack(fill="x", pady=2)
                        row.pack_propagate(False)

                        status = b.get("status", "pending")
                        if status == "completed":
                            badge_color, badge_text_color = ACCENT_GREEN, TEXT_MAIN
                        elif status == "processing":
                            badge_color, badge_text_color = ACCENT_AMBER, BG_MAIN
                        elif status == "failed":
                            badge_color, badge_text_color = ACCENT_RED, TEXT_MAIN
                        else:
                            badge_color, badge_text_color = BG_CARD_ALT, TEXT_MUTED

                        ctk.CTkLabel(row, text=b_id, font=ctk.CTkFont(family="Consolas", size=11, weight="bold"), text_color=TEXT_MAIN, width=160, anchor="w").pack(side="left", padx=(12, 6))
                        ctk.CTkLabel(row, text=f"{len(b.get('files', []))} berkas", font=ctk.CTkFont(size=11), text_color=TEXT_MUTED, width=110, anchor="w").pack(side="left", padx=6)

                        badge_lbl = ctk.CTkLabel(
                            row,
                            text=status.upper(),
                            fg_color=badge_color,
                            text_color=badge_text_color,
                            font=ctk.CTkFont(size=10, weight="bold"),
                            corner_radius=6,
                            width=100,
                            pady=2,
                        )
                        badge_lbl.pack(side="left", padx=6)

                        worker_info = b.get("worker_id") or ""
                        if b.get("error_message"):
                            worker_info += f" ({b.get('error_message')})"
                        ctk.CTkLabel(row, text=worker_info or "-", font=ctk.CTkFont(size=11), text_color=TEXT_DIM, anchor="w").pack(side="left", fill="x", expand=True, padx=6)

                        retry_cnt = b.get("retry_count", 0)
                        ctk.CTkLabel(row, text=f"{retry_cnt}x", font=ctk.CTkFont(size=11), text_color=TEXT_MUTED, width=70, anchor="center").pack(side="right", padx=(6, 12))

    def on_close(self):
        if self._running:
            self._stop_upload()
        self.destroy()


if __name__ == "__main__":
    app = GDriveLauncher()
    app.protocol("WM_DELETE_WINDOW", app.on_close)
    app.mainloop()
