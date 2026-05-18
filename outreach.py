"""
SupportKos Outreach Pipeline — Feature 1.

Priority:
  1. Main post yang ada nomor WA → notif ke owner: hubungi via WA langsung
  2. Main post tanpa nomor WA   → notif ke owner: kirim FB DM
  3. Komentar di post yang seeking → notif ke owner: kirim FB DM ke komentator
"""
import re
import os
import time
import random
import hashlib
import sqlite3
import requests
from datetime import datetime
from playwright.sync_api import sync_playwright

from config import (
    FB_SESSION_PATH, FACEBOOK_GROUPS, BALI_AREAS, OPENAI_API_KEY,
    WA_NOTIFY_URL, MAX_LEADS_PER_DAY, BANTUKOS_DB_PATH,
)
from scanner import _is_seeking, _get_post_text, _post_id_from_url, discover_group_urls

OUTREACH_DB_PATH = os.getenv("OUTREACH_DB_PATH", "data/outreach.db")


# ── Database ──────────────────────────────────────────────────────────────────

def init_outreach_db():
    conn = sqlite3.connect(OUTREACH_DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS outreach_leads (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            fb_post_id   TEXT UNIQUE,
            post_url     TEXT,
            poster_name  TEXT,
            profile_url  TEXT,
            wa_number    TEXT,
            location     TEXT,
            post_text    TEXT,
            source_type  TEXT,
            dm_draft     TEXT,
            notified_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()


def already_notified(fb_post_id: str) -> bool:
    conn = sqlite3.connect(OUTREACH_DB_PATH)
    row = conn.execute(
        "SELECT id FROM outreach_leads WHERE fb_post_id = ?", (fb_post_id,)
    ).fetchone()
    conn.close()
    return row is not None


def count_leads_today() -> int:
    today = datetime.now().strftime("%Y-%m-%d")
    conn = sqlite3.connect(OUTREACH_DB_PATH)
    count = conn.execute(
        "SELECT COUNT(*) FROM outreach_leads WHERE notified_at >= ?",
        (today + " 00:00:00",)
    ).fetchone()[0]
    conn.close()
    return count


def save_lead(fb_post_id, post_url, poster_name, profile_url, wa_number,
              location, post_text, source_type, dm_draft):
    conn = sqlite3.connect(OUTREACH_DB_PATH)
    try:
        conn.execute("""
            INSERT INTO outreach_leads
                (fb_post_id, post_url, poster_name, profile_url, wa_number,
                 location, post_text, source_type, dm_draft)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (fb_post_id, post_url, poster_name, profile_url, wa_number,
              location, post_text, source_type, dm_draft))
        conn.commit()
    except sqlite3.IntegrityError:
        pass
    finally:
        conn.close()


# ── Phone / WA number extraction ─────────────────────────────────────────────

def _normalize_phone(num: str) -> str:
    num = re.sub(r'[^\d]', '', num)
    if num.startswith('0'):
        num = '62' + num[1:]
    return num


def _extract_wa_number(text: str) -> str:
    """
    Ekstrak nomor WA dari teks post. Return string '628xxx' atau '' jika tidak ada.
    Prioritaskan nomor yang disebutkan dekat kata WA/WhatsApp/hubungi.
    """
    # Cari nomor yang disebut dekat keyword WA
    wa_ctx = re.search(
        r'(?:wa|whatsapp|wp|hubungi|kontak|contact|chat|ping|dm)[\s:.\-]*'
        r'(\+?(?:62|0)[0-9][\d\s\-\.]{7,14})',
        text, re.IGNORECASE
    )
    if wa_ctx:
        return _normalize_phone(wa_ctx.group(1))

    # Fallback: nomor panjang (10–14 digit) dimanapun
    m = re.search(r'(\+?62[\s\-]?\d{3}[\s\-]?\d{3,5}[\s\-]?\d{3,5}|0\d{2,3}[\s\-]?\d{3,5}[\s\-]?\d{3,5})', text)
    if m:
        num = _normalize_phone(m.group(1))
        if 10 <= len(num) <= 15:
            return num
    return ''


# ── FB DOM helpers ────────────────────────────────────────────────────────────

def _extract_poster_info(page) -> tuple[str, str]:
    """Return (poster_name, profile_url) dari halaman post yang sudah dibuka."""
    result = page.evaluate("""
        () => {
            const selectors = [
                'h2 a[href*="facebook.com"]',
                'h3 a[href*="facebook.com"]',
                'strong a[href*="facebook.com"]',
                '[data-ad-rendering-role="profile_name"] a',
                'a[role="link"][href*="/user/"]',
                'a[role="link"][href*="profile.php"]',
            ];
            for (const sel of selectors) {
                const el = document.querySelector(sel);
                if (el) {
                    const name = (el.innerText || el.textContent || '').trim();
                    let href = el.href || '';
                    try {
                        const u = new URL(href);
                        if (u.searchParams.has('id')) {
                            href = u.origin + u.pathname + '?id=' + u.searchParams.get('id');
                        } else {
                            href = u.origin + u.pathname.replace(/\\/posts.*/, '').replace(/\\?.*/, '');
                        }
                    } catch(e) {}
                    if (name && href.includes('facebook.com')) return [name, href];
                }
            }
            return ['', ''];
        }
    """)
    return (result[0] or '', result[1] or '') if result else ('', '')


def _extract_comments_info(page) -> list[dict]:
    """
    Return list of {text, commenter_name, profile_url, comment_url} dari komentar di halaman.
    """
    return page.evaluate("""
        () => {
            const results = [];
            // Expand komentar kalau ada tombolnya
            document.querySelectorAll('[aria-label*="comment" i][role="button"]').forEach(b => {
                try { b.click(); } catch(e) {}
            });

            document.querySelectorAll('[data-commentid], [aria-label*="Comment by"]').forEach(el => {
                const textEl = el.querySelector('div[dir="auto"]');
                const text = textEl ? textEl.innerText.trim() : '';
                if (!text || text.length < 15 || text.length > 600) return;

                const nameEl = el.querySelector('a[href*="facebook.com"] span, strong a');
                const name = nameEl ? (nameEl.innerText || nameEl.textContent || '').trim() : '';
                const profileEl = el.querySelector('a[href*="facebook.com"]:not([href*="/posts/"])');
                let profileUrl = profileEl ? profileEl.href : '';
                try {
                    const u = new URL(profileUrl);
                    if (u.searchParams.has('id')) {
                        profileUrl = u.origin + u.pathname + '?id=' + u.searchParams.get('id');
                    } else {
                        profileUrl = u.origin + u.pathname.replace(/\\/posts.*/, '').replace(/\\?.*/, '');
                    }
                } catch(e) {}

                // Coba dapatkan permalink komentar
                const permalinkEl = el.querySelector('a[href*="/permalink/"], a[href*="comment_id="]');
                const commentUrl = permalinkEl ? permalinkEl.href : '';

                if (text) results.push({ text, name, profileUrl, commentUrl });
            });
            return results.slice(0, 25);
        }
    """)


def _extract_location(text: str) -> str:
    text_lower = text.lower()
    for area in BALI_AREAS:
        if area in text_lower:
            return area.title()
    return "Bali"


# ── Listing lookup ────────────────────────────────────────────────────────────

def _clean_price(price: str) -> str:
    """Normalisasi harga ke format ringkas. Return '' jika tidak valid."""
    p = (price or '').strip()
    if not p or p in ('N/A', 'Hubungi pemilik', '-'):
        return ''
    # Sudah bersih: "Rp 1.2jt/bln" atau "Rp 800rb/bln"
    if p.startswith('Rp ') and ('/bln' in p or '/bulan' in p):
        return p.replace('/bulan', '/bln')
    # Angka mentah: "2jt", "1.5jt", "800k", "1200000" dll
    import re as _re
    m = _re.search(r'([\d][.,\d]*)\s*(jt|juta|rb|ribu|k)?', p.lower().replace(' ', ''))
    if not m:
        return ''
    try:
        num = float(m.group(1).replace(',', '.'))
        suffix = (m.group(2) or '').lower()
        if 'jt' in suffix or 'juta' in suffix:
            amt = int(num * 1_000_000)
        elif suffix in ('rb', 'ribu', 'k'):
            amt = int(num * 1_000)
        else:
            amt = int(num * 1_000_000) if num < 10 else int(num * 1_000) if num < 10_000 else int(num)
        if not (400_000 <= amt <= 8_000_000):
            return ''
        if amt >= 1_000_000:
            label = f"{amt/1_000_000:.1f}".rstrip('0').rstrip('.')
            return f"Rp {label}jt/bln"
        return f"Rp {amt // 1000}rb/bln"
    except (ValueError, TypeError):
        return ''


_ADMIN_SUFFIXES = re.compile(
    r',?\s*(Bali|Badung|Gianyar|Tabanan|Denpasar\s*(Barat|Selatan|Utara|Timur)?|'
    r'Denbar|Densel|Denut|Kabupaten|Kota|Indonesia)\s*$',
    re.IGNORECASE,
)
_STREET_RE = re.compile(
    r'((?:jl\.?|jalan|gg\.?|gang|perumahan|komplek|dkt\.?|dekat|belakang|depan|sebelah)'
    r'[\w\s\.,/-]{3,40})',
    re.IGNORECASE,
)


def _extract_street_detail(location: str, raw_text: str, base_area: str) -> str:
    """
    Coba ekstrak detail lokasi spesifik (jalan/landmark).
    Return nama area + detail kalau ada, atau nama area saja.
    """
    # Hilangkan suffix administratif dari location field
    loc_clean = _ADMIN_SUFFIXES.sub('', location).strip().strip(',').strip()

    # Kalau location sudah punya info jalan/gang/dekat — pakai itu
    if _STREET_RE.search(loc_clean):
        return loc_clean[:60]

    # Coba cari dari raw_text: ambil 1 kalimat yang punya kata kunci lokasi detail
    if raw_text:
        for line in raw_text.splitlines():
            line = line.strip()
            if not line or len(line) > 120:
                continue
            if base_area.lower() not in line.lower():
                continue
            m = _STREET_RE.search(line)
            if m:
                detail = m.group(1).strip().rstrip('.,').strip()
                return f"{base_area} ({detail[:40]})"

    # Tidak ada detail — kembalikan nama area saja (bukan "Kerobokan, Badung")
    # Kalau loc_clean sama dengan atau mengandung base_area, pakai base_area
    if base_area.lower() in loc_clean.lower():
        return base_area
    return loc_clean or base_area


def _get_listings_for_area(location: str, limit: int = 3) -> list[dict]:
    """
    Ambil listing dari bantukos.db dengan:
    - Lokasi detail (jalan/landmark) jika ada, otherwise nama area saja
    - Harga bersih
    - Nomor WA/kontak owner
    """
    try:
        conn = sqlite3.connect(BANTUKOS_DB_PATH)
        area_kw = location.lower().split()[0] if location else ''
        rows = conn.execute("""
            SELECT location, price, COALESCE(contact,'') as contact,
                   COALESCE(substr(raw_text,1,600),'') as raw_text
            FROM posts
            WHERE status IN ('captioned', 'posted')
              AND LOWER(location) LIKE ?
              AND price IS NOT NULL AND price != ''
              AND price NOT LIKE '%Hubungi%'
              AND price NOT LIKE '%N/A%'
              AND location NOT LIKE '%Bali%'
            ORDER BY RANDOM()
            LIMIT 30
        """, (f'%{area_kw}%',)).fetchall()
        conn.close()

        results = []
        seen_locs = set()
        for loc_raw, price_raw, contact_raw, raw_text in rows:
            if not loc_raw:
                continue
            clean_p = _clean_price(price_raw)
            if not clean_p:
                continue

            loc_display = _extract_street_detail(loc_raw, raw_text, location)
            loc_key = loc_display.lower().strip()
            if loc_key in seen_locs:
                continue
            seen_locs.add(loc_key)

            # Ambil nomor WA dari contact field
            wa = ''
            if contact_raw:
                wa_m = re.search(r'(\+?62[\d\s-]{8,14}|0[\d\s-]{9,13})', contact_raw)
                if wa_m:
                    wa = re.sub(r'[\s-]', '', wa_m.group(1))
                    if wa.startswith('0'):
                        wa = '62' + wa[1:]

            results.append({'location': loc_display, 'price': clean_p, 'wa': wa})
            if len(results) >= limit:
                break
        return results
    except Exception as e:
        print(f"⚠️ Gagal ambil listing untuk draft: {e}")
        return []


# ── DM Draft Generator ────────────────────────────────────────────────────────

BANTUKOS_URL = "https://bantukos.com/listings"


_CLOSING = (
    "kalo mau lihat area lain, bisa cek aja di bantukos.com/listings\n\n"
    "btw, saya bukan calo ya kak, harga yang saya infokan real dari owner kost, "
    "saya disini cuman bantu nawarin aja, atau kalo kakak butuh bantuan — "
    "mungkin kayak gak ada waktu buat cek kost sebelum DP, atau lagi diluar kota — aku bisa bantu 🙏"
)


def _format_listings_block(listings: list[dict]) -> str:
    if not listings:
        return ''
    lines = []
    for l in listings:
        line = f"• {l['location']} — {l['price']}"
        if l.get('wa'):
            line += f" (WA owner: {l['wa']})"
        lines.append(line)
    return '\n'.join(lines)


def generate_dm_draft(poster_name: str, post_text: str, location: str, via_wa: bool = False) -> str:
    first_name = poster_name.split()[0] if poster_name else ""
    name_part  = f"Kak {first_name}" if first_name else "Kak"
    loc        = location or "Bali"

    listings       = _get_listings_for_area(loc)
    listings_block = _format_listings_block(listings)

    # Bagian pembuka (listing) — OpenAI untuk nada natural, fallback kalau gagal
    if listings_block:
        listing_intro = f"Ada beberapa yang lagi kosong di {loc}:\n{listings_block}"
    else:
        listing_intro = f"Bisa cek listing kos di {loc} di bantukos.com/listings ya."

    if not OPENAI_API_KEY:
        opener = f"Halo {name_part}, kebetulan tau ada kos di {loc} nih 👋\n\n{listing_intro}"
        return f"{opener}\n\n{_CLOSING}"

    try:
        from openai import OpenAI
        client = OpenAI(api_key=OPENAI_API_KEY)
        prompt = f"""Kamu seorang teman yang genuinely mau bantu orang cari kos.

Seseorang bernama "{name_part}" lagi cari kos di {loc}.
Post mereka: "{post_text[:200]}"

Tulis HANYA bagian pembuka pesannya saja (2-3 kalimat): sapaan natural + sebutkan listing di bawah ini secara apa adanya:

{listing_intro}

Aturan:
- Santai, kayak teman, bukan agen
- Sebutkan listing di atas apa adanya (lokasi + harga + WA owner kalau ada)
- Bahasa gaul/sehari-hari
- JANGAN tambahkan penutup atau ajakan apapun — bagian itu sudah ditulis terpisah
- Tulis isi pesan saja, tanpa tanda kutip"""

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=200,
            temperature=1.0,
        )
        opener = response.choices[0].message.content.strip().strip('"').strip("'")
        return f"{opener}\n\n{_CLOSING}"
    except Exception as e:
        print(f"⚠️ OpenAI gagal, pakai template: {e}")
        opener = f"Halo {name_part}, kebetulan tau ada kos di {loc} nih 👋\n\n{listing_intro}"
        return f"{opener}\n\n{_CLOSING}"


# ── WA Notify ─────────────────────────────────────────────────────────────────

def notify_owner_wa(
    poster_name: str,
    profile_url: str,
    post_url: str,
    post_text: str,
    dm_draft: str,
    location: str,
    wa_number: str = '',
    source_type: str = 'post',   # 'post' | 'comment'
) -> bool:
    short_post = post_text[:180].replace('\n', ' ')
    first_name = poster_name.split()[0] if poster_name else '?'

    if wa_number:
        # Prioritas: ada nomor WA → hubungi langsung via WA
        wa_link = f"https://wa.me/{wa_number}"
        message = (
            f"🎯 *Lead SupportKos — Via WA Langsung!*\n\n"
            f"👤 Nama  : {poster_name or '?'}\n"
            f"📍 Lokasi: {location}\n"
            f"📱 WA    : {wa_link}\n\n"
            f"📝 *Post asli:*\n_{short_post}_\n\n"
            f"🔗 Lihat post: {post_url}\n\n"
            f"✍️ *Draft pesan WA:*\n"
            f"---\n{dm_draft}\n---\n\n"
            f"👉 Klik link WA di atas → paste draft"
        )
    elif source_type == 'comment':
        # Komentar seeking — DM via FB ke komentator
        message = (
            f"💬 *Lead SupportKos — Komentar FB*\n\n"
            f"👤 Nama  : {poster_name or '?'}\n"
            f"📍 Lokasi: {location}\n"
            f"🔗 Profil FB: {profile_url or '(tidak terdeteksi)'}\n\n"
            f"💬 *Komentar:*\n_{short_post}_\n\n"
            f"🔗 Lihat komentar: {post_url}\n\n"
            f"✍️ *Draft DM FB:*\n"
            f"---\n{dm_draft}\n---\n\n"
            f"👉 Buka profil FB → kirim DM"
        )
    else:
        # Post tanpa nomor WA — DM via FB
        message = (
            f"🎯 *Lead SupportKos — FB DM*\n\n"
            f"👤 Nama  : {poster_name or '?'}\n"
            f"📍 Lokasi: {location}\n"
            f"🔗 Profil FB: {profile_url or '(tidak terdeteksi)'}\n\n"
            f"📝 *Post asli:*\n_{short_post}_\n\n"
            f"🔗 Lihat post: {post_url}\n\n"
            f"✍️ *Draft DM FB:*\n"
            f"---\n{dm_draft}\n---\n\n"
            f"👉 Buka profil FB → kirim DM"
        )

    try:
        resp = requests.post(WA_NOTIFY_URL, json={"message": message}, timeout=10)
        if resp.status_code == 200:
            channel = f"WA {wa_number}" if wa_number else "FB DM"
            print(f"   ✅ Notif terkirim [{source_type}] {poster_name} → {channel}")
            return True
        else:
            print(f"   ⚠️ WA notify gagal: {resp.status_code} {resp.text[:100]}")
            return False
    except Exception as e:
        print(f"   ⚠️ WA notify error: {e}")
        return False


# ── Scan logic ────────────────────────────────────────────────────────────────

def _handle_lead(page, post_url: str, text: str, poster_name: str,
                 profile_url: str, lead_key: str, source_type: str) -> bool:
    """Generate draft, notify owner, save lead. Return True on success."""
    location  = _extract_location(text)
    wa_number = _extract_wa_number(text) if source_type == 'post' else ''
    via_wa    = bool(wa_number)

    print(f"\n   🎯 Lead [{source_type}]: {poster_name or '?'} | {location}" +
          (f" | 📱 {wa_number}" if wa_number else ""))
    print(f"   📝 {text[:80]}...")

    dm_draft = generate_dm_draft(poster_name, text, location, via_wa=via_wa)
    ok = notify_owner_wa(
        poster_name=poster_name,
        profile_url=profile_url,
        post_url=post_url,
        post_text=text,
        dm_draft=dm_draft,
        location=location,
        wa_number=wa_number,
        source_type=source_type,
    )
    if ok:
        save_lead(lead_key, post_url, poster_name, profile_url, wa_number,
                  location, text[:500], source_type, dm_draft)
    return ok


def _process_post_main(page, post_url: str) -> int:
    """
    Pass 1 — cek teks post utama saja.
    Kalau orang posting cari kos: kirim lead (WA jika ada nomor, FB DM jika tidak).
    Return 1 kalau lead berhasil dikirim, 0 jika tidak.
    """
    post_id  = _post_id_from_url(post_url)
    post_key = f"outreach_post_{post_id}"

    if already_notified(post_key):
        return 0

    try:
        page.goto(post_url, wait_until="domcontentloaded", timeout=20000)
        time.sleep(random.randint(2, 4))

        post_text = _get_post_text(page)
        if not post_text or not _is_seeking(post_text):
            return 0

        poster_name, profile_url = _extract_poster_info(page)
        return 1 if _handle_lead(page, post_url, post_text, poster_name,
                                 profile_url, post_key, source_type='post') else 0
    except Exception as e:
        print(f"   ⚠️ Error cek post utama {post_url}: {e}")
        return 0


def _process_post_comments(page, post_url: str) -> int:
    """
    Pass 2 — scan komentar di satu post.
    Cari komentar yang isinya nanya/cari kos (misal "ada yang daerah kerobokan?").
    Return jumlah leads baru yang berhasil dikirim.
    """
    post_id = _post_id_from_url(post_url)
    leads   = 0

    try:
        page.goto(post_url, wait_until="domcontentloaded", timeout=20000)
        time.sleep(random.randint(2, 4))

        comments = _extract_comments_info(page)
        for c in comments:
            if count_leads_today() >= MAX_LEADS_PER_DAY:
                break
            c_text = c.get('text', '')
            if not c_text or not _is_seeking(c_text):
                continue

            c_id  = hashlib.md5(c_text.encode()).hexdigest()[:12]
            c_key = f"outreach_cmt_{post_id}_{c_id}"
            if already_notified(c_key):
                continue

            comment_url = c.get('commentUrl') or post_url
            if _handle_lead(page, comment_url, c_text,
                            c.get('name', ''), c.get('profileUrl', ''),
                            c_key, source_type='comment'):
                leads += 1
            time.sleep(random.randint(1, 3))

    except Exception as e:
        print(f"   ⚠️ Error scan komentar {post_url}: {e}")

    return leads


def _scan_group_outreach(page, group_url: str) -> int:
    """
    Scan satu grup dalam dua pass:
    Pass 1 — semua post utama yang cari kos (prioritas, ada WA → via WA, tidak ada → FB DM)
    Pass 2 — semua komentar di semua post (cari yang nanya/cari kos di kolom komentar)
    """
    try:
        page.goto(group_url, wait_until="domcontentloaded", timeout=30000)
        time.sleep(random.randint(3, 6))
    except Exception as e:
        print(f"   ⚠️ Gagal buka grup: {e}")
        return 0

    for _ in range(6):
        page.evaluate("window.scrollBy(0, 2000)")
        time.sleep(random.randint(1, 3))

    post_links = page.evaluate("""
        () => {
            const links = new Set();
            document.querySelectorAll('a[href]').forEach(a => {
                const href = a.href || '';
                if (href.includes('facebook.com') && /\\/posts\\/\\d+|story_fbid=\\d+/.test(href)) {
                    links.add(href.split('?')[0]);
                }
            });
            return [...links].slice(0, 30);
        }
    """)

    print(f"   🔎 {len(post_links)} post ditemukan")
    total = 0

    # ── Pass 1: post utama yang cari kos ──────────────────────────────────────
    print("   📌 Pass 1: cek post utama...")
    for post_url in post_links:
        if count_leads_today() >= MAX_LEADS_PER_DAY:
            return total
        total += _process_post_main(page, post_url)
        time.sleep(random.randint(2, 5))

    # ── Pass 2: komentar di semua post ────────────────────────────────────────
    print("   💬 Pass 2: scan komentar semua post...")
    for post_url in post_links:
        if count_leads_today() >= MAX_LEADS_PER_DAY:
            break
        total += _process_post_comments(page, post_url)
        time.sleep(random.randint(2, 5))

    return total


def run_outreach():
    """Scan semua grup FB dan kirim notif WA untuk setiap lead yang ditemukan."""
    if not os.path.exists(FB_SESSION_PATH):
        print(f"❌ Session Facebook tidak ditemukan: {FB_SESSION_PATH}")
        return

    init_outreach_db()
    today_count = count_leads_today()

    if today_count >= MAX_LEADS_PER_DAY:
        print(f"⏸️ Batas lead harian tercapai ({today_count}/{MAX_LEADS_PER_DAY}).")
        return

    print(f"\n🎯 Outreach Scan — {today_count}/{MAX_LEADS_PER_DAY} leads hari ini")

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage",
                  "--disable-blink-features=AutomationControlled"],
        )
        ctx = browser.new_context(
            storage_state=FB_SESSION_PATH,
            viewport={"width": 1280, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
        )
        page = ctx.new_page()

        page.goto("https://www.facebook.com", wait_until="domcontentloaded", timeout=30000)
        time.sleep(3)
        if "login" in page.url or "checkpoint" in page.url:
            print("❌ Session Facebook expired. Perlu re-export session.")
            ctx.close(); browser.close()
            return

        targets = FACEBOOK_GROUPS if FACEBOOK_GROUPS else discover_group_urls(page)

        if not targets:
            print("⚠️ Tidak ada grup ditemukan.")
            ctx.close(); browser.close()
            return

        total_leads = 0
        for group_url in targets:
            if count_leads_today() >= MAX_LEADS_PER_DAY:
                print("⏸️ Batas harian tercapai.")
                break
            print(f"\n📋 Outreach scan grup: {group_url}")
            total_leads += _scan_group_outreach(page, group_url)
            time.sleep(random.randint(10, 20))

        ctx.close()
        browser.close()

    print(f"\n✅ Outreach selesai. Total leads hari ini: {count_leads_today()}/{MAX_LEADS_PER_DAY}")
