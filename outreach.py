"""
SupportKos Outreach Pipeline — Feature 1.

Scan grup FB setiap jam, cari post "cari kos Bali", generate draft DM
yang menawarkan jasa inspeksi kos SupportKos, lalu kirim notif ke owner via WA.
Owner tinggal copy-paste draft DM dan buka profil FB-nya.
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
    WA_NOTIFY_URL, MAX_LEADS_PER_DAY,
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
            location     TEXT,
            post_text    TEXT,
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


def save_lead(fb_post_id, post_url, poster_name, profile_url, location, post_text, dm_draft):
    conn = sqlite3.connect(OUTREACH_DB_PATH)
    try:
        conn.execute("""
            INSERT INTO outreach_leads
                (fb_post_id, post_url, poster_name, profile_url, location, post_text, dm_draft)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (fb_post_id, post_url, poster_name, profile_url, location, post_text, dm_draft))
        conn.commit()
    except sqlite3.IntegrityError:
        pass
    finally:
        conn.close()


# ── FB DOM helpers ────────────────────────────────────────────────────────────

def _extract_poster_info(page) -> tuple[str, str]:
    """Return (poster_name, profile_url) dari halaman post yang sudah dibuka."""
    result = page.evaluate("""
        () => {
            // Coba temukan link profil penulis post — biasanya h2/h3 di header post
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
                    // Bersihkan query string yang panjang, simpan profil saja
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
    name = result[0] if result else ''
    url  = result[1] if result else ''
    return name, url


def _extract_location(text: str) -> str:
    text_lower = text.lower()
    for area in BALI_AREAS:
        if area in text_lower:
            return area.title()
    return "Bali"


# ── DM Draft Generator ────────────────────────────────────────────────────────

_DM_FALLBACKS = [
    "Halo {name}! Aku lihat kamu lagi cari kos di {location}.\n\nKebetulan aku bisa bantu cek kondisi kos sebelum kamu DP — foto terkini, fasilitas asli, lingkungan sekitar. Gratis konsultasi.\n\nMau aku bantu cariin dan cekkan dulu?",
    "Hai {name}, masih cari kos di {location} ya?\n\nBoleh aku bantu! Aku biasa survei kos langsung ke lapangan — jadi kamu bisa tau kondisi aslinya sebelum bayar. Kalau tertarik, chat aku ya.",
    "Halo {name}! Lagi cari kos di {location}?\n\nAku bisa bantu survei dan foto kondisi kos buat kamu sebelum DP. Biar nggak kaget pas udah bayar. Mau dibantu?",
]


def generate_dm_draft(poster_name: str, post_text: str, location: str) -> str:
    first_name = poster_name.split()[0] if poster_name else "Kak"
    loc = location or "Bali"

    if not OPENAI_API_KEY:
        import random as _r
        return _r.choice(_DM_FALLBACKS).format(name=first_name, location=loc)

    try:
        from openai import OpenAI
        client = OpenAI(api_key=OPENAI_API_KEY)

        prompt = f"""Kamu adalah penulis DM yang sopan dan natural di Facebook.

Seseorang bernama "{first_name}" baru saja posting di grup FB:
"{post_text[:300]}"

Mereka lagi cari kos di {loc}.

Tulis DM singkat (3-5 kalimat) yang:
- Menawarkan jasa survei/inspeksi kos sebelum DP (jasa bernama SupportKos)
- Terasa seperti teman yang genuinely mau bantu, bukan sales
- Sebutkan bahwa kamu bisa cek kondisi asli, foto terbaru, dan lingkungan kos
- Bahasa santai tapi sopan (mix Indonesia/gaul oke)
- Tidak perlu mention harga, tidak ada link, tidak ada hashtag
- Tutup dengan ajakan untuk chat/reply

Tulis hanya isi DM-nya saja, tanpa penjelasan."""

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=200,
            temperature=0.9,
        )
        return response.choices[0].message.content.strip().strip('"').strip("'")
    except Exception as e:
        print(f"⚠️ OpenAI gagal, pakai template DM: {e}")
        import random as _r
        return _r.choice(_DM_FALLBACKS).format(name=first_name, location=loc)


# ── WA Notify ─────────────────────────────────────────────────────────────────

def notify_owner_wa(poster_name: str, profile_url: str, post_url: str,
                    post_text: str, dm_draft: str, location: str):
    short_post = post_text[:150].replace('\n', ' ')
    message = (
        f"🎯 *Lead SupportKos Baru!*\n\n"
        f"👤 Nama: {poster_name or '(tidak terdeteksi)'}\n"
        f"📍 Lokasi: {location}\n"
        f"🔗 Profil FB: {profile_url or post_url}\n\n"
        f"📝 *Post asli:*\n_{short_post}_\n\n"
        f"✍️ *Draft DM:*\n---\n{dm_draft}\n---\n\n"
        f"👉 Buka profil di atas → kirim DM dengan teks di atas"
    )

    try:
        resp = requests.post(WA_NOTIFY_URL, json={"message": message}, timeout=10)
        if resp.status_code == 200:
            print(f"   ✅ Notif WA terkirim untuk lead: {poster_name}")
            return True
        else:
            print(f"   ⚠️ WA notify gagal: {resp.status_code} {resp.text[:100]}")
            return False
    except Exception as e:
        print(f"   ⚠️ WA notify error: {e}")
        return False


# ── Scan logic ────────────────────────────────────────────────────────────────

def _process_post_outreach(page, post_url: str) -> bool:
    """Proses satu post untuk outreach. Return True kalau lead berhasil dikirim."""
    post_id = _post_id_from_url(post_url)
    lead_key = f"outreach_{post_id}"

    if already_notified(lead_key):
        return False

    try:
        page.goto(post_url, wait_until="domcontentloaded", timeout=20000)
        time.sleep(random.randint(2, 4))

        post_text = _get_post_text(page)
        if not post_text or not _is_seeking(post_text):
            return False

        poster_name, profile_url = _extract_poster_info(page)
        location = _extract_location(post_text)

        print(f"\n   🎯 Lead ditemukan: {poster_name or '?'} | {location}")
        print(f"   📝 Post: {post_text[:80]}...")

        dm_draft = generate_dm_draft(poster_name, post_text, location)
        ok = notify_owner_wa(poster_name, profile_url, post_url, post_text, dm_draft, location)

        if ok:
            save_lead(lead_key, post_url, poster_name, profile_url, location, post_text[:500], dm_draft)
            return True

    except Exception as e:
        print(f"   ⚠️ Error outreach post: {e}")

    return False


def _scan_group_outreach(page, group_url: str) -> int:
    """Scan satu grup untuk outreach leads. Return jumlah leads ditemukan."""
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
    leads = 0

    for post_url in post_links:
        if count_leads_today() >= MAX_LEADS_PER_DAY:
            break
        if _process_post_outreach(page, post_url):
            leads += 1
        time.sleep(random.randint(2, 5))

    return leads


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
