# Bantukos AutoKomen Bot — Panduan Penggunaan

## Arsitektur Sistem

```
┌─────────────────────────────┐     ┌──────────────────────────┐
│  bantukos-autokomen-bot     │────▶│  bantukos-wa-bot         │
│  (Python / Playwright)      │     │  (Node.js / WA)          │
│                             │     │                          │
│  • Scan FB grup             │     │  • Auto-reply tamu       │
│  • Komen di post kos        │     │  • Admin commands        │
│  • Outreach ke pencari kos  │     │  • Notify API :3001      │
│  • bantukos.db (listing)    │     │  • Kirim ke owner kos    │
│  • outreach.db (leads)      │     │  • Kirim ke pencari kos  │
└─────────────────────────────┘     └──────────────────────────┘
```

---

## Setup Pertama

**1. Install dependencies:**
```bash
pip install -r requirements.txt
playwright install chromium
```

**2. Buat file `.env`:**
```bash
cp .env.example .env
# isi OPENAI_API_KEY
# isi BANTUKOS_DB_PATH → path ke bantukos.db dari bantukos-bot
# isi WA_NOTIFY_URL   → URL notify endpoint WA bot
```

**3. Copy session Facebook:**
```bash
cp ../bantukos-bot/data/fb_session.json data/fb_session.json
```

---

## Commands (CLI)

| Command | Keterangan |
|---------|-----------|
| `python3 main.py` | Mode terjadwal — scan tiap 30 menit + outreach tiap 60 menit |
| `python3 main.py scan` | Scan & komen sekali langsung |
| `python3 main.py outreach` | Outreach scan sekali langsung |
| `python3 main.py stats` | Lihat statistik komentar hari ini |

---

## Fitur 1 — Auto-Komen FB

Scan grup Facebook → temukan post "cari kos" → generate komentar via AI → posting.

**Batas keamanan (config.py):**

| Setting | Default | Keterangan |
|---------|---------|-----------|
| `MAX_COMMENTS_PER_DAY` | 8 | Max komentar per hari |
| `MIN_DELAY_AFTER_POST` | 15 | Menit tunggu sebelum komentar |
| `SCAN_INTERVAL_MINUTES` | 30 | Cek grup tiap X menit |

---

## Fitur 2 — SupportKos Outreach

Scan grup FB untuk **pencari kos** (bukan poster listing), generate draft DM personal, kirim notif ke owner via WA bot.

### Alur

```
Scan grup (tiap 60 menit)
  │
  ├─ Pass 1: semua POST UTAMA
  │    Posting "cari kos di kerobokan"?
  │    ├─ Ada nomor WA di post → notif WA + tombol kirim
  │    └─ Tidak ada WA → notif WA + instruksi DM FB
  │
  └─ Pass 2: KOMENTAR semua post
       Komentar "ada yang di kerobokan gak?"?
       └─ Notif WA + instruksi DM FB ke komentator
```

### Format Notif yang Masuk ke WA

**Kalau pencari kos punya nomor WA di postingan:**
```
🎯 Lead SupportKos — Via WA Langsung!

👤 Nama  : Sari Dewi
📍 Lokasi: Kerobokan
📱 WA    : https://wa.me/628xxx

📝 Post asli:
"Cari kos daerah kerobokan dong budget 1-1.5jt"

🔗 Lihat post: https://facebook.com/...

✍️ Draft pesan WA:
---
[draft pesan yang siap dikirim]
---

👉 Balas: kirim outreach abc123
   atau klik link WA → paste draft manual
```

**Kalau tidak ada WA (FB DM) atau dari komentar:**
```
💬 Lead SupportKos — Komentar FB / FB DM

👤 Nama  : ...
📍 Lokasi: ...
🔗 Profil FB: ...

[isi komentar/post]

✍️ Draft DM FB:
---[draft]---

👉 Buka profil FB di atas → kirim DM
```

### Tombol Kirim (hanya untuk lead yang ada WA)

Balas notif dengan:
```
lead kirim abc123
```
Bot langsung kirim draft ke WA pencari kos. Konfirmasi terkirim muncul sebagai reply.

> **Catatan:** `lead kirim` = kirim ke **pencari kos** (client).
> Berbeda dengan `owner kirim` = kirim ke **owner kos** di database.

### Batas harian
```
MAX_LEADS_PER_DAY = 10  (env var, default 10)
```

---

## WA Bot — Admin Commands

Semua command dikirim ke **Saved Messages** bot (self-chat).

### Data Listing (Owner Kos)
| Command | Keterangan |
|---------|-----------|
| `list` | 15 listing terbaru |
| `cari sesetan` | Cari listing by keyword |
| `#34` | Detail listing #34 |
| `stat` | Statistik database |

### Owner Kos
| Command | Keterangan |
|---------|-----------|
| `owner list` | 15 listing terbaru |
| `owner cek` | Lihat owner yang belum dihubungi |
| `owner preview` | Contoh pesan yang akan dikirim ke owner |
| `owner kirim` | Kirim WA ke owner kos (max 10 per run) |
| `owner add 08xxx` | Tambah nomor owner manual ke daftar intercept |
| `owner verify #34` | Tandai listing #34 masih kosong |
| `owner flow` | Panduan alur lengkap cek owner |

### Lead (Pencari Kos)
| Command | Keterangan |
|---------|-----------|
| `lead kirim <id>` | Kirim draft WA ke pencari kos (id ada di notif) |

### Lainnya
| Command | Keterangan |
|---------|-----------|
| `help` | Tampilkan semua command |
| `stat` | Statistik database |
| `cari <keyword>` | Cari listing by keyword |
| `#34` | Detail listing #34 |

---

## Disk Monitor

Cron job di server (`/usr/local/bin/disk_monitor.sh`) jalan tiap 30 menit.
Kalau disk > 85% → kirim WA alert ke `OWNER_NOTIFY_NUMBER` (dengan sound di iPhone).

Untuk trigger manual:
```bash
/usr/local/bin/disk_monitor.sh
```

---

## Notifikasi WA — Dua Jalur

| Jenis | Tujuan | Sound iPhone |
|-------|--------|-------------|
| Outreach lead | Saved Messages bot | ❌ (silent) |
| Disk alert / system | `OWNER_NOTIFY_NUMBER` | ✅ (ada sound) |

Set `OWNER_NOTIFY_NUMBER` di `.env` WA bot → nomor pribadi yang berbeda dari nomor bot.

---

## Lihat Log di Server

```bash
docker logs -f --tail=100 CONTAINER_ID
docker exec -it CONTAINER_ID python3 main.py stats
```
