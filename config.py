import os
from dotenv import load_dotenv
load_dotenv()

# ── Facebook ────────────────────────────────────────────────────────────────
FB_SESSION_PATH = os.getenv("FB_SESSION_PATH", "data/fb_session.json")

# Kosongkan list ini untuk auto-scan semua grup yang diikuti akun bot.
# Isi dengan URL spesifik kalau mau batasi ke grup tertentu saja.
FACEBOOK_GROUPS = []

# ── Database ─────────────────────────────────────────────────────────────────
DB_PATH          = "data/autokomen.db"
BANTUKOS_DB_PATH = os.getenv("BANTUKOS_DB_PATH", "../bantukos-bot/data/bantukos.db")

# ── Outreach (SupportKos) ─────────────────────────────────────────────────────
WA_NOTIFY_URL      = os.getenv("WA_NOTIFY_URL", "http://bantukos-wa-bot:3001/notify")
MAX_LEADS_PER_DAY  = int(os.getenv("MAX_LEADS_PER_DAY", "10"))

# ── Keamanan — batas harian ──────────────────────────────────────────────────
MAX_COMMENTS_PER_DAY  = 8    # max komentar per hari
MIN_DELAY_AFTER_POST  = 3    # menit — tunggu sebelum komentar (agar tidak terlalu cepat)
SCAN_INTERVAL_MINUTES = 30   # cek grup tiap X menit

# ── OpenAI ───────────────────────────────────────────────────────────────────
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

# ── Kata kunci post yang MENCARI kos ────────────────────────────────────────
SEEKING_KEYWORDS = [
    # Aktif mencari — kos & kost
    "cari kos", "nyari kos", "nari kos", "cari kost", "nyari kost",
    "cari kamar", "nyari kamar", "cari kamar kost", "cari kamar kos",
    "cari kontrakan", "nyari kontrakan", "cari tempat tinggal",
    "butuh kos", "butuh kost", "mau ngekos", "mau ngekost",
    "mau kos", "mau kost", "mau sewa kamar", "mau sewa kos", "mau sewa kost",
    "mau ngontrak", "cari ngontrak",
    # Belum dapat
    "belum dapat kos", "belum dapat kost", "belum dapet kos", "belum dapet kost",
    "ngak dapat kos", "ngak dapat kost", "nggak dapat kos", "nggak dapat kost",
    "gak dapat kos", "gak dapat kost", "tidak dapat kos", "tidak dapat kost",
    "susah cari kos", "susah cari kost", "susah nyari kos", "susah nyari kost",
    "sudah lama cari", "lama cari kos", "lama nyari kos",
    # Minta rekomendasi / info
    "ada yang tau kos", "ada yang tau kost", "ada info kos", "ada info kost",
    "rekomendasi kos", "rekomendasi kost", "info kos", "info kost",
    "tolong info kos", "tolong info kost", "bantu cari kos", "bantu cari kost",
    "ada yang punya kos", "ada yang punya kost",
    "ada kos kosong", "ada kost kosong", "ada kamar kosong", "ada kontrakan kosong",
    # Pola lokasi
    "kos daerah", "kost daerah", "kos di daerah", "kost di daerah",
    "kos sekitar", "kost sekitar", "kos area", "kost area",
    "kontrakan daerah", "kontrakan sekitar",
    # Inggris
    "looking for kos", "looking for kost", "looking for room",
    "need a room", "need room", "find a room",
]

# ── Area Bali yang dikenali ──────────────────────────────────────────────────
BALI_AREAS = [
    # Area utama
    "canggu", "seminyak", "kuta", "legian", "denpasar", "sanur",
    "ubud", "jimbaran", "nusa dua", "ungasan", "pecatu", "tabanan",
    "gianyar", "badung", "mengwi", "kerobokan",
    # Denpasar — area populer
    "renon", "sesetan", "gatsu", "gatot subroto", "monang maning",
    "imam bonjol", "panjer", "kesiman", "sidakarya", "padangsambian",
    "pemogan", "tohpati", "penatih", "batubulan", "tonja",
    # Denpasar — area lain
    "ubung", "peguyangan", "tegal", "sumerta", "dangin puri",
    "dauh puri", "denbar", "densel", "denut", "denbarat",
    "denpasar barat", "denpasar selatan", "denpasar utara", "denpasar timur",
    # Badung & sekitar
    "berawa", "cemagi", "pererenan", "echo beach", "batu bolong",
    "dalung", "abianbase", "tibubeneng", "munggu", "buduk",
    "penarungan", "abiansemal", "sading", "lukluk", "kapal",
    # Lain
    "bypass", "ngurah rai", "sunset road", "teuku umar",
    "gunung agung", "cargo", "marlboro",
]
