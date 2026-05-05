# Bantukos AutoKomen Bot — Panduan Penggunaan

## Cara Kerja

```
Scan grup Facebook → Temukan post "cari kos" → Cocokkan dengan listing di DB
→ Generate komentar via AI → Posting komentar → Catat di DB
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
```

**3. Copy session Facebook dari bantukos-bot:**
```bash
cp ../bantukos-bot/data/fb_session.json data/fb_session.json
```
Atau export ulang session khusus akun bot (direkomendasikan):
```bash
cd ../bantukos-bot
python3 facebook.py --export-session
cp data/fb_session.json ../bantukos-autokomen-bot/data/fb_session.json
```

---

## Commands

| Command | Keterangan |
|---------|-----------|
| `python3 main.py` | Mode terjadwal — scan tiap 30 menit |
| `python3 main.py scan` | Scan sekali langsung |
| `python3 main.py stats` | Lihat statistik komentar hari ini |

---

## Batas Keamanan (config.py)

| Setting | Default | Keterangan |
|---------|---------|-----------|
| `MAX_COMMENTS_PER_DAY` | 8 | Max komentar per hari |
| `MIN_DELAY_AFTER_POST` | 15 | Menit tunggu sebelum komentar |
| `SCAN_INTERVAL_MINUTES` | 30 | Cek grup tiap X menit |

> Jangan naikkan `MAX_COMMENTS_PER_DAY` terlalu tinggi — risiko akun diblokir Facebook.

---

## Menambah Grup Facebook

Edit `config.py`, bagian `FACEBOOK_GROUPS`:
```python
FACEBOOK_GROUPS = [
    "https://www.facebook.com/groups/ID_GRUP_1",
    "https://www.facebook.com/groups/ID_GRUP_2",
]
```

---

## Contoh Komentar yang Di-generate

```
Haii Dinda, kebetulan ada kos di Canggu nih! Harga sekitar 2jt/bulan,
AC + wifi + kamar mandi dalam. Kalau minat bisa PM atau cek @bantukos 😊
```

Tiap komentar berbeda karena di-generate AI berdasarkan:
- Nama poster
- Lokasi yang dicari
- Listing yang cocok dari database

---

## Lihat Log di Server

```bash
docker exec -it CONTAINER_ID python3 main.py stats
docker logs -f --tail=100 CONTAINER_ID
```
