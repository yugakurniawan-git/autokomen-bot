"""
Scan grup Facebook, temukan post/komentar yang mencari kos,
cocokkan dengan listing, lalu komentar/balas.
"""
import re
import sys
import time
import random
import hashlib
import os
from playwright.sync_api import sync_playwright

from config import (
    FB_SESSION_PATH, FACEBOOK_GROUPS,
    SEEKING_KEYWORDS, BALI_AREAS,
    MAX_COMMENTS_PER_DAY, MIN_DELAY_AFTER_POST,
)
from database import (
    already_commented, count_comments_today,
    save_comment, find_matching_listings,
)
from generator import generate_comment


def _extract_sought_location(text: str) -> str:
    text_lower = text.lower()
    for area in BALI_AREAS:
        if area in text_lower:
            return area.title()
    return ""


def _post_id_from_url(url: str) -> str:
    m = re.search(r'/posts/(\d+)', url)
    if m:
        return m.group(1)
    m = re.search(r'story_fbid=(\d+)', url)
    if m:
        return m.group(1)
    return hashlib.md5(url.encode()).hexdigest()[:16]


OFFERING_SIGNALS = [
    "disewakan", "kami sewakan", "kami tawarkan", "kami punya kos",
    "tersedia kamar", "kamar tersedia", "masih ada kamar", "masih kosong",
    "per bulan", "perbulan", "/bulan", "/bln",
    "hubungi kami", "wa kami", "dm kami", "contact us",
    "fasilitas:", "harga:", "tarif:", "biaya sewa",
]

def _is_seeking(text: str) -> bool:
    text_lower = text.lower()
    if not any(kw in text_lower for kw in SEEKING_KEYWORDS):
        return False
    # Kalau dominan offering, bukan seeking
    offering_hits = sum(1 for s in OFFERING_SIGNALS if s in text_lower)
    if offering_hits >= 2:
        return False
    return True


def _get_post_text(page) -> str:
    """Ambil teks konten post, hindari teks navigasi."""
    return page.evaluate("""
        () => {
            const candidates = [...document.querySelectorAll(
                'div[dir="auto"], [data-ad-preview="message"], [data-ad-comet-preview="message"]'
            )];
            const texts = candidates
                .map(el => el.innerText.trim())
                .filter(t => t.length > 20 && t.length < 5000);
            return texts.sort((a, b) => b.length - a.length)[0] || '';
        }
    """)


KOS_GROUP_KEYWORDS = [
    "kos", "kost", "kontrakan", "sewa", "rent", "room", "kamar",
    "properti", "property", "housing", "hunian", "indekos",
]
SKIP_IDS = ["feed", "discover", "create", "you", "joins", "search"]

def discover_group_urls(page) -> list:
    """
    Auto-discover grup yang diikuti akun, filter hanya grup kos/sewa.
    Grup yang namanya tidak mengandung kata kos-related akan diskip.
    """
    print("🔍 Auto-discover grup kos dari akun...")
    page.goto("https://www.facebook.com/groups/", wait_until="domcontentloaded", timeout=30000)
    time.sleep(3)

    for _ in range(5):
        page.evaluate("window.scrollBy(0, 1500)")
        time.sleep(1)

    groups = page.evaluate("""
        () => {
            const found = [];
            document.querySelectorAll('a[href*="/groups/"]').forEach(a => {
                const m = (a.href || '').match(/facebook\\.com\\/groups\\/(\\d+|[a-zA-Z0-9._]+)\\/?/);
                if (m) {
                    const name = (a.innerText || a.textContent || '').trim();
                    found.push({ url: 'https://www.facebook.com/groups/' + m[1] + '/', name, id: m[1] });
                }
            });
            return found;
        }
    """)

    filtered = []
    skipped = []
    seen = set()
    for g in groups:
        gid = g.get("id", "")
        name = g.get("name", "").lower()
        url = g.get("url", "")
        if gid in SKIP_IDS or gid in seen:
            continue
        seen.add(gid)
        if any(kw in name for kw in KOS_GROUP_KEYWORDS):
            filtered.append(url)
            print(f"   ✅ {g['name'] or gid}")
        else:
            skipped.append(g.get("name") or gid)

    if skipped:
        print(f"   ⏭️  Skip {len(skipped)} grup non-kos: {', '.join(skipped[:5])}" +
              (f" +{len(skipped)-5} lainnya" if len(skipped) > 5 else ""))

    print(f"   📋 Total grup kos: {len(filtered)}")
    return filtered


