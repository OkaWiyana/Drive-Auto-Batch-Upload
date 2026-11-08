# GDrive Auto Uploader (Multi-Tab Batch Worker) 🚀

Aplikasi desktop cerdas berbasis Python dan otomatisasi browser paralel untuk mengunggah (upload) ribuan file ke **1 folder Google Drive** secara massal dengan sistem **multi-tab** ("nyicil-nyicil di banyak tab secara bersamaan").

---

## 💡 Mengapa Sistem Multi-Tab?

Mengunggah ribuan file (misalnya 5.000 - 50.000 foto/dokumen) sekaligus ke Google Drive web melalui 1 tab browser seringkali menyebabkan:
- Browser freeze/macet kehabisan RAM.
- Upload tersendat jika ada 1 file yang gagal atau internet drop.
- Quota API yang rumit dan terbatas jika menggunakan Google Drive API / Cloud Console.

**Solusi Aplikasi Ini:**
Aplikasi ini membagi file lokal ke dalam antrean batch (misal 50 file per batch) dan membuka beberapa tab browser secara paralel (misal 3–5 tab) ke folder tujuan yang sama:
1. **Tab 1** memproses Batch 1 (File 1–50).
2. **Tab 2** memproses Batch 2 (File 51–100).
3. **Tab 3** memproses Batch 3 (File 101–150).
4. Saat salah satu tab selesai, tab tersebut langsung mengambil batch berikutnya dari antrean secara otomatis tanpa menunggu tab lain!
5. **Resume Otomatis**: Jika Anda menjeda aplikasi atau laptop dimatikan, progres tersimpan di `state.json` sehingga Anda dapat melanjutkan kapan saja tanpa mengulang dari awal.

---

## ✨ Fitur Unggulan

- **🖥️ Antarmuka GUI Modern (CustomTkinter):** Tampilan bertema gelap yang intuitif dengan metrik real-time, progress bar, daftar batch, dan live log konsol.
- **⚡ Upload Multi-Tab Paralel:** Mengatur jumlah tab (1 s.d. 10 tab) sesuai spek PC dan kecepatan internet.
- **🔑 Sesi Akun Google Persisten:** Tombol **"Login Google"** membuka browser asli (Chrome/Edge) agar Anda login sekali saja secara manual (bebas blokir bot / 2FA). Cookies dan sesi tersimpan permanen di folder `gdrive_profile`.
- **📂 Manajemen Antrean Cerdas (`state.json`):**
  - Mencegah upload duplikat.
  - Memulihkan batch yang belum selesai secara otomatis (*zombie recovery*).
  - Percobaan ulang otomatis (*auto-retry*) jika koneksi tersendat.
- **🛡️ Penanganan File Duplikat:** Opsi otomatis memilih *Simpan Keduanya (Keep Separate)* atau *Ganti File Lama (Replace)* jika Drive mendeteksi nama file yang sama.
- **👁️ Auto File Watcher (Opsional):** Memindai folder secara berkala atau mendeteksi file baru yang dimasukkan ke folder sumber saat upload sedang berjalan.

---

## 📁 Struktur Proyek

```
Drive batch/
├── run.py                 # Entry point utama (menjalankan GUI atau Worker)
├── agent_worker.py        # Background engine upload paralel
├── .env.example           # Contoh konfigurasi
├── requirements.txt       # Daftar pustaka Python
├── README.md              # Dokumentasi lengkap
├── public/                # Aset ikon dan logo
├── src/
│   ├── core/
│   │   ├── config.py       # Pengaturan konfigurasi (.env)
│   │   ├── queue_manager.py# Pengelola antrean batch & status state.json
│   │   ├── scanner.py      # Scanner folder lokal & watchdog
│   │   └── scheduler.py    # Penjadwal multi-tab paralel
│   ├── browser/
│   │   ├── browser_pool.py # Manajemen tab browser persistent
│   │   ├── gdrive_uploader.py # Logika interaksi DOM Google Drive
│   │   └── auth_helper.py  # Helper login akun Google
│   └── ui/
│       └── app.py          # Antarmuka CustomTkinter
```

---

## 🚀 Panduan Penggunaan

### 1. Prasyarat Sistem
- Python 3.8 s.d. 3.13
- Google Chrome atau Microsoft Edge terpasang di komputer Anda.

### 2. Instalasi Dependensi
Buka terminal / PowerShell di folder proyek ini dan jalankan:
```bash
pip install -r requirements.txt
```

### 3. Menjalankan Aplikasi
Cukup jalankan perintah:
```bash
python run.py
```

### 4. Langkah Penggunaan di Aplikasi:
1. **Langkah 1: Login Akun Google**
   - Klik tombol **"🔑 Buka Browser Login Google"** di aplikasi.
   - Jendela browser Chrome/Edge akan terbuka menuju Google Drive.
   - Masukkan email, kata sandi, dan selesaikan verifikasi 2FA jika diminta.
   - Setelah masuk ke halaman Google Drive, tutup jendela browser tersebut. Status akun di aplikasi akan otomatis berubah menjadi: `✅ Profil Sesi Tersimpan`.
2. **Langkah 2: Tentukan Folder & Link Drive**
   - Klik **"Pilih Folder..."** untuk memilih folder file di komputer Anda.
   - Tempel (*paste*) tautan folder Google Drive tujuan di kolom input (contoh: `https://drive.google.com/drive/folders/1abc...`).
3. **Langkah 3: Atur Kapasitas Worker**
   - **Jumlah Tab Paralel:** Mulai dengan 3–5 tab.
   - **Ukuran Batch:** 25–50 file per tab.
4. **Langkah 4: Mulai Upload**
   - Klik **"🚀 Mulai Upload"**.
   - Tab-tab browser akan otomatis terbuka ke folder target dan mengunggah batch file secara serempak!

---

## 💡 Tips & Rekomendasi Performa

| Parameter | Koneksi Standar | Koneksi Cepat (Fiber / LAN) |
|---|---|---|
| **Jumlah Tab (`MAX_WORKERS`)** | 2 – 3 Tab | 4 – 8 Tab |
| **Ukuran Batch (`BATCH_SIZE`)** | 20 – 50 File | 50 – 100 File |

- **Jangan gunakan terlalu banyak tab jika koneksi terbatas:** Menggunakan 10 tab pada koneksi lambat akan membagi bandwidth ke terlalu banyak file sekaligus, yang dapat memicu timeout upload dari Google Drive.
- **Jeda & Lanjut:** Anda dapat menekan **"⏸️ Hentikan"** kapan saja. Antrean yang tersisa akan tersimpan di `state.json` dan bisa dilanjutkan kembali dengan mengklik **"🚀 Mulai Upload"**.
