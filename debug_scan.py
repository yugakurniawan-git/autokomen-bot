"""
Debug mode — jalankan ini untuk cek apa yang terjadi saat scan.

python3 debug_scan.py
"""
import os, sys, time, random
from playwright.sync_api import sync_playwright
from config import FB_SESSION_PATH, FACEBOOK_GROUPS, SEEKING_KEYWORDS

if not os.path.exists(FB_SESSION_PATH):
    print(f"❌ Session tidak ditemukan: {FB_SESSION_PATH}")
    sys.exit(1)

targets = FACEBOOK_GROUPS if FACEBOOK_GROUPS else ["https://www.facebook.com/groups/feed/"]
print(f"✅ Session ditemukan: {FB_SESSION_PATH}")
print(f"📋 Target scan: {targets}")
print()

with sync_playwright() as p:
    browser = p.chromium.launch(
        headless=False,  # buka browser supaya bisa lihat apa yang terjadi
        args=["--no-sandbox", "--disable-blink-features=AutomationControlled"],
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

    # 1. Cek session valid
    print("🔐 Cek session Facebook...")
    page.goto("https://www.facebook.com", wait_until="domcontentloaded", timeout=30000)
    time.sleep(3)
    print(f"   URL sekarang: {page.url}")
    if "login" in page.url or "checkpoint" in page.url:
        print("❌ Session tidak valid — perlu re-export session.")
        ctx.close(); browser.close(); sys.exit(1)
    print("   ✅ Session valid, sudah login")

    # 2. Buka target (groups/feed kalau FACEBOOK_GROUPS kosong)
    group_url = targets[0]
    print(f"\n📋 Buka: {group_url}")
    page.goto(group_url, wait_until="domcontentloaded", timeout=30000)
    time.sleep(4)
    print(f"   URL setelah redirect: {page.url}")

    # 3. Scroll dan cari post links
    print("\n🔄 Scroll halaman (8x)...")
    for i in range(8):
        page.evaluate("window.scrollBy(0, 2000)")
        time.sleep(2)
        print(f"   Scroll {i+1}/8...")

    # 4. Ambil semua link post
    all_links = page.evaluate("""
        () => {
            const s = new Set();
            document.querySelectorAll('a[href]').forEach(a => {
                const h = a.href || '';
                if (h.includes('facebook.com') && /\\/posts\\/\\d+|story_fbid=\\d+/.test(h)) {
                    s.add(h.split('?')[0]);
                }
            });
            return [...s].slice(0, 20);
        }
    """)
    print(f"\n   Total link post ditemukan: {len(all_links)}")
    for l in all_links[:5]:
        print(f"      {l[:90]}")

    # 6. Kalau ada link, coba buka satu dan cek teksnya
    if all_links:
        # Cek 3 post pertama
        for test_url in all_links[:3]:
            print(f"\n📄 Buka: {test_url[:80]}")
            page.goto(test_url, wait_until="domcontentloaded", timeout=20000)
            time.sleep(3)

            # Ambil teks dengan cara baru
            post_text = page.evaluate("""
                () => {
                    const candidates = [...document.querySelectorAll('div[dir="auto"], [data-ad-preview="message"], [data-ad-comet-preview="message"]')];
                    const texts = candidates
                        .map(el => el.innerText.trim())
                        .filter(t => t.length > 20 && t.length < 5000);
                    return texts.sort((a, b) => b.length - a.length)[0] || '';
                }
            """)
            print(f"   Teks ({len(post_text)} char): {post_text[:150]}")
            matched = [kw for kw in SEEKING_KEYWORDS if kw in post_text.lower()]
            print(f"   Keyword cocok: {matched or 'tidak ada'}")
    else:
        print("\n⚠️ TIDAK ADA LINK POST DITEMUKAN")
        print("   - Coba join lebih banyak grup kos di akun bot")
        print("   - Atau tambahkan URL grup spesifik di config.py")

    input("\n[Browser masih terbuka — tekan Enter untuk tutup]")
    ctx.close()
    browser.close()