def _do_comment(page, target_url: str, comment_text: str, is_reply: bool = False) -> bool:
    """Buka post/komentar dan posting komentar/balasan."""
    try:
        page.goto(target_url, wait_until="domcontentloaded", timeout=20000)
        time.sleep(random.randint(2, 4))

        # Cari kotak komentar
        comment_box = page.query_selector(
            '[contenteditable="true"][aria-label*="comment" i], '
            '[contenteditable="true"][aria-label*="komentar" i], '
            '[contenteditable="true"][aria-label*="Reply" i], '
            '[contenteditable="true"][aria-label*="Balas" i]'
        )

        if not comment_box:
            # Klik tombol "Komentar" untuk expand dulu
            for btn_text in ["Comment", "Komentar"]:
                btn = page.query_selector(f'[aria-label="{btn_text}"]')
                if btn:
                    btn.click()
                    time.sleep(2)
                    break
            comment_box = page.query_selector('[contenteditable="true"]')

        if not comment_box:
            print("   ⚠️ Kotak komentar tidak ditemukan.")
            return False

        comment_box.click()
        time.sleep(1)

        # Ambil snapshot teks komentar sebelum posting untuk verifikasi
        first_words = " ".join(comment_text.split()[:4]).lower()

        for char in comment_text:
            comment_box.type(char, delay=random.randint(25, 70))

        time.sleep(random.randint(1, 2))
        comment_box.press("Enter")

        # Tunggu dan verifikasi komentar benar-benar muncul di halaman
        time.sleep(6)
        try:
            page_text = page.inner_text("body").lower()
            if first_words in page_text:
                return True
            else:
                print("   ⚠️ Komentar dikirim tapi tidak muncul di halaman (mungkin diblokir FB).")
                return False
        except Exception:
            # Kalau tidak bisa verifikasi, anggap gagal agar tidak salah catat
            return False

    except Exception as e:
        print(f"   ⚠️ Gagal posting komentar: {e}")
        return False


def _process_post(page, post_url: str) -> int:
    """
    Buka satu post, cek:
    1. Teks post utama — kalau seeking, komentar
    2. Komentar di post — kalau ada yang seeking, balas komentar itu

    Return jumlah komentar yang berhasil dipost.
    """
    commented = 0
    post_id = _post_id_from_url(post_url)

    try:
        page.goto(post_url, wait_until="domcontentloaded", timeout=20000)
        time.sleep(random.randint(2, 4))

        # ── 1. Cek teks post utama ──────────────────────────────────────────
        post_text = _get_post_text(page)
        comment_key = f"post_{post_id}"

        if post_text and _is_seeking(post_text) and not already_commented(comment_key):
            sought = _extract_sought_location(post_text)
            listings = find_matching_listings(sought)
            if listings:
                listing = listings[0]
                lid, lloc, lprice, _, _, lcap = listing

                # Ambil nama poster
                name_el = page.query_selector('h2 a strong, h3 a, [data-ad-rendering-role="profile_name"] span')
                poster = name_el.inner_text().strip() if name_el else "kak"

                text = generate_comment(poster, sought, lid, lloc or "Bali", lprice or "", lcap or "")
                print(f"\n   📝 Post seeking: {post_text[:60]}...")
                print(f"   💬 Komentar: {text[:80]}...")

                delay = random.randint(MIN_DELAY_AFTER_POST * 60, (MIN_DELAY_AFTER_POST + 2) * 60)
                print(f"   ⏳ Tunggu {delay//60} mnt...")
                time.sleep(delay)

                ok = _do_comment(page, post_url, text)
                if ok:
                    save_comment(comment_key, post_url, sought, lid, text)
                    print(f"   ✅ Komentar berhasil di post (BK-{lid})")
                    commented += 1
                    time.sleep(random.randint(30, 90))

        if count_comments_today() >= MAX_COMMENTS_PER_DAY:
            return commented

        # ── 2. Cek komentar di post — cari yang seeking ────────────────────
        comments = page.evaluate("""
            () => {
                const results = [];
                // Expand "lihat komentar" kalau ada
                document.querySelectorAll('[aria-label*="comment" i][role="button"]').forEach(b => {
                    try { b.click(); } catch(e) {}
                });

                document.querySelectorAll('div[dir="auto"]').forEach(el => {
                    const text = el.innerText.trim();
                    const link = el.closest('a') || el.closest('[data-commentid]');
                    if (text.length > 15 && text.length < 500) {
                        results.push({ text, commentId: el.closest('[id]')?.id || '' });
                    }
                });
                return results.slice(0, 20);
            }
        """)

        for c in comments:
            if count_comments_today() >= MAX_COMMENTS_PER_DAY:
                break
            c_text = c.get("text", "")
            c_id = c.get("commentId", "") or hashlib.md5(c_text.encode()).hexdigest()[:12]
            reply_key = f"reply_{post_id}_{c_id}"

            if not _is_seeking(c_text) or already_commented(reply_key):
                continue

            sought = _extract_sought_location(c_text)
            listings = find_matching_listings(sought)
            if not listings:
                continue

            listing = listings[0]
            lid, lloc, lprice, _, _, lcap = listing
            text = generate_comment("kak", sought, lid, lloc or "Bali", lprice or "", lcap or "")

            print(f"\n   💬 Komentar seeking: {c_text[:60]}...")
            print(f"   ↩️  Balas: {text[:80]}...")

            delay = random.randint(MIN_DELAY_AFTER_POST * 60, (MIN_DELAY_AFTER_POST + 2) * 60)
            print(f"   ⏳ Tunggu {delay//60} mnt...")
            time.sleep(delay)

            ok = _do_comment(page, post_url, text)
            if ok:
                save_comment(reply_key, post_url, sought, lid, text)
                print(f"   ✅ Balasan berhasil (BK-{lid})")
                commented += 1
                time.sleep(random.randint(30, 90))

    except Exception as e:
        print(f"   ⚠️ Error proses post: {e}")

    return commented


def _scan_group(page, group_url: str) -> int:
    """Scan satu grup, return jumlah komentar yang dipost."""
    try:
        page.goto(group_url, wait_until="domcontentloaded", timeout=30000)
        time.sleep(random.randint(4, 7))
    except Exception as e:
        print(f"   ⚠️ Gagal buka grup: {e}")
        return 0

    # Scroll untuk load lebih banyak post
    for _ in range(8):
        page.evaluate("window.scrollBy(0, 2000)")
        time.sleep(random.randint(2, 3))

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

    for post_url in post_links:
        if count_comments_today() >= MAX_COMMENTS_PER_DAY:
            break
        total += _process_post(page, post_url)
        time.sleep(random.randint(3, 6))

    return total


def scan_and_comment():
    """Scan semua grup dan komentar post/komentar yang relevan."""
    if not os.path.exists(FB_SESSION_PATH):
        print(f"❌ Session Facebook tidak ditemukan: {FB_SESSION_PATH}")
        return

    today_count = count_comments_today()
    if today_count >= MAX_COMMENTS_PER_DAY:
        print(f"⏸️ Batas harian tercapai ({today_count}/{MAX_COMMENTS_PER_DAY}).")
        return

    print(f"\n🔍 Scan — {today_count}/{MAX_COMMENTS_PER_DAY} komentar hari ini")

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

        # Auto-discover grup kalau tidak ada di config
        targets = FACEBOOK_GROUPS if FACEBOOK_GROUPS else discover_group_urls(page)

        if not targets:
            print("⚠️ Tidak ada grup ditemukan. Pastikan akun sudah join grup.")
            ctx.close(); browser.close()
            return

        total = 0
        for group_url in targets:
            if count_comments_today() >= MAX_COMMENTS_PER_DAY:
                print("⏸️ Batas harian tercapai.")
                break
            print(f"\n📋 Grup: {group_url}")
            total += _scan_group(page, group_url)
            time.sleep(random.randint(20, 40))

        ctx.close()
        browser.close()

    print(f"\n✅ Scan selesai. Total komentar hari ini: {count_comments_today()}/{MAX_COMMENTS_PER_DAY}")
